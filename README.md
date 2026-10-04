# WhyCI — Explain Why This Failed

WhyCI is a privacy-first CI failure diagnosis engine for GitHub Actions. The long-term goal is to turn noisy workflow logs into a structured explanation of what failed, with secrets redacted before any external AI analysis.

The LLM is support, not the core. The engineering value is the log-intelligence and security pipeline around it.

## Current phase

This repository is a **local CI-log-processing prototype** (Phase 2).

It can:

- read a CI log file
- count lines and flag error-like / warning-like signals
- score those signals with a transparent heuristic
- group nearby errors into failure clusters
- propose a **likely root-cause candidate** and possible cascading failures

The score is a deterministic priority weight, **not** AI confidence, and **not** a guaranteed root cause.

It does **not** yet:

- talk to GitHub or GitHub Actions
- call an LLM
- redact secrets
- post pull request comments
- include a frontend, database, or authentication

## Project structure

```
WhyCI/
├── src/whyci/              # Python package
│   ├── main.py             # CLI entry point
│   ├── config.py           # detection patterns and scoring rules
│   └── log_processor/      # loading, classification, heuristic analysis
├── tests/                  # pytest coverage for processor and analyzer
├── sample_logs/            # example GitHub Actions-style failure logs
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Install dependencies

Python 3.11+ is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the CLI

From the project root, put `src` on `PYTHONPATH` so `python -m whyci.main` can import the package:

```powershell
$env:PYTHONPATH = "src"
python -m whyci.main --log sample_logs/example_failure.log
python -m whyci.main --log sample_logs/cascading_db_failure.log
```

On macOS or Linux:

```bash
PYTHONPATH=src python -m whyci.main --log sample_logs/example_failure.log
PYTHONPATH=src python -m whyci.main --log sample_logs/cascading_db_failure.log
```

The CLI prints total lines, error and warning counts, a likely root-cause candidate with a heuristic score, supporting evidence, possible cascading failures, and the detected error lines with original line numbers.

## Run tests

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests
```
