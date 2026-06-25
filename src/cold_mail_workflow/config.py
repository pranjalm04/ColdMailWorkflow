import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]


def _path(env_var: str, default: str) -> Path:
    raw = os.getenv(env_var, default)
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = os.getenv("MODEL", "claude-sonnet-4-6")

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
APOLLO_SEARCH_URL = os.getenv("APOLLO_SEARCH_URL", "https://api.apollo.io/api/v1/mixed_people/search")
APOLLO_MATCH_URL = os.getenv("APOLLO_MATCH_URL", "https://api.apollo.io/api/v1/people/bulk_match")

DEFAULT_ROLE = os.getenv("DEFAULT_ROLE", "Software Engineer")

CV_PATH = _path("CV_PATH", "cv.md")
RESUME_PATH = _path("RESUME_PATH", "resume/Pranjal_Mestry_resume.pdf")
CONTACTS_PATH = _path("CONTACTS_PATH", "data")
TRACKER_PATH = _path("TRACKER_PATH", "output/sent_tracker.csv")
CREDENTIALS_PATH = _path("CREDENTIALS_PATH", "credentials/credentials.json")
TOKEN_PATH = _path("TOKEN_PATH", "credentials/token.json")

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

SEND_DELAY_SECONDS = float(os.getenv("SEND_DELAY_SECONDS", "2.0"))
MAX_SENDS_PER_RUN = int(os.getenv("MAX_SENDS_PER_RUN", "50"))

MAX_TOKENS = 1024
