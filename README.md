# Minute — Meeting Summarizer

Upload a meeting recording and get a **timestamped transcript**, an **executive summary with key decisions**, and a checklist of **action items** (owner + due date when the conversation mentioned them).

This project is a full-stack implementation of the *Meeting Summarizer* brief:

| Requirement | How it is implemented |
| --- | --- |
| Input: meeting audio files | Drag-and-drop or file picker (`mp3`, `wav`, `m4a`, `mp4`, `webm`, `ogg`, `flac`, …) |
| Output: transcript + summary + action items | Stored in SQLite and shown in the UI as Minutes / Transcript / Audio tabs |
| Frontend to upload audio & view summary | React + Vite app (`frontend/`) |
| ASR API integration | OpenAI Whisper (`whisper-1`) via the official Audio Transcriptions API |
| Backend to store & process data | FastAPI + SQLAlchemy + local audio files |
| LLM for summary generation | OpenAI Chat Completions (`gpt-4o-mini` by default) with a structured JSON prompt |

Without an OpenAI key the app still runs in **demo mode**: any uploaded file is processed with a realistic sample transcript and minutes so you can walk the full UI.

---

## Architecture

```
┌──────────────┐     POST /api/meetings      ┌──────────────────────────┐
│  React UI    │  ─────────────────────────► │  FastAPI backend         │
│  (Vite :5173)│  GET  /api/meetings/:id     │                          │
│              │  ◄──── poll until complete ─│  1. Save audio to disk   │
└──────────────┘                             │  2. Whisper ASR          │
                                             │  3. LLM minutes JSON     │
                                             │  4. SQLite persist       │
                                             └────────────┬─────────────┘
                                                          │
                                             ┌────────────▼─────────────┐
                                             │  OpenAI                  │
                                             │  • whisper-1 (ASR)       │
                                             │  • gpt-4o-mini (LLM)     │
                                             └──────────────────────────┘
```

Processing is asynchronous. The upload endpoint returns immediately with `status: queued`. A background worker thread then moves the meeting through:

`queued → transcribing → summarizing → completed` (or `failed`)

The frontend polls every 1.5–2 seconds while a meeting is in flight.

### Data model

| Table | Purpose |
| --- | --- |
| `meetings` | File metadata, duration, language, pipeline status |
| `transcripts` | Full text + JSON time-coded segments from Whisper |
| `summaries` | Overview, key decisions, topic labels |
| `action_items` | Task, owner, due date, done flag |

Audio bytes live on disk under `backend/uploads/`. Only the filename is stored in the database.

---

## Repository layout

```
unthinkable/
├── README.md
├── .gitignore
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── uploads/                 # gitignored recordings
│   └── app/
│       ├── main.py              # FastAPI app, CORS, table create
│       ├── config.py            # env settings
│       ├── database.py          # SQLAlchemy engine (SQLite)
│       ├── models.py
│       ├── schemas.py
│       ├── routers/meetings.py  # REST API
│       └── services/
│           ├── transcription.py # Whisper / demo ASR
│           ├── summarization.py # LLM prompt + JSON parse
│           └── pipeline.py      # background job
└── frontend/
    ├── package.json
    ├── vite.config.js           # proxies /api → :8000
    └── src/
        ├── App.jsx
        ├── api.js
        └── index.css
```

---

## Prerequisites

