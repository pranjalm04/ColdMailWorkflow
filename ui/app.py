import base64
import hashlib
import os
import sys
from datetime import datetime, timezone

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import voice
from cold_mail_workflow import config, generate, ingest, mailer, pipeline, tracker
from cold_mail_workflow.models import Contact, TrackerRecord

st.set_page_config(page_title="ColdMailWorkflow", page_icon="✉️", layout="wide")

_MIC = components.declare_component(
    "big_mic", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic_component")
)


def load_cv():
    return config.CV_PATH.read_text(encoding="utf-8")


def load_contacts():
    if not config.CONTACTS_PATH.exists():
        return []
    return ingest.read_contacts(config.CONTACTS_PATH, config.DEFAULT_ROLE)


def dedup_filter(contacts):
    seen = set()
    out = []
    for c in contacts:
        key = tracker.dedup_key(c)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def send_single(contact, email):
    key = tracker.dedup_key(contact)
    if tracker.already_sent(key):
        return "skipped", None
    if not config.RESUME_PATH.exists():
        raise FileNotFoundError(f"Resume not found: {config.RESUME_PATH}")
    service = mailer.build_service()
    msg_id = mailer.send(contact.recruiter_email, email, service=service, attachment=config.RESUME_PATH)
    tracker.append(
        TrackerRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            dedup_key=key,
            recruiter_email=contact.recruiter_email,
            company=contact.company,
            role=contact.role,
            subject=email.subject,
            gmail_message_id=msg_id,
            status="sent",
        )
    )
    return "sent", msg_id


def current_contact():
    return Contact(
        company=st.session_state.f_company.strip(),
        role=st.session_state.f_role.strip() or config.DEFAULT_ROLE,
        recruiter_email=st.session_state.f_to.strip(),
        recruiter_name=st.session_state.f_name.strip(),
        title=st.session_state.f_title.strip(),
        notes=st.session_state.f_notes.strip(),
    )


FIELD_DEFAULTS = {
    "f_to": "",
    "f_name": "",
    "f_company": "",
    "f_role": config.DEFAULT_ROLE,
    "f_title": "",
    "f_notes": "",
}
for _k, _v in FIELD_DEFAULTS.items():
    st.session_state.setdefault(_k, _v)


def reset_fields():
    for k, v in FIELD_DEFAULTS.items():
        st.session_state[k] = v
    st.session_state.pop("preview_email", None)
    st.session_state.pop("preview_contact", None)
    st.session_state.pop("voice_transcript", None)


def apply_voice_fields(fields):
    reset_fields()
    for fk, val in fields.items():
        if val:
            st.session_state[fk] = val


st.title("✉️ ColdMailWorkflow")

tab_compose, tab_batch, tab_tracker, tab_status = st.tabs(["Compose", "Batch", "Tracker", "Status"])

with tab_compose:
    mic = _MIC(silence_ms=1200, default=None, key="big_mic")
    if mic and mic.get("id") != st.session_state.get("mic_last_id"):
        st.session_state["mic_last_id"] = mic["id"]
        try:
            audio_bytes = base64.b64decode(mic["audio"])
            with st.spinner("Transcribing…"):
                transcript = voice.transcribe(audio_bytes)
            with st.spinner("Extracting fields…"):
                fields = voice.extract_fields(transcript, load_contacts())
            apply_voice_fields(fields)
            st.session_state["voice_transcript"] = transcript
            st.rerun()
        except Exception as exc:
            st.error(f"Voice failed: {exc}")

    with st.expander("Prefer push-to-talk?"):
        audio = st.audio_input("Record — it processes when you stop")
        if audio is not None:
            data = audio.getvalue()
            digest = hashlib.sha256(data).hexdigest()
            if st.session_state.get("voice_hash") != digest:
                try:
                    with st.spinner("Transcribing…"):
                        transcript = voice.transcribe(data)
                    with st.spinner("Extracting fields…"):
                        fields = voice.extract_fields(transcript, load_contacts())
                    apply_voice_fields(fields)
                    st.session_state["voice_transcript"] = transcript
                    st.session_state["voice_hash"] = digest
                    st.rerun()
                except Exception as exc:
                    st.error(f"Voice failed: {exc}")

    if st.session_state.get("voice_transcript"):
        st.caption(f"Heard: “{st.session_state['voice_transcript']}”")

    st.subheader("Compose")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Recruiter email *", key="f_to")
        st.text_input("Recruiter name", key="f_name")
        st.text_input("Company", key="f_company")
    with col2:
        st.text_input("Target role", key="f_role")
        st.text_input("Recipient title (e.g. Engineering Manager)", key="f_title")
    st.text_area("Notes / job posting", key="f_notes", height=120)

    pcol1, pcol2 = st.columns([3, 1])
    do_preview = pcol1.button("Preview", type="primary")
    pcol2.button("Clear", on_click=reset_fields)
    if do_preview:
        if "@" not in st.session_state.f_to:
            st.error("Enter a valid recruiter email.")
        else:
            contact = current_contact()
            try:
                with st.spinner("Generating…"):
                    email = generate.compose(contact, load_cv())
                st.session_state["preview_contact"] = contact
                st.session_state["preview_email"] = email
            except Exception as exc:
                st.error(f"Generation failed: {exc}")

    email = st.session_state.get("preview_email")
    contact = st.session_state.get("preview_contact")
    if email and contact and contact != current_contact():
        st.info("You've edited the form since this preview. Click **Preview** to regenerate before sending.")
    elif email and contact:
        if tracker.already_sent(tracker.dedup_key(contact)):
            st.warning("This (company, role, email) was already sent — sending will be skipped.")
        st.markdown(f"**Subject:** {email.subject}")
        st.text_area("Body", email.body, height=280, disabled=True)
        st.caption(f"📎 {config.RESUME_PATH.name} will be attached  •  to: {contact.recruiter_email}")
        confirm = st.checkbox("I confirm sending this email")
        if st.button("Send previewed email", disabled=not confirm):
            try:
                with st.spinner("Sending…"):
                    status, msg_id = send_single(contact, email)
                if status == "sent":
                    st.success(f"Sent to {contact.recruiter_email}  (id {msg_id})")
                    st.session_state.pop("preview_email", None)
                    st.session_state.pop("preview_contact", None)
                else:
                    st.warning("Already sent — skipped.")
            except Exception as exc:
                st.error(f"Send failed: {exc}")

