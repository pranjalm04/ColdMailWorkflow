import argparse
import csv
import logging
import sys
from pathlib import Path

from . import apollo, pipeline
from .config import CONTACTS_PATH, DEFAULT_ROLE
from .models import Contact, GeneratedEmail

logger = logging.getLogger("cold_mail_workflow")


def _load_forward_email(path: Path, subject: str | None) -> GeneratedEmail:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        file_subject = lines[0].split(":", 1)[1].strip()
        body = "\n".join(lines[1:]).strip()
    else:
        file_subject = ""
        body = text.strip()

    final_subject = (subject or file_subject).strip()
    if not final_subject:
        raise ValueError("No subject: provide --subject or a leading 'Subject:' line in the email file.")
    if not body:
        raise ValueError(f"Email file has no body: {path}")
    return GeneratedEmail(subject=final_subject, body=body, metadata={"source": "forwarded"})


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cold_mail_workflow",
        description="Generate and send personalized cold emails to recruiters.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send emails via Gmail. Default is dry-run (generate only).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Scan at most N contacts from the sources (before the already-sent check).")
    parser.add_argument(
        "--max-new",
        type=int,
        default=None,
        metavar="N",
        help="Send to at most N NEW contacts this run (those not already in the tracker). "
        "Bounds new emails (and generation cost) regardless of how many sources are loaded. Re-run to continue.",
    )
    parser.add_argument(
        "--company",
        type=str,
        default=None,
        help="In file mode, filter to a single company. With --to, the company for that one record.",
    )
    parser.add_argument(
        "--to",
        type=str,
        default=None,
        metavar="EMAIL",
        help="Single-record mode: recruiter email. Runs the workflow for just this one contact, "
        "ignoring the contacts files. Use with --company / --recruiter-name / --title / --role.",
    )
    parser.add_argument("--recruiter-name", type=str, default=None, help="Recruiter name for --to mode (greeting).")
    parser.add_argument("--title", type=str, default=None, help="Recipient title for --to mode (drives technical depth).")
    parser.add_argument(
        "--notes",
        type=str,
        default=None,
        help="Freeform hint for --to mode (e.g. the job posting text) passed to the generator for grounding.",
    )
    parser.add_argument(
        "--contacts",
        type=Path,
        default=CONTACTS_PATH,
        help="Path to a contacts file (.csv or .xlsx). Defaults to config CONTACTS_PATH.",
    )
    parser.add_argument(
        "--role",
        type=str,
        default=DEFAULT_ROLE,
        help="Target role for rows that don't specify one (used in dedup + email). Default from config.",
    )
    parser.add_argument(
        "--forward-email",
        type=Path,
        default=None,
        metavar="PATH",
        help="Forward mode: send the fixed email in this file to the whole batch, skipping generation. "
        "First line may be 'Subject: ...'; the rest is the body. Dedup/tracking still apply.",
    )
    parser.add_argument(
        "--subject",
        type=str,
        default=None,
        help="Subject line for --forward-email (overrides a 'Subject:' line in the file).",
    )
    parser.add_argument(
        "--followup",
        action="store_true",
        help="Follow-up mode: send a short follow-up to every contact already marked 'sent' in the tracker, "
        "replying in the original Gmail thread. Skips contacts already followed up. Honors --send/--limit/--company.",
    )
    parser.add_argument(
        "--apollo-company",
        type=str,
        default=None,
        metavar="COMPANY",
        help="Apollo mode: look up the top technical recruiters at COMPANY via the Apollo API and print them. "
        "Does not send anything. Combine with --apollo-save to write them to a contacts CSV.",
    )
    parser.add_argument(
        "--apollo-limit",
        type=int,
        default=10,
        help="How many technical recruiters to return in --apollo-company mode (default 10).",
    )
    parser.add_argument(
        "--apollo-unlock",
        action="store_true",
        help="In --apollo-company mode, reveal recruiter emails via Apollo bulk match. "
        "CONSUMES Apollo credits. Without it, locked emails come back blank.",
    )
    parser.add_argument(
        "--apollo-save",
        type=Path,
        default=None,
        metavar="PATH",
        help="In --apollo-company mode, also write the recruiters to this CSV path (ingest-compatible, "
        "so the normal pipeline can then email them).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args(argv)


def _save_contacts_csv(path: Path, contacts: list[Contact]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["company", "role", "recruiter_name", "recruiter_email", "title", "notes"])
        for c in contacts:
            writer.writerow([c.company, c.role, c.recruiter_name, c.recruiter_email, c.title, c.notes])


def _run_apollo(company: str, limit: int, role: str, unlock: bool, save: Path | None, log: logging.Logger) -> int:
    try:
        recruiters = apollo.search_recruiters(company, limit=limit, role=role, unlock=unlock)
    except Exception as exc:
        log.error("Fatal: Apollo lookup failed: %s", exc)
        return 1

    if not recruiters:
        log.warning("No technical recruiters found for %r.", company)
        return 0

    print(f"\nTop {len(recruiters)} technical recruiter(s) at {company}:\n")
    for i, c in enumerate(recruiters, start=1):
        email = c.recruiter_email or "(email locked — re-run with --apollo-unlock to reveal)"
        print(f"{i:>2}. {c.recruiter_name or '(unknown)'} — {c.title or '(no title)'}")
        print(f"    {email}")

    if save is not None:
        _save_contacts_csv(save, recruiters)
        log.info("Saved %d recruiter(s) to %s", len(recruiters), save)

    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    log = logger

    if args.apollo_company:
        return _run_apollo(
            args.apollo_company, args.apollo_limit, args.role, args.apollo_unlock, args.apollo_save, log
        )

    forward_email = None
    if args.forward_email:
        if not args.forward_email.exists():
            log.error("Fatal: --forward-email file not found: %s", args.forward_email)
            return 1
        try:
            forward_email = _load_forward_email(args.forward_email, args.subject)
        except (OSError, ValueError) as exc:
            log.error("Fatal: %s", exc)
            return 1
        log.info("Forward mode: sending fixed email %r to the batch (generation skipped).", forward_email.subject)
    elif args.subject:
        log.warning("--subject is ignored without --forward-email.")

    single = None
    if args.to:
        if "@" not in args.to:
            log.error("Fatal: --to must be a valid email address, got %r", args.to)
            return 1
        single = Contact(
            company=(args.company or "").strip(),
            role=args.role,
            recruiter_email=args.to.strip(),
            recruiter_name=(args.recruiter_name or "").strip(),
            title=(args.title or "").strip(),
            notes=(args.notes or "").strip(),
        )
        log.info("Single-record mode: %s / %s -> %s", single.company or "(no company)", single.role, single.recruiter_email)

    try:
        if args.followup:
            if single or forward_email:
                log.error("Fatal: --followup cannot be combined with --to or --forward-email.")
                return 1
            stats = pipeline.run_followups(
                send=args.send,
                limit=args.limit,
                company=args.company,
                contacts_path=args.contacts,
                max_new=args.max_new,
            )
        else:
            stats = pipeline.run(
                send=args.send,
                limit=args.limit,
                company=args.company,
                contacts_path=args.contacts,
                role=args.role,
                contact=single,
                forward_email=forward_email,
                max_new=args.max_new,
            )
    except Exception as exc:
        log.error("Fatal: %s", exc)
        return 1

    mode = ("FOLLOWUP-SEND" if args.followup else "SEND") if args.send else ("FOLLOWUP-DRY-RUN" if args.followup else "DRY-RUN")
    log.info(
        "[%s] done | total=%d generated=%d sent=%d skipped=%d failed=%d",
        mode,
        stats.total,
        stats.generated,
        stats.sent,
        stats.skipped,
        stats.failed,
    )
    return 0 if not stats.failed else 2


if __name__ == "__main__":
    sys.exit(main())
