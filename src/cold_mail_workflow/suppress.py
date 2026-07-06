import csv
import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from .config import SUPPRESS_PATH

logger = logging.getLogger(__name__)

HEADER = ["timestamp", "email", "reason"]


def normalize(email: str) -> str:
    return (email or "").strip().lower()


def load(path: Path = SUPPRESS_PATH) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", newline="", encoding="utf-8") as f:
        return {normalize(row["email"]) for row in csv.DictReader(f) if row.get("email")}


def is_suppressed(email: str, path: Path = SUPPRESS_PATH) -> bool:
    return normalize(email) in load(path)


def is_any_suppressed(emails: Iterable[str], path: Path = SUPPRESS_PATH) -> bool:
    blocked = load(path)
    return any(normalize(e) in blocked for e in emails)


def add(emails: Iterable[str], reason: str = "", path: Path = SUPPRESS_PATH) -> list[str]:
    existing = load(path)
    to_add: list[str] = []
    seen: set[str] = set()
    for raw in emails:
        norm = normalize(raw)
        if norm and "@" in norm and norm not in existing and norm not in seen:
            seen.add(norm)
            to_add.append(raw.strip())

    if not to_add:
        return []

    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    ts = datetime.now(timezone.utc).isoformat()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(HEADER)
        for addr in to_add:
            writer.writerow([ts, addr, reason])

    logger.info("Suppressed %d address(es): %s", len(to_add), ", ".join(to_add))
    return to_add
