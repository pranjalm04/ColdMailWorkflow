# ColdMailWorkflow

A batch CLI for personalized job-outreach cold emails. It reads recruiter contacts from an
Excel file, generates a tailored email for each one with the Anthropic SDK (grounded in your
CV), and sends them via the Gmail API. Every send is recorded, and no contact is emailed twice
for the same role.

**Dry-run is the default. Nothing is sent unless you pass `--send`.**

## How it works

For each contact, `pipeline.run()`:

1. **Ingest** — reads `data/contacts.xlsx` into `Contact` records.
2. **Dedup** — computes a `(company, role, recruiter)` key; if it was already sent, skips.
3. **Generate** — one Anthropic call returns subject + body + metadata as JSON, grounded in `cv.md`.
4. **Send** — builds a MIME message and sends via Gmail (only with `--send`).
5. **Track** — appends a row to `output/sent_tracker.csv`.

Re-running is idempotent: only contacts without a successful tracker row are reprocessed.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS/Linux
pip install -e .
```

Configuration comes from `.env` (copy `.env.example`):

```
ANTHROPIC_API_KEY=sk-ant-...
```

Paths and `MODEL` have defaults in `src/cold_mail_workflow/config.py` and can be overridden via env.

### Gmail credentials

1. Create an OAuth **Desktop** client in Google Cloud, enable the Gmail API.
2. Download the client secret to `credentials/credentials.json`.
3. The first `--send` run opens a browser for consent and caches `credentials/token.json`.

Only the `gmail.send` scope is requested.

## Inputs

**`cv.md`** — your CV in markdown. The single source of truth: generated emails may only cite
skills, experience, and projects that appear here.

**Contacts file** — `.csv` **or** `.xlsx`, auto-detected by extension. Row 1 is a header;
columns are matched by name (case-insensitive) with aliases, so a raw recruiter export (e.g.
Apollo) works without reshaping. Mapped fields:

| field             | source columns (any of)                                   | required |
|-------------------|-----------------------------------------------------------|----------|
| company           | `company`, `company name`, `company name for emails`      | yes      |
| recruiter_email   | `recruiter_email`, `email`, `primary email`               | yes      |
| recruiter_name    | `recruiter_name` / `name`, or `first name` + `last name`  | no       |
| title             | `title`, `contact title`                                  | no²      |
| role              | `role`, `position`, `target role`                         | no¹      |
| job_url           | `job_url`, `job url`, `posting`                           | no       |
| notes             | `notes`, else `industry`                                  | no       |

Rows missing **company** or **email** are skipped with a warning. Recruiter names are
sanitized (obfuscated email fragments like `Phha{At}Ebaycom` are stripped); when no usable
name remains the email opens with "Hi there".

² **`title` is the *recipient's* job title**, and it drives the email's technical depth.
A recruiter / talent / sourcer / HR title (the default) gets an outcome-led, keyword-matchable
email with no deep jargon. A technical title — engineering manager, tech lead, director/VP of
engineering, senior/staff/principal engineer, architect, CTO — gets a deeper, engineer-to-engineer
email that references real architecture and trade-offs (still grounded in the CV). "Technical
Recruiter" is treated as non-technical. Classification lives in `generate._is_technical_audience`.

¹ These are generic recruiter outreach lists with no specific posting, so **role defaults to
`Software Engineer`** (set `DEFAULT_ROLE` in `.env` or pass `--role`). The email pitches your
profile to the recruiter / their company rather than a single job ad. `job_url` is typically
empty and simply omitted from the body.

## Usage

```bash
# dry run (default) — generates and prints emails, sends nothing
python -m cold_mail_workflow

# send for real
python -m cold_mail_workflow --send

# process at most N contacts
python -m cold_mail_workflow --limit 5

# filter to one company
python -m cold_mail_workflow --company "Stripe"

# point at a specific contacts file (.csv or .xlsx)
python -m cold_mail_workflow --contacts data/contact.csv

# override the target role used in the pitch + dedup key
python -m cold_mail_workflow --role "Backend Engineer"

# smoke-test a single live send first
python -m cold_mail_workflow --send --limit 1
```

### Single-record mode (ad-hoc, no CSV)

Pass `--to` to run the workflow for one contact typed on the command line, ignoring the
contacts files entirely. `--company`, `--recruiter-name`, `--title`, and `--role` describe that
one record. The tracker dedup still applies (an already-sent contact is skipped), and `--send`
is still required to actually send.

```bash
# dry-run one ad-hoc email
python -m cold_mail_workflow --to jane.doe@datadoghq.com --company "Datadog" \
    --recruiter-name "Jane Doe" --title "Engineering Manager"

# send it for real
python -m cold_mail_workflow --send --to jane.doe@datadoghq.com --company "Datadog" \
    --recruiter-name "Jane Doe" --title "Engineering Manager"
```

`--title` drives technical depth here too: an engineering-manager / tech-lead title gets the
deeper engineer-to-engineer email; omit it (or a recruiter title) for the recruiter-friendly one.

## Safety

- Dry-run is the default; real sending requires `--send`.
- The dedup check runs before generation and before sending — never sends a duplicate.
- Sends are rate-limited (`SEND_DELAY_SECONDS`) and capped per run (`MAX_SENDS_PER_RUN`).
- Generated content is grounded in `cv.md`; the prompt forbids fabricating experience or numbers.
- `.env`, `credentials/`, and `output/` are gitignored.
