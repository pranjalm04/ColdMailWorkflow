import logging

import requests

from .config import APOLLO_API_KEY, APOLLO_MATCH_URL, APOLLO_SEARCH_URL, DEFAULT_ROLE
from .models import Contact

logger = logging.getLogger(__name__)

# Apollo OR-matches person_titles. Lead with explicitly technical recruiting titles,
# then broader recruiting/talent titles so we can fall back if a company has few of the former.
TECHNICAL_RECRUITER_TITLES = [
    "technical recruiter",
    "senior technical recruiter",
    "technical sourcer",
    "engineering recruiter",
    "technical talent partner",
    "technical talent acquisition",
]
GENERAL_RECRUITER_TITLES = [
    "recruiter",
    "talent acquisition",
    "technical sourcer",
    "sourcer",
    "talent partner",
]

_TECH_TOKENS = ("technical", "engineering", "engineer", "software", "developer")
_RECRUIT_TOKENS = ("recruit", "talent", "sourc")
_LOCKED_EMAIL_MARKER = "email_not_unlocked"

# Apollo bulk_match accepts at most 10 records per request.
_BULK_MATCH_MAX = 10


def _is_recruiter(title: str) -> bool:
    return any(tok in (title or "").lower() for tok in _RECRUIT_TOKENS)


def _is_technical_recruiter(title: str) -> bool:
    t = (title or "").lower()
    return _is_recruiter(t) and any(tok in t for tok in _TECH_TOKENS)


def _person_name(person: dict) -> str:
    name = (person.get("name") or "").strip()
    if name:
        return name
    return " ".join(p for p in (person.get("first_name"), person.get("last_name")) if p).strip()


def _best_email(person: dict) -> str:
    email = (person.get("email") or "").strip()
    if email and _LOCKED_EMAIL_MARKER not in email.lower():
        return email
    for pe in person.get("personal_emails") or []:
        if pe and pe.strip():
            return pe.strip()
    for ce in person.get("contact_emails") or []:
        addr = (ce or {}).get("email", "") if isinstance(ce, dict) else ""
        if addr and _LOCKED_EMAIL_MARKER not in addr.lower():
            return addr.strip()
    return ""


def _person_to_contact(person: dict, company: str, role: str) -> Contact:
    org = person.get("organization") or {}
    org_name = (org.get("name") if isinstance(org, dict) else None) or company
    return Contact(
        company=org_name,
        role=role,
        recruiter_email=_best_email(person),
        recruiter_name=_person_name(person),
        title=(person.get("title") or "").strip(),
        notes="",
    )


def _rank_people(people: list[dict], limit: int) -> list[dict]:
    technical: list[dict] = []
    general: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for person in people:
        title = person.get("title") or ""
        name = _person_name(person)
        if not name or not _is_recruiter(title):
            continue
        key = (name.lower(), title.lower())
        if key in seen:
            continue
        seen.add(key)
        (technical if _is_technical_recruiter(title) else general).append(person)

    return (technical + general)[:limit]


def _search_request(company: str, titles: list[str], per_page: int, page: int) -> dict:
    if not APOLLO_API_KEY:
        raise RuntimeError("APOLLO_API_KEY is not set")

    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": APOLLO_API_KEY,
    }
    payload = {
        "q_organization_name": company,
        "person_titles": titles,
        "page": page,
        "per_page": per_page,
    }
    response = requests.post(APOLLO_SEARCH_URL, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def _bulk_match_request(details: list[dict]) -> list[dict]:
    if not APOLLO_API_KEY:
        raise RuntimeError("APOLLO_API_KEY is not set")

    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": APOLLO_API_KEY,
    }
    payload = {"reveal_personal_emails": True, "details": details}
    response = requests.post(APOLLO_MATCH_URL, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data.get("matches") or []


def _match_detail(person: dict) -> dict:
    detail = {
        "first_name": person.get("first_name") or "",
        "last_name": person.get("last_name") or "",
        "name": _person_name(person),
        "organization_name": ((person.get("organization") or {}).get("name") or ""),
    }
    if person.get("id"):
        detail["id"] = person["id"]
    return detail


def unlock_emails(people: list[dict]) -> list[dict]:
    """Reveal emails for the given Apollo people via bulk match (consumes Apollo credits).

    Returns the same people, each updated in place with an unlocked 'email' when one is found.
    Best-effort: people without a match are returned unchanged.
    """
    if not people:
        return people

    unlocked_by_id: dict[str, str] = {}
    unlocked_by_name: dict[str, str] = {}

    for start in range(0, len(people), _BULK_MATCH_MAX):
        chunk = people[start : start + _BULK_MATCH_MAX]
        matches = _bulk_match_request([_match_detail(p) for p in chunk])
        for match in matches:
            if not isinstance(match, dict):
                continue
            email = _best_email(match)
            if not email:
                continue
            if match.get("id"):
                unlocked_by_id[match["id"]] = email
            name = _person_name(match)
            if name:
                unlocked_by_name[name.lower()] = email

    revealed = 0
    for person in people:
        email = unlocked_by_id.get(person.get("id")) or unlocked_by_name.get(_person_name(person).lower())
        if email:
            person["email"] = email
            revealed += 1
    logger.info("Unlocked %d/%d email(s) via Apollo bulk match", revealed, len(people))
    return people


def search_recruiters(
    company: str,
    limit: int = 10,
    role: str = DEFAULT_ROLE,
    per_page: int = 25,
    unlock: bool = False,
) -> list[Contact]:
    company = (company or "").strip()
    if not company:
        raise ValueError("company is required")

    titles = TECHNICAL_RECRUITER_TITLES + GENERAL_RECRUITER_TITLES
    data = _search_request(company, titles, per_page=max(per_page, limit), page=1)
    people = data.get("people") or []
    logger.info("Apollo returned %d people for %r", len(people), company)

    selected = _rank_people(people, limit)
    if unlock:
        selected = unlock_emails(selected)

    recruiters = [_person_to_contact(p, company, role) for p in selected]
    logger.info("Selected %d technical recruiter(s) for %r", len(recruiters), company)
    return recruiters
