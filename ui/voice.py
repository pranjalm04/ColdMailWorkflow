import io
import os

from anthropic import Anthropic

from cold_mail_workflow import config

_MODEL = None
_MODEL_NAME = os.getenv("WHISPER_MODEL", "small.en")

EXTRACT_TOOL = {
    "name": "fill_email_fields",
    "description": "Extract structured fields for a recruiter cold-email from the user's spoken request.",
    "input_schema": {
        "type": "object",
        "properties": {
            "company": {"type": "string", "description": "Company name, if mentioned"},
            "role": {"type": "string", "description": "Target role/title being applied to"},
            "recruiter_name": {"type": "string", "description": "Recruiter's name, if mentioned"},
            "title": {"type": "string", "description": "Recipient's own job title, if mentioned"},
            "notes": {"type": "string", "description": "Any job-posting text or extra hint"},
        },
        "required": [],
    },
}


def _get_model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel

        _MODEL = WhisperModel(_MODEL_NAME, device="cpu", compute_type="int8")
    return _MODEL


def _transcribe(audio) -> str:
    model = _get_model()
    language = None if _MODEL_NAME.endswith(".en") else "en"
    segments, _info = model.transcribe(
        audio,
        beam_size=5,
        language=language,
        vad_filter=True,
        condition_on_previous_text=False,
        temperature=0.0,
    )
    return " ".join(s.text for s in segments).strip()


def transcribe(audio_bytes: bytes) -> str:
    return _transcribe(io.BytesIO(audio_bytes))


def transcribe_pcm16(pcm: bytes) -> str:
    import numpy as np

    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    return _transcribe(audio)


def _resolve_email(name: str, company: str, contacts) -> str:
    name_n = (name or "").strip().lower()
    comp_n = (company or "").strip().lower()
    if name_n and comp_n:
        for c in contacts:
            if name_n in c.recruiter_name.lower() and comp_n in c.company.lower():
                return c.recruiter_email
    if name_n:
        for c in contacts:
            if name_n in c.recruiter_name.lower():
                return c.recruiter_email
    if comp_n:
        for c in contacts:
            if comp_n in c.company.lower():
                return c.recruiter_email
    return ""


def extract_fields(transcript: str, contacts) -> dict:
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.MODEL,
        max_tokens=512,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "fill_email_fields"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract the cold-email fields from this spoken request. "
                    "Leave a field empty if it is not mentioned. Never invent an email address.\n\n"
                    f"Request: {transcript}"
                ),
            }
        ],
    )

    data = {}
    for block in response.content:
        if block.type == "tool_use":
            data = block.input
            break

    name = (data.get("recruiter_name") or "").strip()
    company = (data.get("company") or "").strip()
    return {
        "f_company": company,
        "f_role": (data.get("role") or "").strip() or config.DEFAULT_ROLE,
        "f_name": name,
        "f_title": (data.get("title") or "").strip(),
        "f_notes": (data.get("notes") or "").strip(),
        "f_to": _resolve_email(name, company, contacts),
    }