- **Python 3.11+** (developed against 3.13)
- **Node.js 18+** and npm
- An **OpenAI API key** for live transcription and summarization ([platform.openai.com/api-keys](https://platform.openai.com/api-keys))

  Whisper and Chat Completions are billed per OpenAI’s current rates. Demo mode needs no key.

---

## Quick start

Open two terminals from the project root.

### 1. Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env          # Windows
# cp .env.example .env          # macOS / Linux
```

Edit `backend/.env` and paste your key:

```env
OPENAI_API_KEY=sk-...
DEMO_MODE=false
```

Leave `OPENAI_API_KEY` empty (or set `DEMO_MODE=true`) to try the UI without calling OpenAI. A tiny silent clip is included at `samples/sample-meeting.wav` so you can exercise the upload flow immediately.

You can also paste a key in the sidebar **OpenAI API key** field and click **Save key**. The app verifies it with OpenAI, writes it to `backend/.env`, and switches off demo mode without a restart.

Start the API:

```bash
# from backend/, with the venv active
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` to the backend, so you do not need a separate `VITE_API_URL` in development.

---

## Using the app

1. Drop a meeting recording onto the upload panel (or click **Upload audio**).
2. Wait while the status chip moves through **Queued → Transcribing → Writing minutes → Ready**.
3. Open **Minutes** for the overview, key decisions, topics, and action-item checklist.
4. Open **Transcript** for the Whisper text with timestamps.
5. Open **Audio** to replay the original file.
6. Tick action items as you complete them. **Copy minutes** / **Copy transcript** put a shareable version on the clipboard.

Whisper’s hosted API currently caps a single request at **25 MB**. That limit is enforced on upload (`MAX_UPLOAD_MB`). For longer meetings, compress the file or split it before uploading (see *Going further*).

---

## API reference

Base URL in development: `http://127.0.0.1:8000`

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Service status, demo flag, whether an API key is saved |
| `POST` | `/api/settings/openai-key` | `{ "api_key": "sk-..." }` — verify, save, turn off demo mode |
| `DELETE` | `/api/settings/openai-key` | Remove the key and return to demo mode |
| `GET` | `/api/meetings` | Newest-first meeting list |
| `POST` | `/api/meetings` | Multipart upload field `file` — starts the pipeline |
| `GET` | `/api/meetings/{id}` | Full transcript, summary, and action items |
| `GET` | `/api/meetings/{id}/audio` | Stream the stored recording |
| `PATCH` | `/api/meetings/{id}/actions/{action_id}` | `{ "done": true }` |
| `DELETE` | `/api/meetings/{id}` | Remove row + audio file |

### Example upload (curl)

```bash
curl -X POST http://127.0.0.1:8000/api/meetings ^
  -F "file=@standup.mp3"
```

### Example meeting payload (trimmed)

```json
{
  "id": 1,
  "title": "Q3 product planning — beta freeze",
  "status": "completed",
  "transcript": {
    "full_text": "Alex: Thanks everyone...",
    "segments": [{ "start": 0, "end": 8.4, "text": "Thanks everyone..." }]
  },
  "summary": {
    "overview": "The team locked scope...",
    "key_decisions": ["Ship the product beta on September 12..."],
    "topics": ["Beta launch", "Scope freeze"]
  },
  "action_items": [
    { "id": 1, "task": "File the team-switcher scope cut in Linear", "owner": "Maya", "due": "today", "done": false }
  ]
}
```

---

## ASR and LLM details

### Speech-to-text (Whisper)

`backend/app/services/transcription.py` calls:

```python
client.audio.transcriptions.create(
    model="whisper-1",
    file=audio_file,
    response_format="verbose_json",
)
```

`verbose_json` returns language, duration, and **segment timestamps**, which the Transcript tab renders. Swap the model with `OPENAI_TRANSCRIBE_MODEL` (for example `gpt-4o-mini-transcribe`) if your account supports it.

The same module can be pointed at Azure OpenAI or a local Whisper server by changing the `OpenAI()` client `base_url` / `api_key` in one place.

### Summary prompt

`backend/app/services/summarization.py` uses Chat Completions with `response_format={"type": "json_object"}` and the assignment’s guidance:

> Summarize this meeting transcript into key decisions and action items.

The system prompt requires this JSON shape:

```json
{
  "title": "short meeting title, 5-10 words",
  "overview": "2-4 sentence executive summary",
  "key_decisions": ["only decisions that were actually agreed"],
  "action_items": [
    { "task": "specific, actionable task", "owner": "name or null", "due": "mentioned date or null" }
  ],
  "topics": ["short topic labels"]
}
```

Guardrails in the prompt:

- Do not invent agreement or facts that are not in the transcript.
- Action items must be verb + outcome.
- Owner and due date are `null` unless clearly stated.

Temperature is `0.2` so minutes stay conservative. Change the model with `OPENAI_SUMMARY_MODEL` (e.g. `gpt-4o` for harder multilingual meetings).

---

## Configuration

All settings live in `backend/.env` (see `.env.example`).

| Variable | Default | Meaning |
| --- | --- | --- |
| `OPENAI_API_KEY` | empty | Enables live Whisper + LLM. Empty → demo mode |
| `OPENAI_TRANSCRIBE_MODEL` | `whisper-1` | ASR model |
| `OPENAI_SUMMARY_MODEL` | `gpt-4o-mini` | Minutes model |
| `DEMO_MODE` | `false` | Force the sample pipeline even if a key is set |
| `MAX_UPLOAD_MB` | `25` | Matches the Whisper file-size cap |
| `DATABASE_URL` | `sqlite:///./meetings.db` | SQLAlchemy URL (`meetings.db` is created next to the backend folder) |
| `UPLOAD_DIR` | `uploads` | Audio storage directory |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Allowed browser origins |

---

## Demo mode

Demo mode is on when `DEMO_MODE=true` **or** the API key is blank.

Uploading any valid audio file still stores that file (so the Audio tab works), but transcription and summarization return a canned Q3 planning meeting: scope freeze, named owners, and due dates. A **Demo mode** chip appears in the sidebar so it is obvious you are not calling OpenAI.

This is intended for local UI review and for graders who do not want to spend API credits.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Frontend shows a network / health error | Start the backend on port 8000 first |
| `401` / `incorrect API key` after upload | Check `OPENAI_API_KEY` in `backend/.env`, then restart uvicorn |
| `413` file too large | Compress or split the recording; Whisper hosted API is 25 MB |
| Unsupported file type | Convert to `mp3` or `wav` |
| Meeting stuck on *Queued* | Look at the uvicorn console; failed jobs surface `error_message` on `GET /api/meetings/{id}` |
| CORS errors if the UI is not on :5173 | Add the origin to `CORS_ORIGINS` |

---

## Going further

Ideas that fit the same architecture:

- **Speaker diarization** (who said what) via a second model, then feed named turns into the LLM.
- **Chunking** for files over 25 MB: split on silence, transcribe in parallel, stitch segments.
- **Calendar / Slack export** of action items.
- **Postgres + object storage** instead of SQLite and local disk for multi-user deploys.
- **Azure Speech** or **Google Cloud Speech-to-Text** as alternate ASR backends behind the same `transcribe_audio()` interface.

---

## License

Built as a take-home / portfolio implementation of the Meeting Summarizer assignment. You are free to use and modify it.
"# Meeting-Summarizer" 
