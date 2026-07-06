import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pathlib import Path

from . import generate, ingest, mailer, suppress, tracker
from .config import (
    CONTACTS_PATH,
    CV_PATH,
    DEFAULT_ROLE,
    MAX_SENDS_PER_RUN,
    RESUME_PATH,
    SEND_DELAY_SECONDS,
)
from .models import Contact, FollowupTarget, GeneratedEmail, TrackerRecord

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    total: int = 0
    skipped: int = 0
    generated: int = 0
    sent: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_cv() -> str:
    if not CV_PATH.exists():
        raise FileNotFoundError(f"CV not found: {CV_PATH}")
    text = CV_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"CV is empty: {CV_PATH}")
    return text


def _dedup(contacts: list[Contact]) -> list[Contact]:
    seen: set[str] = set()
    out: list[Contact] = []
    for c in contacts:
        key = tracker.dedup_key(c)
        if key in seen:
            logger.info("Duplicate across files, skipping: %s / %s -> %s", c.company, c.role, c.recruiter_email)
            continue
        seen.add(key)
        out.append(c)
    return out


def _select(contacts: list[Contact], company: str | None, limit: int | None) -> list[Contact]:
    selected = contacts
    if company:
        needle = company.strip().lower()
        selected = [c for c in selected if c.company.strip().lower() == needle]
    if limit is not None:
        selected = selected[:limit]
    return selected


def _preview(contact: Contact, email: GeneratedEmail) -> None:
    logger.info(
        "DRY-RUN preview | to=%s | %s / %s\nSubject: %s\n%s",
        ", ".join(contact.recipients),
        contact.company,
        contact.role,
        email.subject,
        email.body,
    )


def _send_all(
    recipients: list[str],
    email: GeneratedEmail,
    service,
    attachment: Path,
    thread_id: str | None = None,
) -> tuple[list[str], list[str]]:
    sent_ids: list[str] = []
    errors: list[str] = []
    for i, addr in enumerate(recipients):
        try:
            sent_ids.append(
                mailer.send(addr, email, service=service, attachment=attachment, thread_id=thread_id)
            )
        except Exception as exc:
            errors.append(f"{addr}: {exc}")
        if SEND_DELAY_SECONDS > 0 and i < len(recipients) - 1:
            time.sleep(SEND_DELAY_SECONDS)
    return sent_ids, errors


def _re_subject(subject: str) -> str:
    s = (subject or "").strip()
    if not s:
        return ""
    return s if s.lower().startswith("re:") else f"Re: {s}"


def _build_followup_targets(contacts_path: Path) -> list[FollowupTarget]:
    enrich: dict[str, Contact] = {}
    try:
        for c in ingest.read_contacts(contacts_path):
            enrich.setdefault(tracker.dedup_key(c), c)
    except Exception as exc:
        logger.warning("Could not load contacts for follow-up enrichment (names/titles): %s", exc)

    targets: list[FollowupTarget] = []
    for row in tracker.sent_rows():
        key = row.get("dedup_key", "")
        base = enrich.get(key)
        contact = Contact(
            company=row.get("company", ""),
            role=row.get("role", ""),
            recruiter_email=row.get("recruiter_email", ""),
            recruiter_name=base.recruiter_name if base else "",
            title=base.title if base else "",
            job_url=base.job_url if base else "",
            notes=base.notes if base else "",
        )
        targets.append(
            FollowupTarget(
                contact=contact,
                dedup_key=key,
                thread_id=row.get("gmail_message_id", ""),
                prior_subject=row.get("subject", ""),
            )
        )
    return targets


def _select_followups(targets: list[FollowupTarget], company: str | None, limit: int | None) -> list[FollowupTarget]:
    selected = targets
    if company:
        needle = company.strip().lower()
        selected = [t for t in selected if t.contact.company.strip().lower() == needle]
    if limit is not None:
        selected = selected[:limit]
    return selected


