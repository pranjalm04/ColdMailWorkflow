# CLAUDE.md — ColdMailWorkflow

Project guidance for Claude Code working in the **ColdMailWorkflow** repository. Read this
before making changes.

## What this project is

A cold-emailing workflow for job outreach. It reads recruiter contacts from an Excel
file, generates a personalized cold email for each one using the Anthropic SDK (grounded
in the owner's CV), and sends them via the Gmail API. Every send is recorded in a tracker
file, and a contact is never emailed twice for the same role.

The owner is a software engineer reaching out to recruiters. The CV lives at `cv.md` and is
the single source of truth for skills, experience, and projects referenced in generated mail.

## Tech stack

- **Python 3.11+**
- **`anthropic`** — content + metadata generation
- **`openpyxl`** — read the contacts spreadsheet (pandas is fine too, but openpyxl keeps deps light)
- **`google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`** — Gmail send
- **`python-dotenv`** — config from `.env`
- **stdlib**: `csv`, `json`, `base64`, `email.mime`, `dataclasses`, `pathlib`, `logging`, `argparse`

Keep the dependency surface small. Don't add a framework (Celery, FastAPI, etc.) — this is a
batch CLI, not a service.

## Repository layout

```
ColdMailWorkflow/
├── CLAUDE.md
├── README.md
├── pyproject.toml              # deps + build config (single source of truth)
├── .env.example
├── cv.md                       # INPUT: owner's CV, markdown. Source of truth for skills.
├── data/
│   └── contacts.xlsx           # INPUT: recruiter records (see schema below)
├── output/
│   └── sent_tracker.csv        # STATE: append-only log of sends (see schema below)
├── credentials/                # gitignored
│   ├── credentials.json        # Google OAuth client secret (downloaded from GCP)
│   └── token.json              # cached OAuth token, created on first auth
└── src/cold_mail_workflow/
    ├── __init__.py
    ├── __main__.py             # CLI entrypoint (argparse)
    ├── config.py               # paths, env vars, model name, flags
    ├── models.py               # Contact, GeneratedEmail, TrackerRecord dataclasses
    ├── ingest.py               # read_contacts() -> list[Contact]
    ├── tracker.py              # load, dedup_key(), already_sent(), append()
    ├── suppress.py             # permanent do-not-contact list (by email): load/add/is_suppressed
    ├── generate.py             # Anthropic content + metadata generation
    ├── mailer.py               # Gmail auth + send
    └── pipeline.py             # orchestration: ingest -> dedup -> generate -> send -> track
```

When adding a module, follow this single-responsibility split. Orchestration logic belongs
only in `pipeline.py`; the other modules stay pure and independently testable.

## The pipeline (end to end)

`pipeline.run()` does the following, in order, for each contact:

1. **Ingest** — `ingest.read_contacts()` loads `data/contacts.xlsx` into `Contact` objects.
2. **Dedup check** — compute `dedup_key(contact)`; if `tracker.already_sent(key)`, **skip** and log. Never generate or send for an already-sent key.
3. **Generate** — `generate.compose(contact, cv_text)` calls the Anthropic API. The CV plus the contact's company and role go in as context. Returns a `GeneratedEmail` (subject, body, metadata).
4. **Send** — `mailer.send(...)` builds a MIME message and sends it via Gmail. **Only runs when `--send` is passed.** In dry-run (default), the email is printed/saved but not sent.
5. **Track** — on a successful send, append a `TrackerRecord` to `output/sent_tracker.csv`.

The pipeline must be **idempotent**: re-running after a partial/failed batch re-processes only
contacts that have no successful tracker row. Achieve this purely through the dedup check —
do not add separate state files.

## Data contracts

### Excel input — `data/contacts.xlsx`

Row 1 is a header. Expected columns (match by header name, case-insensitive, trimmed):

| column            | required | notes                                  |
|-------------------|----------|----------------------------------------|
| `company`         | yes      | used for dedup and personalization     |
| `role`            | yes      | the position being applied to          |
| `recruiter_name`  | no       | used for the greeting; fall back to "Hiring Team" |
| `recruiter_email` | yes      | recipient                              |
| `job_url`         | no       | referenced in the body if present      |
| `notes`           | no       | freeform hint passed to the generator  |

Skip rows missing any required field and log a warning. Do not invent values for missing fields.

### Tracker — `output/sent_tracker.csv`

Append-only CSV. Header:

```
timestamp,dedup_key,recruiter_email,company,role,subject,gmail_message_id,status
```

- `timestamp` — ISO 8601, UTC.
- `status` — `sent` | `failed` | `skipped`.
- Only rows with `status == sent` count for deduplication.
- Never rewrite or delete existing rows. Appends only.

### Suppression — `output/suppressed.csv`

Append-only do-not-contact list. Header: `timestamp,email,reason`. Keyed on the **email address**
(the person), not on `dedup_key`, so it blocks them across every company/role and matches any of
their `all_emails`. `pipeline.run` and `pipeline.run_followups` skip a contact if any of its
addresses is suppressed — before generation, with no tracker row written. Managed via
`--suppress` / `--list-suppressed`; logic lives in `suppress.py`.

### Dedup key

```python
def dedup_key(c: Contact) -> str:
    norm = lambda s: (s or "").strip().lower()
    return f"{norm(c.company)}::{norm(c.role)}::{norm(c.recruiter_email)}"
```

This means: one email per (company, role, recruiter). If the intended rule is "one email per
role regardless of recruiter," drop the email component — but keep the key definition in **one
place** (`tracker.dedup_key`) so the rule is changed in exactly one spot.

## Anthropic SDK usage (`generate.py`)

- Default model: **`claude-haiku-4-5-20251001`** — fast and low cost, right for a high-volume
  mailing batch. For higher quality on a small high-stakes batch, the model is configurable
  via `config.MODEL` (e.g. `claude-sonnet-4-6`, `claude-opus-4-8`, or `claude-fable-5` for the most capable).
- The API key comes from the `ANTHROPIC_API_KEY` env var; never hardcode it.
- The generator produces **content and metadata together** as structured JSON. Prompt the model
  to return *only* a JSON object, then parse it safely (strip code fences, `json.loads`,
  fall back gracefully on parse failure):

  ```json
  {
    "subject": "...",
    "body": "...",
    "metadata": {
      "matched_skills": ["...", "..."],
      "company_hook": "one line on why this company/role",
      "tone": "concise|warm|formal",
      "personalization_notes": "..."
    }
  }
  ```

- The prompt must ground the email in `cv.md`: the model may only cite skills, experience, and
  projects that appear in the CV. **Do not let it fabricate experience, employers, metrics, or
  numbers.** State this constraint explicitly in the system prompt.
- The body must connect the owner's actual skills to the **specific company and role** on the
  record — that relevance is the whole point of the email, not a generic template.
- Keep emails short (roughly 120–160 words), with a clear ask and a real subject line.
- Set `max_tokens` modestly (e.g. 1024). One API call per contact.

## Gmail API usage (`mailer.py`)

- Scope: `https://www.googleapis.com/auth/gmail.send` (send-only; do not request broader scopes).
- OAuth client secret lives at `credentials/credentials.json`. On first run, the InstalledApp
  flow opens a browser for consent and caches `credentials/token.json`; subsequent runs refresh
  silently.
- Build the message with `email.mime`, base64url-encode it (`raw`), and call
  `users().messages().send(userId="me", body={"raw": ...})`.
- Return the Gmail `message id` on success so it lands in the tracker.
- Reference: https://developers.google.com/gmail/api/guides/sending
- **Sending is irreversible.** Treat `mailer.send` as the only place that performs a side effect,
  and gate it behind the `--send` flag (see safety rules).

## Configuration

All config in `config.py`, read from `.env` (see `.env.example`). Required:

```
ANTHROPIC_API_KEY=...
```

Paths (CV, contacts, tracker, credentials) and `MODEL` have sensible defaults in `config.py` and
can be overridden via env. Never commit `.env`, `credentials/`, or `output/`.

## Commands

```bash
# setup
python -m venv .venv && source .venv/bin/activate
pip install -e .            # installs the package + deps from pyproject.toml

# dry run (default) — generates and prints emails, sends nothing
python -m cold_mail_workflow

# send for real
python -m cold_mail_workflow --send

# useful flags
python -m cold_mail_workflow --limit 5            # process at most N contacts
python -m cold_mail_workflow --company "Acme"     # filter to one company
python -m cold_mail_workflow --send --limit 1     # smoke-test a single live send first
```

## Safety rules (do not weaken these)

- **Dry-run is the default.** Real sending happens only when `--send` is explicitly passed.
  Do not flip this default or make `--send` implicit.
- **Never send a duplicate.** The dedup check runs before generation and before sending. If in
  doubt, skip and log.
- **Rate-limit sends** — add a small delay between messages (e.g. 1–3s) and respect a
  configurable per-run cap. Don't blast the whole sheet in a tight loop.
- **Fabrication is a bug.** If generated content references anything not in `cv.md`, that's a
  defect — fix the prompt, don't ship it.
- **Secrets never touch the repo, logs, or generated content.** No API keys or tokens in code,
  commits, or printed output.
- When unsure whether an action is reversible (sending, overwriting the tracker), prefer the
  safe path and surface the question rather than guessing.

## Conventions

- Type hints on all public functions; small `@dataclass` models in `models.py`.
- `logging` over `print` for pipeline output (CLI may print a final summary).
- Pure functions in `ingest`/`tracker`/`generate`/`mailer`; side effects and ordering live in
  `pipeline`. This keeps each module unit-testable without network access.
- Fail loud on malformed input (bad rows, missing CV, missing credentials) with a clear message;
  fail soft on a single contact's generation/send error (log it, mark `failed`, continue the batch).