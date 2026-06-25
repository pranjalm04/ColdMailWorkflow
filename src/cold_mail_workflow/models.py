from dataclasses import dataclass, field


@dataclass(frozen=True)
class Contact:
    company: str
    role: str
    recruiter_email: str
    recruiter_name: str = ""
    title: str = ""
    job_url: str = ""
    notes: str = ""
    all_emails: tuple[str, ...] = ()

    @property
    def recipients(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in (self.recruiter_email, *self.all_emails):
            addr = (raw or "").strip()
            key = addr.lower()
            if addr and key not in seen:
                seen.add(key)
                out.append(addr)
        return out


@dataclass
class GeneratedEmail:
    subject: str
    body: str
    metadata: dict = field(default_factory=dict)


@dataclass
class TrackerRecord:
    timestamp: str
    dedup_key: str
    recruiter_email: str
    company: str
    role: str
    subject: str
    gmail_message_id: str
    status: str


@dataclass(frozen=True)
class FollowupTarget:
    contact: Contact
    dedup_key: str
    thread_id: str
    prior_subject: str