def run_followups(
    send: bool = False,
    limit: int | None = None,
    company: str | None = None,
    contacts_path: Path = CONTACTS_PATH,
    resume_path: Path = RESUME_PATH,
    max_new: int | None = None,
) -> RunStats:
    stats = RunStats()
    cv_text = _load_cv()

    if not resume_path.exists():
        raise FileNotFoundError(f"Resume to attach not found: {resume_path}")

    targets = _select_followups(_build_followup_targets(contacts_path), company, limit)
    stats.total = len(targets)

    if not send:
        logger.info(
            "DRY-RUN mode: %d follow-up(s) will be generated, nothing sent. Resume attachment: %s",
            stats.total,
            resume_path.name,
        )

    service = mailer.build_service() if send else None
    sent_this_run = 0
    new_processed = 0
    blocked = suppress.load()

    for target in targets:
        key = target.dedup_key
        contact = target.contact

        if blocked and any(suppress.normalize(e) in blocked for e in contact.recipients):
            stats.skipped += 1
            logger.info("Skip (suppressed / do-not-contact): %s / %s -> %s", contact.company, contact.role, contact.recruiter_email)
            continue

        if tracker.already_followed_up(key):
            stats.skipped += 1
            logger.info("Skip (already followed up): %s / %s -> %s", contact.company, contact.role, contact.recruiter_email)
            continue

        if max_new is not None and new_processed >= max_new:
            logger.info("Reached --max-new limit (%d new follow-up(s)). Stopping; re-run to continue the rest.", max_new)
            break
        new_processed += 1

        try:
            email = generate.compose(contact, cv_text, followup=True, prior_subject=target.prior_subject)
            stats.generated += 1
        except Exception as exc:
            stats.failed += 1
            msg = f"follow-up generate failed for {contact.company}/{contact.role}: {exc}"
            stats.errors.append(msg)
            logger.error(msg)
            tracker.append(
                TrackerRecord(
                    timestamp=_utc_now(),
                    dedup_key=key,
                    recruiter_email=contact.recruiter_email,
                    company=contact.company,
                    role=contact.role,
                    subject="",
                    gmail_message_id="",
                    status="followup_failed",
                )
            )
            continue

        # Reply in the original thread: keep the subject identical (Re: ...) so Gmail groups it.
        threaded_subject = _re_subject(target.prior_subject)
        if threaded_subject:
            email.subject = threaded_subject

        if not send:
            _preview(contact, email)
            continue

        if sent_this_run >= MAX_SENDS_PER_RUN:
            logger.warning("Per-run send cap reached (%d). Stopping; re-run to continue the rest.", MAX_SENDS_PER_RUN)
            break

        try:
            message_id = mailer.send(
                contact.recruiter_email,
                email,
                service=service,
                attachment=resume_path,
                thread_id=target.thread_id or None,
            )
            stats.sent += 1
            sent_this_run += 1
            tracker.append(
                TrackerRecord(
                    timestamp=_utc_now(),
                    dedup_key=key,
                    recruiter_email=contact.recruiter_email,
                    company=contact.company,
                    role=contact.role,
                    subject=email.subject,
                    gmail_message_id=message_id,
                    status="followup_sent",
                )
            )
        except Exception as exc:
            stats.failed += 1
            msg = f"follow-up send failed for {contact.company}/{contact.role}: {exc}"
            stats.errors.append(msg)
            logger.error(msg)
            tracker.append(
                TrackerRecord(
                    timestamp=_utc_now(),
                    dedup_key=key,
                    recruiter_email=contact.recruiter_email,
                    company=contact.company,
                    role=contact.role,
                    subject=email.subject,
                    gmail_message_id="",
                    status="followup_failed",
                )
            )
            continue

        if SEND_DELAY_SECONDS > 0:
            time.sleep(SEND_DELAY_SECONDS)

    return stats


