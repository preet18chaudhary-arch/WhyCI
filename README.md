# WhyCI — Explain Why Your CI Failed

> **Stop guessing. Start fixing.**

WhyCI is a privacy-first CI failure diagnosis tool that turns noisy CI logs into explainable results. It redacts recognized secrets, groups related failures, and ranks a likely root-cause candidate with supporting evidence, original line numbers, and actionable debugging suggestions.

**Built around deterministic analysis, not an LLM.** WhyCI uses transparent heuristic scoring to help developers investigate CI failures without requiring AI credentials.

## Features

- **Log analysis:** classify error and warning signals from CI logs.
- **Secret redaction:** redact recognized credentials before analysis or display.
- **Failure clustering:** group related errors to make patterns easier to inspect.
- **Root-cause ranking:** prioritize a likely cause using deterministic heuristic scoring.
- **Cascade detection:** highlight possible downstream failures.
- **Evidence and line numbers:** explain why a candidate was selected.
- **Debugging suggestions:** provide practical next steps for different failure categories.
- **Report exports:** export sanitized results as JSON or Markdown.
- **Web interface and CLI:** inspect logs in the browser or run analysis from the command line.
- **Five bundled demos:** explore authentication, database, secret-redaction, Python dependency, and TypeScript compilation failures.

> **Scoring note:** Scores are heuristic priority weights, not AI confidence probabilities or guarantees of the true root cause.

## Project structure

The project includes a Python analysis engine, a FastAPI backend, a React and TypeScript frontend, sample CI logs, and automated tests.

```text
WhyCI/
├── src/whyci/          # Deterministic analysis engine
├── backend/            # FastAPI application and API routes
├── frontend/           # React + TypeScript web interface
├── sample_logs/        # Five bundled CI failure examples
├── tests/              # Automated test suite
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```
## Status

WhyCI runs locally and includes a web interface, a CLI, API endpoints, secret-redaction logic, sample scenarios, and automated tests. Its analysis is heuristic, so results should be reviewed alongside the supporting evidence.

## Prerequisites

- Python 3.11 or newer
- Node.js 18 or newer
- npm 9 or newer

## Installation

### 1. Install Python dependencies

From the project root, create and activate a virtual environment in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. Install frontend dependencies

```powershell
cd frontend
npm install
cd ..
```

## Run the application

### Start the backend

From the project root, in PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

When the server starts, open these URLs in your browser:

- Web application: http://localhost:8000
- Interactive API documentation: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Build the frontend

If you need to rebuild the frontend, open a second terminal in the project root and run:

```powershell
cd frontend
npm run build
cd ..
```

### Run the CLI

From the project root, in a terminal:

```powershell
$env:PYTHONPATH = "src"
python -m whyci.main --log sample_logs/example_failure.log
python -m whyci.main --log sample_logs/cascading_db_failure.log
```

## Run tests

From the project root:

```powershell
$env:PYTHONPATH = "src"
python -m pytest -v
```

The current verified backend test result is **88 passed**. Re-run the tests after code changes to confirm the result remains current.

## API overview

The FastAPI backend provides endpoints for health checks, bundled sample logs, log analysis, and demo workflows.

Open [the interactive API documentation](http://localhost:8000/docs) while the application is running to inspect the available routes and their request and response formats.

## Security and limitations

- WhyCI is designed to redact recognized secrets before analysis or display.
- Redaction is pattern-based and cannot guarantee detection of every possible credential.
- Analysis uses deterministic heuristic scoring, not a calibrated probability of correctness.
- Treat diagnostic results as recommendations and review the evidence before changing your CI configuration.
- Avoid uploading sensitive production logs unless you are comfortable with how and where they are processed.

## Current limitations

- Root-cause rankings are heuristic candidates, not guaranteed diagnoses.
- Unrecognized log formats and secrets may not be handled correctly.
- Results depend on the patterns and rules implemented in the current version.

## Roadmap

Potential future improvements include broader CI log format support, additional tested redaction patterns, and optional integrations with CI platforms.
