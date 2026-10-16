# WhyCI — Explain Why Your CI Failed

> **Stop guessing. Start fixing.**

WhyCI is a privacy-first CI failure diagnosis application. It reads your CI log file, redacts secrets, and uses a **deterministic Python engine** to rank the most likely root cause — with supporting evidence, exact line numbers, and actionable debugging steps. No LLM required. No credentials needed to run locally.

---

## What it does

- **Upload** any `.log` or `.txt` CI log file via drag-and-drop or file picker
- **Redacts** GitHub tokens, AWS keys, Bearer headers, passwords, and other credentials *before* analysis or display
- **Classifies** error and warning signals with configurable pattern rules
- **Clusters** nearby related failures into failure groups
- **Ranks** a likely root-cause candidate using a transparent deterministic scoring system
- **Identifies** possible cascading failures downstream of the root cause
- **Explains** why the candidate was selected, with original line numbers and supporting evidence
- **Suggests** concrete debugging steps per failure category
- **Exports** sanitized reports as JSON or Markdown
- Runs **5 bundled sample logs** for immediate demo without any credentials or internet access

---

## Architecture

```
WhyCI/
├── src/whyci/                   # Deterministic analysis engine (Python)
│   ├── __init__.py
│   ├── config.py                # Detection patterns, scoring rules, redaction rules
│   ├── github_actions.py        # Safe ZIP archive processor (Zip Slip protection)
│   ├── redactor.py              # Two-layer secret redaction
│   ├── main.py                  # CLI entry point (--log, --archive)
│   └── log_processor/
│       ├── __init__.py
│       ├── processor.py         # Log loading, line classification
│       ├── analyzer.py          # Clustering, scoring, root-cause selection
│       ├── evidence.py          # Evidence extraction and context windowing
│       └── redactor.py         # Phase-2 pattern-level redaction
│
├── backend/                     # FastAPI web API
│   ├── __init__.py
│   ├── main.py                  # App factory, CORS, static file serving
│   ├── service.py               # Adapter: ProcessingResult → API response
│   └── api/
│       ├── __init__.py
│       ├── routes.py            # Route handlers (/health, /api/samples, /api/analyze, /api/demo)
│       └── schemas.py           # Pydantic request/response models
│
├── frontend/                    # React + TypeScript + Vite + Tailwind CSS
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx              # Main app (state machine: idle/loading/result/error)
│   │   ├── api.ts               # Typed fetch client
│   │   ├── index.css            # Tailwind + global styles
│   │   └── components/
│   │       ├── DropZone.tsx     # Drag-and-drop file upload
│   │       ├── SampleSelector.tsx
│   │       ├── LogViewer.tsx    # Collapsible log table with search
│   │       └── AnalysisResult.tsx  # Results panel, export/copy
│   ├── dist/                    # Production build (served by FastAPI)
│   └── vite.config.ts
│
├── sample_logs/                 # Bundled CI failure examples
│   ├── example_failure.log      # npm auth test failure
│   ├── cascading_db_failure.log # Postgres connection refused → test cascade
│   ├── secret_redaction_failure.log  # Credential redaction demo
│   ├── python_dependency_failure.log # Missing pip package → ModuleNotFoundError
│   └── compilation_failure.log  # TypeScript type errors → build failure
│
├── tests/                       # pytest suite (88 tests)
│   ├── test_analyzer.py
│   ├── test_evidence.py
│   ├── test_github_actions.py
│   ├── test_log_processor.py
│   ├── test_redactor.py
│   └── test_api.py              # API integration tests (FastAPI TestClient)
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## Prerequisites

- **Python 3.11+** (tested on 3.12)
- **Node.js 18+** and **npm 9+** (for frontend)

---

## Installation

### 1. Python dependencies

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Frontend dependencies (one-time)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd frontend
npm install
npm run build
cd ..
```

```bash
cd frontend
npm install
npm run build
cd ..
```

---

## Run the application

### Web application (recommended)

```powershell
# Windows PowerShell — from project root
$env:PYTHONPATH = "src"
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
# macOS / Linux
PYTHONPATH=src uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** in your browser.

> The built frontend (`frontend/dist/`) is served automatically. If you edit the frontend, re-run `npm run build` in the `frontend/` directory.

### CLI (no web server required)

```powershell
$env:PYTHONPATH = "src"
python -m whyci.main --log sample_logs/cascading_db_failure.log
python -m whyci.main --log sample_logs/python_dependency_failure.log
python -m whyci.main --archive path/to/workflow_logs.zip
```

```bash
PYTHONPATH=src python -m whyci.main --log sample_logs/cascading_db_failure.log
```

Add `--no-redact` to disable redaction for offline debugging of non-sensitive logs (**unsafe** for real credentials).

---

## Run tests

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests -v
```

```bash
PYTHONPATH=src python -m pytest tests -v
```

**Expected result:** `88 passed` (64 engine tests + 24 API integration tests)

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Application health and version |
| `GET` | `/api/samples` | List bundled sample logs |
| `GET` | `/api/samples/{id}` | Get sample metadata |
| `GET` | `/api/demo/{id}` | Analyze a bundled sample |
| `POST` | `/api/analyze` | Upload and analyze a log file |

