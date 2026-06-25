import json
import logging
import re

from anthropic import Anthropic

from .config import ANTHROPIC_API_KEY, MAX_TOKENS, MODEL
from .models import Contact, GeneratedEmail

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are writing a short, personalized cold email from a software engineer to a recruiter, expressing interest in software engineering opportunities at the recruiter's company (or roles they staff for).

Hard rules:
- Ground every claim in the CV provided. You may ONLY cite skills, experience, projects, employers, metrics, and numbers that appear verbatim or in clear substance in the CV.
- NEVER fabricate experience, employers, metrics, or numbers. If the CV does not support a claim, do not make it.
- Connect the candidate's actual skills to the SPECIFIC company and target role on the record. Relevance to this exact company is the point; do not write a generic template. If the company is a staffing/recruiting firm, frame it as a strong candidate they could place.
- The candidate's resume (PDF) IS attached to this email. Reference it naturally once (e.g. "I've attached my resume" or "my resume is attached for the full details"). Do NOT offer to "send" or "share" a resume as if it were not already attached.
- The ask is a brief reply or a short call; the recruiter's name (if given) goes in the greeting, else use "Hi there".
- Keep the email roughly 120-160 words, with a clear ask and a real subject line.
- Be concise and professional. No markdown, no placeholders like [Name].

Voice: write like a real, confident engineer typing a quick note, not like AI. This is critical:
- NEVER use em dashes or en dashes (the long dash characters) and NEVER use a double hyphen. Use commas, periods, or parentheses instead. Normal single hyphens inside words (real-time, high-throughput, 15-minute, sub-second) are fine. Never use tab characters.
- Avoid AI-tell phrases and openings. Do NOT use: "I came across", "I wanted to reach out", "I'm reaching out", "drawn to", "resonates", "excited about / genuinely excited", "passionate about", "a natural fit", "exactly the kind of ... I", "delve", "leverage", "spearheaded", "in today's fast-paced", "I'd love to" (at most once, ideally not at all), "feel free to". Start emails differently from each other, not all with the same template.
- Plain, direct, specific sentences. Vary sentence length and rhythm so it reads like a person, not a generated paragraph. Contractions are good. Cut filler and hype adjectives ("cutting-edge", "world-class", "robust", "passionate"); let the concrete results carry the weight.
- Sound like a strong engineer who is matter-of-fact about real wins, confident without bragging. State what you built and the result plainly. Do not flatter the company or gush.
- Vary the closing ask naturally (a short reply, a quick call, worth a chat) instead of repeating one fixed sentence.

Audience and technical level — ADAPT to the recipient. The user message gives the recipient's "Title" and an "Audience" flag (NON-TECHNICAL or TECHNICAL).

Common to both: foreground the candidate's concrete software-engineering SKILLS as shown by real work (backend APIs and services, distributed systems, data pipelines, AI/agentic systems, performance optimization, leading delivery), tie each to a real achievement and its impact, and present them as a multi-language engineer — surface Java and C++ alongside Python as core languages (grounded in the CV: Java at TCS/Flink work, C++ in the systems/networking project), not just a Python specialist.

If Audience is NON-TECHNICAL (recruiter, talent, sourcer, HR — the default):
- Lead with impact and outcomes (the numbers), then name the demonstrated skill. Prefer "scaled the browser-automation cluster 4x and cut compute cost ~60%" over the low-level mechanism.
- Keep recognizable, resume-matchable technology keywords (Python, Java, C++, FastAPI, Kafka, Spark, Kubernetes, distributed systems, LLM/agentic AI) so it's easy to match to a job description.
- DO NOT use dense low-level implementation jargon a non-technical reader cannot parse (avoid terms like "hierarchical FSM", "CDP proxy with TCP multiplexing", "KD-tree point-to-polygon"). Translate such work into plain capability + outcome.
- Aim for 2-4 concrete, skill-revealing accomplishments rather than one deep architecture description.

If Audience is TECHNICAL (engineering manager, tech lead, director/head/VP of engineering, senior/staff/principal engineer, architect, CTO):
- You may go deeper and speak engineer-to-engineer. Reference concrete architecture, design decisions, and mechanisms where they demonstrate real depth (e.g. hierarchical FSM orchestration of LLM agents, a CDP proxy with TCP command multiplexing, Spark Structured Streaming with exactly-once semantics, KD-tree point-to-polygon spatial lookups, circuit breakers and bounded-retry recovery).
- Still LEAD with the impact, keep it tight, and ground every technical detail in the CV — depth, not a brain-dump. Show judgment about trade-offs, not just a list of buzzwords.
- It is fine to address them as a peer who will evaluate engineering substance, while still being respectful of their time with a clear, low-friction ask.

Return ONLY a single JSON object, no prose, no code fences, with exactly this shape:
{
  "subject": "...",
  "body": "...",
  "metadata": {
    "matched_skills": ["...", "..."],
    "company_hook": "one line on why this company/role",
    "tone": "concise|warm|formal",
    "personalization_notes": "..."
  }
}"""


FOLLOWUP_SYSTEM_PROMPT = """You are writing a SHORT follow-up email from a software engineer to a recruiter they already emailed once about software engineering opportunities at the recruiter's company (or roles they staff for). The recruiter has not replied. This is a polite second touch, not a first introduction.

