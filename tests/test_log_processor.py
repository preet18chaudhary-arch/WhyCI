from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from whyci.log_processor.processor import (
    load_log_lines,
    process_log_file,
)


@pytest.fixture
def sample_log_path() -> Path:
    return ROOT / "sample_logs" / "example_failure.log"


@pytest.fixture
def fixture_log(tmp_path: Path) -> Path:
    content = "\n".join(
        [
            "Starting workflow",
            "npm WARN deprecated some-package@1.0.0",
            "Running tests",
            "Error: expected 200, got 500",
            "FAIL: test_login",
            "Warning: coverage below threshold",
            "Build completed with failures",
        ]
    )
    path = tmp_path / "ci.log"
    path.write_text(content, encoding="utf-8")
    return path


def test_log_loading(fixture_log: Path) -> None:
    lines = load_log_lines(fixture_log)
    assert lines[0].text == "Starting workflow"
    assert lines[-1].text == "Build completed with failures"


def test_missing_log_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_log_lines(Path("does-not-exist.log"))


def test_line_counting(fixture_log: Path) -> None:
    result = process_log_file(fixture_log)
    assert result.total_lines == 7


def test_error_detection(fixture_log: Path) -> None:
    result = process_log_file(fixture_log)
    texts = [line.text for line in result.error_lines]
    assert result.error_count == 2
    assert "Error: expected 200, got 500" in texts
    assert "FAIL: test_login" in texts


def test_warning_detection(fixture_log: Path) -> None:
    result = process_log_file(fixture_log)
    texts = [line.text for line in result.warning_lines]
    assert result.warning_count == 2
    assert "npm WARN deprecated some-package@1.0.0" in texts
    assert "Warning: coverage below threshold" in texts


def test_preserves_original_line_numbers(fixture_log: Path) -> None:
    result = process_log_file(fixture_log)
    error_numbers = [line.line_number for line in result.error_lines]
    warning_numbers = [line.line_number for line in result.warning_lines]
    assert error_numbers == [4, 5]
    assert warning_numbers == [2, 6]


def test_sample_log_loads(sample_log_path: Path) -> None:
    result = process_log_file(sample_log_path)
    assert result.total_lines > 0
    assert result.error_count > 0
