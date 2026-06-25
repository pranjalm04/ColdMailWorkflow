# ColdMailWorkflow — Desktop UI

A local Streamlit interface over the `cold_mail_workflow` package. It imports the core
directly (no server) and reuses the same generation, dedup, rate-limit, resume-attach, and
tracker logic as the CLI. **The CLI core is unchanged** — this lives in `ui/` and depends on it.

## Setup

From the repo root:

```bash
pip install -e .                      # the core package (once)
pip install -r ui/requirements.txt    # streamlit + faster-whisper
```

`faster-whisper` downloads a small speech model on first voice use (~150 MB).

## Run

```bash
streamlit run ui/app.py
```

Opens in your browser at http://localhost:8501.

## Tabs

- **Compose** — type a single email (recruiter email, name, company, role, title, notes), or
  use **🎙 Voice**: record a request, it's transcribed locally (Whisper) and the fields are
  extracted (Claude) and filled in for you. The email address is resolved by matching the spoken
  name/company against your loaded contacts — it is never dictated, and it's left blank for you
  to confirm if there's no match. **Preview** generates the draft; **Send** is a separate,
  confirmed click that emails exactly what you previewed (resume attached).
- **Batch** — preview drafts for new contacts and send the whole batch (honors company filter and
  per-run limit). Already-sent contacts are skipped automatically.
- **Tracker** — view `output/sent_tracker.csv`.
- **Status** — model, files, counts, and Gmail auth state.

## Safety

Dry-run is the default — nothing sends without an explicit confirm + Send click. Dedup, the
rate-limit delay, the per-run cap, and resume attachment all carry over from the core unchanged.

## Voice / transcription

Transcription is **fully local** via `faster-whisper` (a fast CPU build of OpenAI Whisper) —
no audio leaves your machine. The default model is **`small.en`** (good accuracy). The first
recording downloads the model (~480 MB) once. Tune accuracy vs. speed with:

- `WHISPER_MODEL` — `tiny.en` / `base.en` (faster, less accurate), `small.en` (default),
  `medium.en` or `distil-medium.en` (most accurate, slower on CPU).

For the best accuracy *and* speed, a cloud STT (e.g. Groq's `whisper-large-v3`) is far ahead of
CPU Whisper — swap `voice.transcribe` to call it if you want that.

For an NVIDIA GPU, edit `voice.py` to `WhisperModel(..., device="cuda", compute_type="float16")`
for near-instant transcription.

## Notes

- **Voice needs `faster-whisper`, `streamlit-webrtc`, `streamlit-autorefresh`**; the typed tabs work without them.
- **First send** opens a browser for Gmail consent (same as the CLI) and caches `token.json`.
- The Compose **Send** emails the exact previewed draft. Batch **Send** regenerates drafts as it
  goes (generation is non-deterministic), so the batch preview is indicative, not byte-identical.
