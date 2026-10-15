# WhyCI — Explain Why This Failed

WhyCI is a privacy-first CI failure diagnosis engine for GitHub Actions. The long-term goal is to turn noisy workflow logs into a structured explanation of what failed, with secrets redacted before any external AI analysis.

The LLM is support, not the core. The engineering value is the log-intelligence and security pipeline around it.

## Current phase

This repository is a **local CI-log-processing prototype with GitHub Actions archive support and security redaction** (Phase 4).

It can:

- read single CI log files (`--log`)
- safely inspect and analyze locally downloaded GitHub Actions workflow log ZIP archives (`--archive` / `--zip`)
- defend against malicious archives (Zip Slip path traversal prevention, in-memory stream extraction, decompression bomb limits)
- redact secrets and credentials by default (Phase 3 security layer)
- score signals with a transparent heuristic
- group nearby errors into failure clusters
- propose a **likely root-cause candidate** and possible cascading failures across workflow jobs

The score is a deterministic priority weight, **not** AI confidence, and **not** a guaranteed root cause.

It does **not** yet:

- call an LLM
- post pull request comments
- include a frontend, database, or authentication

## Project structure

```
WhyCI/
├── src/whyci/              # Python package
│   ├── main.py             # CLI entry point (--log, --archive)
│   ├── config.py           # detection patterns and scoring rules
│   ├── github_actions.py   # safe workflow ZIP archive processing (Phase 4)
│   ├── redactor.py         # deterministic secret redaction (Phase 3)
│   └── log_processor/      # loading, classification, heuristic analysis
├── tests/                  # pytest coverage (processor, analyzer, redactor, github_actions)
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

From the project root, put `src` on `PYTHONPATH` so `python -m whyci.main` can import the package.

### 1. Single Log File (`--log`)

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

The CLI prints total lines, error and warning counts, a likely root-cause candidate with a heuristic score, supporting evidence, possible cascading failures, and the detected error lines with original line numbers. Secrets are automatically redacted by default.

### 2. GitHub Actions Workflow Archive (`--archive` / `--zip`)

WhyCI supports analyzing locally downloaded GitHub Actions workflow run log archives in ZIP format without needing a GitHub API token:

#### How to download logs from GitHub Actions:
- **Via GitHub Web UI**: Open the failed workflow run page, click the `...` menu in the upper-right corner of the run, and select **Download log archive** (saves a `.zip` file).
- **Via GitHub CLI (`gh`)**:
  ```bash
  gh run download <run-id>
  ```

#### Analyzing the archive:

```powershell
$env:PYTHONPATH = "src"
python -m whyci.main --archive path/to/workflow_logs.zip
```

On macOS or Linux:

```bash
PYTHONPATH=src python -m whyci.main --archive path/to/workflow_logs.zip
```

#### Safe Archive Processing Guarantees:
- **In-Memory Streaming**: Log entries are read directly from archive streams into memory without extracting files to arbitrary disk locations.
- **Path Traversal Protection**: Rejects zip slip attempts (`../`, absolute paths).
- **Decompression Bomb Protection**: Enforces safety caps (max 50 MB total decompressed, max 20 MB per file, max 100 entries).
- **Multi-Job Candidate Ranking**: Evaluates each job in the workflow and ranks the overall root-cause candidate across all jobs.
- **Automatic Secret Redaction**: Credentials in all workflow logs are sanitized by default before analysis.

### 3. Secret Redaction & Offline Debugging

Redaction is enabled by default for both single logs and archives. To disable redaction for offline debugging of non-sensitive logs:

```powershell
python -m whyci.main --log sample_logs/example_failure.log --no-redact
python -m whyci.main --archive path/to/workflow_logs.zip --no-redact
```

> [!WARNING]
> `--no-redact` is **UNSAFE** for logs containing credentials or secrets.

## Run tests

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests
```