def run(
    send: bool = False,
    limit: int | None = None,
    company: str | None = None,
    contacts_path: Path = CONTACTS_PATH,
    role: str = DEFAULT_ROLE,
    resume_path: Path = RESUME_PATH,
    contact: Contact | None = None,
    forward_email: GeneratedEmail | None = None,
    max_new: int | None = None,
) -> RunStats:
    stats = RunStats()
    cv_text = "" if forward_email is not None else _load_cv()
    if contact is not None:
        contacts = [contact]
    else:
        contacts = _select(_dedup(ingest.read_contacts(contacts_path, role)), company, limit)
    stats.total = len(contacts)

    if not resume_path.exists():
        raise FileNotFoundError(f"Resume to attach not found: {resume_path}")

    if not send:
        verb = "forwarded the provided email" if forward_email is not None else "generated"
        logger.info(
            "DRY-RUN mode: %d contact(s) will be %s, nothing sent. Resume attachment: %s",
            stats.total,
            verb,
            resume_path.name,
        )

    service = mailer.build_service() if send else None
    sent_this_run = 0
    new_processed = 0
    blocked = suppress.load()

    for contact in contacts:
        key = tracker.dedup_key(contact)

        if blocked and any(suppress.normalize(e) in blocked for e in contact.recipients):
            stats.skipped += 1
            logger.info("Skip (suppressed / do-not-contact): %s / %s -> %s", contact.company, contact.role, contact.recruiter_email)
            continue

        if tracker.already_sent(key):
            stats.skipped += 1
            logger.info("Skip (already sent): %s / %s -> %s", contact.company, contact.role, contact.recruiter_email)
            continue

        if max_new is not None and new_processed >= max_new:
            logger.info("Reached --max-new limit (%d new email(s)). Stopping; re-run to continue the rest.", max_new)
            break
        new_processed += 1

        if forward_email is not None:
            email = forward_email
            stats.generated += 1
        else:
            try:
                email = generate.compose(contact, cv_text)
                stats.generated += 1
            except Exception as exc:
                stats.failed += 1
                msg = f"generate failed for {contact.company}/{contact.role}: {exc}"
                stats.errors.append(msg)
                logger.error(msg)
                tracker.append(
                    TrackerRecord(
                        timestamp=_utc_now(),
                        dedup_key=key,
                        recruiter_email=contact.recruiter_email,
                        company=contact.company,
                        role=contact.role,
                        subject="",
                        gmail_message_id="",
                        status="failed",
                    )
                )
                continue

        if not send:
            _preview(contact, email)
            continue

        if sent_this_run >= MAX_SENDS_PER_RUN:
            logger.warning("Per-run send cap reached (%d). Stopping.", MAX_SENDS_PER_RUN)
            break

        recipients = contact.recipients
        sent_ids, send_errors = _send_all(recipients, email, service, resume_path)

        if sent_ids:
            stats.sent += 1
            sent_this_run += 1
            for err in send_errors:
                msg = f"partial send failure for {contact.company}/{contact.role}: {err}"
                stats.errors.append(msg)
                logger.error(msg)
            logger.info(
                "Sent to %d/%d address(es) for %s / %s",
                len(sent_ids),
                len(recipients),
                contact.company,
                contact.role,
            )
            tracker.append(
                TrackerRecord(
                    timestamp=_utc_now(),
                    dedup_key=key,
                    recruiter_email=contact.recruiter_email,
                    company=contact.company,
                    role=contact.role,
                    subject=email.subject,
                    gmail_message_id=sent_ids[0],
                    status="sent",
                )
            )
        else:
            stats.failed += 1
            msg = f"send failed for {contact.company}/{contact.role}: {'; '.join(send_errors)}"
            stats.errors.append(msg)
            logger.error(msg)
            tracker.append(
                TrackerRecord(
                    timestamp=_utc_now(),
                    dedup_key=key,
                    recruiter_email=contact.recruiter_email,
                    company=contact.company,
                    role=contact.role,
                    subject=email.subject,
                    gmail_message_id="",
                    status="failed",
                )
            )
            continue

        if SEND_DELAY_SECONDS > 0:
            time.sleep(SEND_DELAY_SECONDS)

    return stats
