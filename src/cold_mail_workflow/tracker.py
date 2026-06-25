import csv
import logging
from pathlib import Path

from .config import TRACKER_PATH
from .models import Contact, TrackerRecord

logger = logging.getLogger(__name__)

HEADER = [
    "timestamp",
    "dedup_key",
    "recruiter_email",
    "company",
    "role",
    "subject",
    "gmail_message_id",
    "status",
]


def dedup_key(c: Contact) -> str:
    norm = lambda s: (s or "").strip().lower()
    return f"{norm(c.company)}::{norm(c.role)}::{norm(c.recruiter_email)}"


def load(path: Path = TRACKER_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sent_keys(path: Path = TRACKER_PATH) -> set[str]:
    return {
        row["dedup_key"]
        for row in load(path)
        if row.get("status") == "sent"
    }


def already_sent(key: str, path: Path = TRACKER_PATH) -> bool:
    return key in sent_keys(path)


def followed_up_keys(path: Path = TRACKER_PATH) -> set[str]:
    return {
        row["dedup_key"]
        for row in load(path)
        if row.get("status") == "followup_sent"
    }


def already_followed_up(key: str, path: Path = TRACKER_PATH) -> bool:
    return key in followed_up_keys(path)


def sent_rows(path: Path = TRACKER_PATH) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for row in load(path):
        if row.get("status") != "sent":
            continue
        key = row.get("dedup_key", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def append(record: TrackerRecord, path: Path = TRACKER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(HEADER)
        writer.writerow(
            [
                record.timestamp,
                record.dedup_key,
                record.recruiter_email,
                record.company,
                record.role,
                record.subject,
                record.gmail_message_id,
                record.status,
            ]
        )
    logger.debug("Appended tracker row: %s -> %s", record.dedup_key, record.status)
