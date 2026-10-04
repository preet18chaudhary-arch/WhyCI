from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from whyci.config import REDACTION_PLACEHOLDER
from whyci.log_processor.processor import LogLine, process_log_file
from whyci.log_processor.redactor import redact_line, redact_text
from whyci.main import format_summary

GITHUB_PAT = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
GITHUB_FINE = "github_pat_" + ("A" * 22)


def _write_log(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "ci.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_redacts_api_key_assignment() -> None:
    text, rules = redact_text("export API_KEY=sk-live-example-secret")
    assert REDACTION_PLACEHOLDER in text
    assert "sk-live-example-secret" not in text
    assert text.startswith("export API_KEY=")
    assert "env_assignment" in rules


def test_redacts_password_assignment() -> None:
    text, rules = redact_text("PASSWORD=hunter2")
    assert text == f"PASSWORD={REDACTION_PLACEHOLDER}"
    assert "env_assignment" in rules


def test_redacts_authorization_bearer_token() -> None:
    text, rules = redact_text("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload")
    assert text == f"Authorization: Bearer {REDACTION_PLACEHOLDER}"
    assert "bearer_token" in rules
    assert "eyJhbGciOiJIUzI1NiJ9.payload" not in text


def test_redacts_github_style_tokens() -> None:
    classic, classic_rules = redact_text(f"token {GITHUB_PAT}")
    fine, fine_rules = redact_text(f"using {GITHUB_FINE}")
    assert classic == f"token {REDACTION_PLACEHOLDER}"
    assert fine == f"using {REDACTION_PLACEHOLDER}"
    assert "github_token" in classic_rules
    assert "github_token" in fine_rules


def test_redacts_multiple_secrets_on_one_line() -> None:
    original = f"API_KEY=abc123 PASSWORD=s3cret Authorization: Bearer tok_{GITHUB_PAT}"
    text, rules = redact_text(original)
    assert "abc123" not in text
    assert "s3cret" not in text
    assert "tok_" not in text
    assert GITHUB_PAT not in text
    assert text.count(REDACTION_PLACEHOLDER) >= 3
    assert "env_assignment" in rules
    assert "bearer_token" in rules


def test_redaction_preserves_line_numbers() -> None:
    line = LogLine(line_number=17, text=f"TOKEN={GITHUB_PAT}")
    result = redact_line(line)
    assert result.redacted.line_number == 17
    assert result.original.line_number == 17
    assert result.original.text == line.text
    assert GITHUB_PAT not in result.redacted.text


def test_log_with_no_secrets_is_unchanged() -> None:
    original = "Error: Cannot connect to database"
    text, rules = redact_text(original)
    assert text == original
    assert rules == ()


def test_process_log_redacts_output_and_keeps_line_numbers(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "Starting job",
            f"API_KEY=super-secret-value TOKEN={GITHUB_PAT}",
            "Error: Cannot connect to database",
            "Database connection refused",
            "FAIL: user test",
        ],
    )
    result = process_log_file(log_path)

    assert result.redaction is not None
    assert result.redaction.applied is True
    assert result.redaction.replacement_count >= 2
    assert result.root_cause_line_number == 4
    assert result.error_lines[0].line_number == 3
    secret_line = next(line for line in result.relevant_context if line.line_number == 2)
    assert "super-secret-value" not in secret_line.text
    assert GITHUB_PAT not in secret_line.text
    assert REDACTION_PLACEHOLDER in secret_line.text


def test_cli_summary_reports_redaction(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "Starting job",
            "PASSWORD=dont-print-me",
            "Error: authentication failed",
        ],
    )
    summary = format_summary(process_log_file(log_path))
    assert "dont-print-me" not in summary
    assert "Secret redaction:" in summary
    assert "applied" in summary
    assert "PASSWORD=" in summary
    assert REDACTION_PLACEHOLDER in summary