Interactive API docs: **http://localhost:8000/docs**

### Example: analyze a sample

```bash
curl http://localhost:8000/api/demo/cascading_db_failure | python -m json.tool
```

### Example: upload a log file

```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "file=@sample_logs/example_failure.log" | python -m json.tool
```

### Response schema (`AnalysisResponse`)

```json
{
  "status": "ok",
  "source_name": "cascading_db_failure.log",
  "total_lines": 23,
  "error_count": 11,
  "warning_count": 0,
  "failure_clusters": [
    { "start_line": 6, "end_line": 9, "lines": [...] }
  ],
  "root_cause": {
    "line_number": 7,
    "text": "Database connection refused at postgres:5432",
    "category": "infrastructure",
    "priority_score": 0.92,
    "score_reasons": ["\"connection refused\" matched a high-priority infrastructure rule", "..."],
    "explanation": "WhyCI identified a database connection failure as the most likely root-cause candidate."
  },
  "primary_evidence": [...],
  "supporting_evidence": [...],
  "cascading_failures": [...],
  "relevant_context": [...],
  "debugging_suggestions": ["Check that required services started successfully.", "..."],
  "redaction": { "applied": false, "replacement_count": 0, "matched_rules": [] },
  "analysis_notes": ["Scores are deterministic priority weights — not AI confidence..."]
}
```

---

## Environment configuration

Copy `.env.example` to `.env`. No environment variables are required to run the local MVP.

```bash
cp .env.example .env
```

Optional variables for future extensions:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Reserved for optional LLM explanation (not implemented in MVP) |
| `GITHUB_TOKEN` | Reserved for optional GitHub Actions API integration (not implemented in MVP) |

> Never commit `.env` to source control.

---

## Security and redaction

WhyCI applies a **two-layer deterministic redaction** pipeline before analysis or display:

**Detected and replaced with `[REDACTED]`:**
- GitHub personal access tokens (`ghp_`, `gho_`, `ghs_`, `ghu_`, `ghp_`, fine-grained `github_pat_`)
- AWS Access Key IDs (`AKIA…`)
- Slack tokens (`xox…`)
- Stripe keys (`sk_live_`, `rk_test_`, etc.)
- GitLab PATs (`glpat-…`)
- Hugging Face tokens (`hf_…`)
- NPM tokens (`npm_…`)
- JSON Web Tokens (JWT `eyJ…`)
- HTTP `Authorization: Bearer …` and `Proxy-Authorization` headers
- URL credentials (`https://user:password@host/`)
- PEM private key blocks (`-----BEGIN ... PRIVATE KEY-----`)
- Environment variable assignments: `PASSWORD=`, `API_KEY=`, `SECRET=`, `TOKEN=`, etc.

**Limitations:**
- Regex-based detection only — custom or obfuscated credentials may not be caught
- Cannot guarantee complete privacy
- The `--no-redact` CLI flag disables redaction (unsafe for sensitive logs)
- Log files are processed in memory and not stored permanently by default

---

## Sample logs

| ID | Filename | Demonstrates |
|----|----------|-------------|
| `example_failure` | `example_failure.log` | npm auth test failure |
| `cascading_db_failure` | `cascading_db_failure.log` | Postgres refused → 7 cascading test failures |
| `secret_redaction_failure` | `secret_redaction_failure.log` | Credential detection and redaction |
| `python_dependency_failure` | `python_dependency_failure.log` | pip resolution failure → ModuleNotFoundError |
| `compilation_failure` | `compilation_failure.log` | TypeScript type errors → build failure |

All samples use fictional, non-functional credentials where applicable.

---

## Scoring system

Scores are **deterministic priority weights**, not AI confidence and not a guaranteed root cause.

| Weight range | Meaning |
|---|---|
| 0.85 – 0.92 | High-confidence cause signal (connection refused, module not found, etc.) |
| 0.80 – 0.84 | Strong cause indicator (auth failure, version mismatch, compilation error) |
| 0.22 – 0.34 | Likely cascade symptom (test failure, generic FAILED, GitHub error annotation) |
| 0.30 | Unrecognized error pattern |

Rules are defined in [`src/whyci/config.py`](src/whyci/config.py) and can be extended without changing the engine.

---

## Known limitations

- No authentication or user accounts (by design for MVP)
- No persistent storage of uploaded logs
- No LLM integration in the current MVP
- GitHub Actions API integration is documented as a future extension
- Redaction is regex-based and cannot guarantee all secrets are caught
- Archive analysis via ZIP (GitHub Actions log downloads) is CLI-only in the current API

---

## Next steps (live demo / deployment)

```bash
# Kill any existing server on port 8000, then:
PYTHONPATH=src uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Visit:
# http://localhost:8000      → Web UI
# http://localhost:8000/docs → Interactive API docs
```

For deployment, set `allow_origins` in [`backend/main.py`](backend/main.py) to your production domain and run behind a reverse proxy (nginx, Caddy) with HTTPS.
