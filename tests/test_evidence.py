from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from whyci.log_processor.processor import process_log_file
from whyci.main import format_summary


def _write_log(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "ci.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_extracts_primary_supporting_and_cascading_evidence(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "Initializing application database",
            "Error: Cannot connect to database",
            "Database connection refused at postgres:5432",
            "Failed to initialize database schema",
            "starting tests",
            "running suite",
            "still running",
            "FAIL: user test",
            "FAIL: order test",
            "npm ERR! Test failed. See above for more details.",
        ],
    )
    result = process_log_file(log_path)

    assert result.root_cause_candidate is not None
    assert result.root_cause_line_number == 3
    assert result.root_cause_category == "infrastructure"
    assert result.root_cause_score is not None
    assert result.primary_evidence
    assert result.primary_evidence[0].line_number == 3
    supporting_numbers = [line.line_number for line in result.supporting_evidence]
    assert 2 in supporting_numbers
    assert 4 in supporting_numbers
    cascading_numbers = [line.line_number for line in result.cascading_evidence]
    assert cascading_numbers
    assert min(cascading_numbers) > result.root_cause_line_number
    assert any("FAIL:" in line.text for line in result.cascading_evidence)


def test_relevant_context_keeps_original_line_numbers(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "ok",
            "Initializing application database",
            "Error: Cannot connect to database",
            "Database connection refused",
            "later setup note",
            "running suite",
            "still running",
            "FAIL: user test",
        ],
    )
    result = process_log_file(log_path)

    context_numbers = [line.line_number for line in result.relevant_context]
    occupied = {
        line.line_number
        for line in result.primary_evidence
        + result.supporting_evidence
        + result.cascading_evidence
    }
    assert context_numbers
    assert all(number not in occupied for number in context_numbers)
    assert 2 in context_numbers
    assert context_numbers == sorted(context_numbers)


def test_cascading_sample_has_structured_evidence() -> None:
    sample = ROOT / "sample_logs" / "cascading_db_failure.log"
    result = process_log_file(sample)

    assert result.primary_evidence
    assert result.supporting_evidence
    assert result.cascading_evidence
    assert result.redaction is not None
    assert result.redaction.applied is False
    assert result.redaction.replacement_count == 0
    assert result.root_cause_line_number is not None
    for line in result.primary_evidence + result.supporting_evidence + result.cascading_evidence:
        assert line.line_number >= 1


def test_cli_keeps_phase2_sections_and_adds_evidence(tmp_path: Path) -> None:
    sample = ROOT / "sample_logs" / "cascading_db_failure.log"
    summary = format_summary(process_log_file(sample))
    assert "LIKELY ROOT-CAUSE CANDIDATE" in summary
    assert "Primary evidence:" in summary
    assert "Supporting evidence:" in summary
    assert "Possible cascading failures:" in summary
    assert "Relevant context:" in summary
    assert "Secret redaction:" in summary
    assert "not applied" in summary
    assert "Heuristic score:" in summary
