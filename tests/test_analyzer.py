from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from whyci.log_processor.analyzer import cluster_error_lines
from whyci.log_processor.processor import LogLine, process_log_file


def _write_log(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "ci.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_identifies_strong_root_cause_candidate(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "Starting job",
            "Error: Cannot connect to database",
            "Database connection refused",
            "FAIL: user test",
        ],
    )
    result = process_log_file(log_path)

    assert result.root_cause_candidate is not None
    assert result.root_cause_line_number == 3
    assert "connection refused" in result.root_cause_candidate.text.lower()
    assert result.root_cause_score is not None
    assert result.root_cause_score >= 0.90


def test_prefers_infrastructure_error_over_generic_test_failures(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "npm ci",
            "Error: Cannot find module 'pg'",
            "starting tests",
            "running suite",
            "still running",
            "FAIL: user test",
            "FAIL: order test",
            "npm ERR! Test failed. See above for more details.",
            "##[error]Process completed with exit code 1.",
        ],
    )
    result = process_log_file(log_path)

    assert result.root_cause_line_number == 2
    assert "Cannot find module" in result.root_cause_candidate.text
    cascade_texts = [line.text for line in result.cascading_failure_lines]
    assert "FAIL: user test" in cascade_texts
    assert "FAIL: order test" in cascade_texts


def test_analysis_preserves_original_line_numbers(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "ok",
            "ok",
            "Error: permission denied: .env",
            "ok",
            "ok",
            "ok",
            "FAIL: reads config",
        ],
    )
    result = process_log_file(log_path)

    assert result.root_cause_line_number == 3
    assert result.error_lines[0].line_number == 3
    assert result.cascading_failure_lines[0].line_number == 7


def test_groups_nearby_related_errors(tmp_path: Path) -> None:
    lines = [
        LogLine(20, "Error: Cannot connect to database"),
        LogLine(21, "Database connection refused"),
        LogLine(25, "FAIL: user test"),
        LogLine(26, "FAIL: order test"),
    ]
    clusters = cluster_error_lines(lines)

    assert len(clusters) == 2
    assert [line.line_number for line in clusters[0].lines] == [20, 21]
    assert [line.line_number for line in clusters[1].lines] == [25, 26]


def test_identifies_possible_cascading_failures(tmp_path: Path) -> None:
    sample = ROOT / "sample_logs" / "cascading_db_failure.log"
    result = process_log_file(sample)

    assert result.root_cause_candidate is not None
    assert result.root_cause_line_number is not None
    assert result.root_cause_line_number < 10
    assert "connect" in result.root_cause_candidate.text.lower() or "refused" in result.root_cause_candidate.text.lower()
    cascade_numbers = [line.line_number for line in result.cascading_failure_lines]
    assert cascade_numbers
    assert min(cascade_numbers) > result.root_cause_line_number
    assert any("FAIL:" in line.text for line in result.cascading_failure_lines)


def test_handles_log_with_no_clear_root_cause_candidate(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "Starting workflow",
            "npm WARN deprecated leftover@1.0.0",
            "All checks skipped",
            "##[warning]Node.js 18 actions are deprecated.",
        ],
    )
    result = process_log_file(log_path)

    assert result.error_count == 0
    assert result.root_cause_candidate is None
    assert result.root_cause_score is None
    assert result.root_cause_line_number is None


def test_generic_exit_code_is_not_a_clear_candidate(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "Running job",
            "##[error]Process completed with exit code 1.",
        ],
    )
    result = process_log_file(log_path)

    assert result.error_count == 1
    assert result.root_cause_candidate is None