with tab_batch:
    st.subheader("Batch")
    contacts = dedup_filter(load_contacts())
    sent_keys = tracker.sent_keys()
    new = [c for c in contacts if tracker.dedup_key(c) not in sent_keys]
    st.write(
        f"Loaded **{len(contacts)}** unique contacts  •  **{len(new)}** new  •  "
        f"**{len(contacts) - len(new)}** already sent"
    )

    company = st.text_input("Filter by company (optional)")
    new_filtered = [
        c for c in new if (not company) or company.strip().lower() == c.company.strip().lower()
    ]

    n_preview = st.number_input(
        "Preview how many drafts", min_value=1, max_value=25, value=min(3, max(1, len(new_filtered)))
    )
    if st.button("Preview drafts (no send)"):
        cv_text = load_cv()
        if not new_filtered:
            st.info("Nothing new to preview.")
        for c in new_filtered[: int(n_preview)]:
            try:
                with st.spinner(f"Generating for {c.company}…"):
                    draft = generate.compose(c, cv_text)
                with st.expander(f"{c.company} — {c.recruiter_email}"):
                    st.markdown(f"**Subject:** {draft.subject}")
                    st.text(draft.body)
            except Exception as exc:
                st.error(f"{c.company}: {exc}")

    st.divider()
    limit = st.number_input("Send at most N (0 = all new)", min_value=0, value=0)
    confirm_b = st.checkbox(f"I confirm sending to {len(new_filtered)} recruiter(s)")
    if st.button("Send batch", disabled=not confirm_b or not new_filtered):
        kwargs = {"send": True}
        if company.strip():
            kwargs["company"] = company.strip()
        if int(limit) > 0:
            kwargs["limit"] = int(limit)
        try:
            with st.spinner("Sending batch… (this can take a few minutes)"):
                stats = pipeline.run(**kwargs)
            st.success(f"Done — sent {stats.sent}, skipped {stats.skipped}, failed {stats.failed}")
            if stats.errors:
                st.error("\n".join(stats.errors))
        except Exception as exc:
            st.error(f"Batch failed: {exc}")

with tab_tracker:
    st.subheader("Sent tracker")
    rows = tracker.load()
    if not rows:
        st.info("No sends recorded yet.")
    else:
        st.write(f"{sum(1 for r in rows if r.get('status') == 'sent')} sent")
        st.dataframe(rows, width="stretch")

with tab_status:
    st.subheader("Status")
    all_contacts = dedup_filter(load_contacts())
    sent_keys = tracker.sent_keys()
    c1, c2, c3 = st.columns(3)
    c1.metric("Contacts loaded", len(all_contacts))
    c2.metric("Sent", len(sent_keys))
    c3.metric("Remaining", len([c for c in all_contacts if tracker.dedup_key(c) not in sent_keys]))
    st.write(f"**Model:** `{config.MODEL}`  •  **Default role:** {config.DEFAULT_ROLE}")
    st.write("**Files & auth**")
    st.write(f"- CV: `{config.CV_PATH}` {'✅' if config.CV_PATH.exists() else '❌'}")
    st.write(f"- Resume: `{config.RESUME_PATH}` {'✅' if config.RESUME_PATH.exists() else '❌'}")
    st.write(f"- Contacts: `{config.CONTACTS_PATH}` {'✅' if config.CONTACTS_PATH.exists() else '❌'}")
    st.write(f"- Anthropic API key: {'✅ set' if config.ANTHROPIC_API_KEY else '❌ missing'}")
    st.write(
        f"- Gmail token: {'✅ cached' if config.TOKEN_PATH.exists() else '⚠️ not yet — first send opens a browser'}"
    )