Hard rules:
- This IS a follow-up to a previous email. Acknowledge that briefly and naturally (e.g. "following up on my note from last week", "circling back on the email I sent"). Do NOT pretend they replied, and do NOT re-pitch the whole thing.
- Keep it very short: roughly 50 to 90 words, one short paragraph (two at most). A follow-up is a nudge, not a second resume.
- Ground every claim in the CV provided. You may ONLY cite skills, experience, projects, employers, metrics, and numbers that appear verbatim or in clear substance in the CV. NEVER fabricate experience, employers, metrics, or numbers.
- Add ONE concrete, CV-grounded reason worth a second look, tied to the SPECIFIC company and target role, instead of restating everything from the first email.
- The candidate's resume (PDF) is attached again. You may reference it once, lightly. Do NOT offer to "send" or "share" a resume as if it were not attached.
- End with a low-friction ask: a quick reply, whether they're the right person to talk to, or a short call. Be respectful of their time.
- The recruiter's name (if given) goes in the greeting, else use "Hi there". No markdown, no placeholders like [Name].

Voice: write like a real, confident engineer typing a quick note, not like AI.
- NEVER use em dashes or en dashes (the long dash characters) and NEVER use a double hyphen. Use commas, periods, or parentheses instead. Normal single hyphens inside words (real-time, high-throughput) are fine. Never use tab characters.
- Avoid AI-tell phrases and openings. Do NOT use: "I came across", "I wanted to reach out", "I'm reaching out", "drawn to", "resonates", "excited about / genuinely excited", "passionate about", "a natural fit", "delve", "leverage", "spearheaded", "in today's fast-paced", "feel free to". Do not start with "I just wanted to".
- Plain, direct, specific sentences. Vary rhythm. Contractions are good. Cut filler and hype adjectives. Be matter-of-fact about real wins.

Return ONLY a single JSON object, no prose, no code fences, with exactly this shape:
{
  "subject": "...",
  "body": "...",
  "metadata": {
    "matched_skills": ["...", "..."],
    "company_hook": "one line on why this company/role",
    "tone": "concise|warm|formal",
    "personalization_notes": "..."
  }
}"""


NONTECH_TITLE_PATTERNS = ("recruit", "talent", "sourc", "human resources", "people ops", "staffing", "hr")
TECH_TITLE_PATTERNS = (
    "engineering manager", "eng manager", "engineering lead", "tech lead", "technical lead",
    "team lead", "lead engineer", "director of engineering", "engineering director",
    "head of engineering", "vp of engineering", "vp engineering", "cto", "chief technology",
    "principal engineer", "staff engineer", "senior engineer", "software engineer", "developer",
    "architect", "engineering",
)


def _is_technical_audience(title: str) -> bool:
    t = title.lower()
    if not t:
        return False
    if any(p in t for p in NONTECH_TITLE_PATTERNS):
        return False
    return any(p in t for p in TECH_TITLE_PATTERNS)


def _build_user_prompt(contact: Contact, cv_text: str, followup: bool = False, prior_subject: str = "") -> str:
    greeting = contact.recruiter_name or "(none — use 'Hi there')"
    audience = "TECHNICAL" if _is_technical_audience(contact.title) else "NON-TECHNICAL"
    lines = [
        "=== CV (source of truth) ===",
        cv_text,
        "",
        "=== Target ===",
        f"Company: {contact.company}",
        f"Target role: {contact.role}",
        f"Recipient name: {greeting}",
        f"Recipient title: {contact.title or '(unknown)'}",
        f"Audience: {audience}",
    ]
    if contact.job_url:
        lines.append(f"Job URL: {contact.job_url}")
    if contact.notes:
        lines.append(f"Notes/hints: {contact.notes}")
    lines.append("")
    if followup:
        if prior_subject:
            lines.append(f"Subject of the first email you already sent: {prior_subject}")
        lines.append("Write the SHORT follow-up email now as the JSON object specified.")
    else:
        lines.append("Write the cold email now as the JSON object specified.")
    return "\n".join(lines)


_DASH = re.compile(r"[ \t]*(?:--+|[‒–—―])[ \t]*")


def _humanize(text: str) -> str:
    text = text.replace("\t", " ")
    text = _DASH.sub(", ", text)
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r",[ \t]*,+", ", ", text)
    text = re.sub(r"([.;:!?])[ ]*,[ ]*", r"\1 ", text)
    text = re.sub(r",[ ]*([.;:!?])", r"\1", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"[ ,]+$", "", text)
    return text.strip()


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def compose(contact: Contact, cv_text: str, followup: bool = False, prior_subject: str = "") -> GeneratedEmail:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=FOLLOWUP_SYSTEM_PROMPT if followup else SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(contact, cv_text, followup, prior_subject)}],
    )

    raw = "".join(block.text for block in response.content if block.type == "text")
    data = _extract_json(raw)

    subject = _humanize(str(data.get("subject", "")))
    body = _humanize(str(data.get("body", "")))
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    if not subject or not body:
        raise ValueError(f"Generated email missing subject or body for {contact.company}/{contact.role}")

    return GeneratedEmail(subject=subject, body=body, metadata=metadata)
