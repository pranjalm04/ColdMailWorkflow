import base64
import logging
import mimetypes
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import CREDENTIALS_PATH, GMAIL_SCOPES, TOKEN_PATH
from .models import GeneratedEmail

logger = logging.getLogger(__name__)


def _load_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), GMAIL_SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(f"Google OAuth client secret not found: {CREDENTIALS_PATH}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), GMAIL_SCOPES)
        creds = flow.run_local_server(port=0)

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _build_service():
    return build("gmail", "v1", credentials=_load_credentials())


def _attach(message: MIMEMultipart, path: Path) -> None:
    ctype, _ = mimetypes.guess_type(path.name)
    maintype, subtype = (ctype.split("/", 1) if ctype else ("application", "octet-stream"))
    part = MIMEBase(maintype, subtype)
    part.set_payload(path.read_bytes())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=path.name)
    message.attach(part)


def _encode(to: str, email: GeneratedEmail, attachment: Path | None = None) -> dict:
    if attachment is None:
        message = MIMEText(email.body)
    else:
        message = MIMEMultipart()
        message.attach(MIMEText(email.body))
        _attach(message, attachment)
    message["to"] = to
    message["subject"] = email.subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": raw}


def send(
    to: str,
    email: GeneratedEmail,
    service=None,
    attachment: Path | None = None,
    thread_id: str | None = None,
) -> str:
    service = service or _build_service()
    body = _encode(to, email, attachment)
    if thread_id:
        body["threadId"] = thread_id
    result = service.users().messages().send(userId="me", body=body).execute()
    message_id = result.get("id", "")
    logger.info("Sent message to %s (id=%s, thread=%s)", to, message_id, result.get("threadId", ""))
    return message_id


def build_service():
    return _build_service()
