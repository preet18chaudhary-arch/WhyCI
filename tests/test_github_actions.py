from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from whyci.github_actions import (
    MAX_ARCHIVE_FILE_COUNT,
    MAX_SINGLE_FILE_BYTES,
    MAX_TOTAL_UNCOMPRESSED_BYTES,
    WorkflowResult,
    is_supported_log_file,
    process_workflow_archive,
    validate_archive_entry_path,
)
from whyci.main import format_workflow_summary, main


def _create_zip(tmp_path: Path, files: dict[str, str], zip_name: str = "workflow.zip") -> Path:
    zip_path = tmp_path / zip_name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in files.items():
            zf.writestr(arcname, content)
    return zip_path


def test_supported_log_extensions() -> None:
    assert is_supported_log_file("job.txt")
    assert is_supported_log_file("test.log")
    assert is_supported_log_file("JOB_RUN.TXT")
    assert not is_supported_log_file("metadata.json")
    assert not is_supported_log_file("artifact.tar.gz")
    assert not is_supported_log_file("report.html")


def test_path_traversal_validation() -> None:
    # Valid relative paths
    validate_archive_entry_path("job1.txt")
    validate_archive_entry_path("build/1_setup.txt")
    validate_archive_entry_path("nested/dir/step.log")

    # Path traversal ../
    with pytest.raises(ValueError, match="path traversal '..'"):
        validate_archive_entry_path("../../etc/passwd")

    with pytest.raises(ValueError, match="path traversal '..'"):
        validate_archive_entry_path("build/../etc/passwd")

    with pytest.raises(ValueError, match="path traversal '..'"):
        validate_archive_entry_path("..\\evil.txt")

    # Absolute paths
    with pytest.raises(ValueError, match="absolute path"):
        validate_archive_entry_path("/etc/passwd")

    with pytest.raises(ValueError, match="absolute path"):
        validate_archive_entry_path("\\Windows\\System32\\cmd.exe")

    with pytest.raises(ValueError, match="absolute path"):
        validate_archive_entry_path("C:\\secret.txt")

    # Null bytes
    with pytest.raises(ValueError, match="null byte"):
        validate_archive_entry_path("safe.txt\x00evil.exe")

    # Control characters / terminal escape sequences
    with pytest.raises(ValueError, match="control characters"):
        validate_archive_entry_path("job\x1b[2K.txt")

    with pytest.raises(ValueError, match="control characters"):
        validate_archive_entry_path("job\r\n.txt")

    # Windows reserved device names
    with pytest.raises(ValueError, match="reserved device name"):
        validate_archive_entry_path("CON.txt")

    with pytest.raises(ValueError, match="reserved device name"):
        validate_archive_entry_path("sub/NUL.log")


def test_process_valid_workflow_archive(tmp_path: Path) -> None:
    files = {
        "build/1_setup.txt": "Starting build job\nEnvironment ready\n",
        "build/2_init_db.txt": (
            "Starting database\n"
            "Error: Cannot connect to database\n"
            "Database connection refused at postgres:5432\n"
            "Failed to initialize database schema\n"
        ),
        "test/1_run_tests.txt": (
            "Starting test suite\n"
            "FAIL: user test\n"
            "FAIL: order test\n"
            "npm ERR! Test failed. See above for more details.\n"
            "##[error]Process completed with exit code 1.\n"
        ),
        "summary.json": '{"status": "failure"}',  # unsupported file
    }
    zip_path = _create_zip(tmp_path, files)
    result = process_workflow_archive(zip_path)

    assert isinstance(result, WorkflowResult)
    assert result.total_jobs == 3
    assert len(result.failing_jobs) == 2
    assert "summary.json" in result.unsupported_files

    # Top candidate should be the database connection refused (0.92 weight)
    assert result.top_candidate_job is not None
    assert "2_init_db.txt" in str(result.top_candidate_job.source_path)
    assert result.top_candidate_job.root_cause_candidate is not None
    assert result.top_candidate_job.root_cause_line_number == 3
    assert "connection refused" in result.top_candidate_job.root_cause_candidate.text.lower()
    assert result.top_candidate_job.root_cause_category == "infrastructure"


def test_workflow_archive_redacts_secrets_by_default(tmp_path: Path) -> None:
    files = {
        "job_with_secrets.txt": (
            "export AWS_SECRET_ACCESS_KEY=my-top-secret-aws-key-999\n"
            "Error: Authentication failed for https://admin:superpassword123@db.prod:5432\n"
            "Database connection refused with PASSWORD=my-db-pass-456\n"
            "FAIL: auth test with token ghp_111111111111111111111111111111111111\n"
        ),
    }
    zip_path = _create_zip(tmp_path, files)
    result = process_workflow_archive(zip_path, redact=True)

    job = result.job_results[0]
    assert "my-top-secret-aws-key-999" not in str(job.error_lines)
    assert "superpassword123" not in str(job.error_lines)
    assert "my-db-pass-456" not in str(job.error_lines)
    assert "ghp_111111111111111111111111111111111111" not in str(job.error_lines)

    # Redacted markers present
    assert job.root_cause_candidate is not None
    assert "[REDACTED]" in job.root_cause_candidate.text


def test_workflow_archive_allows_disabling_redaction(tmp_path: Path) -> None:
    files = {
        "job.txt": "Error: Database connection refused with PASSWORD=rawpass123\n",
    }
    zip_path = _create_zip(tmp_path, files)
    unredacted = process_workflow_archive(zip_path, redact=False)
    assert "rawpass123" in unredacted.job_results[0].error_lines[0].text


def test_archive_preserves_1_based_line_numbers_per_file(tmp_path: Path) -> None:
    files = {
        "job_a.txt": (
            "Line 1 ok\n"
            "Line 2 ok\n"
            "Line 3 Error: Cannot find module 'foo'\n"
            "Line 4 ok\n"
        ),
        "job_b.txt": (
            "Line 1 ok\n"
            "Line 2 FAIL: test_feature\n"
        ),
    }
    zip_path = _create_zip(tmp_path, files)
    result = process_workflow_archive(zip_path)

    job_a = next(j for j in result.job_results if "job_a.txt" in str(j.source_path))
    job_b = next(j for j in result.job_results if "job_b.txt" in str(j.source_path))

    assert job_a.error_lines[0].line_number == 3
    assert job_b.error_lines[0].line_number == 2


def test_rejects_missing_archive_file(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.zip"
    with pytest.raises(FileNotFoundError, match="Workflow archive not found"):
        process_workflow_archive(missing)


def test_rejects_corrupted_or_non_zip_file(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.zip"
    corrupt.write_text("this is not a zip file content", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid or corrupted ZIP archive"):
        process_workflow_archive(corrupt)


def test_rejects_empty_archive(tmp_path: Path) -> None:
    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w") as zf:
        pass  # 0 entries

    with pytest.raises(ValueError, match="contains no supported log files"):
        process_workflow_archive(empty_zip)


def test_rejects_archive_with_only_unsupported_files(tmp_path: Path) -> None:
    files = {
        "image.png": "binarycontent",
        "data.json": '{"k": "v"}',
        "document.pdf": "%PDF-1.4",
    }
    zip_path = _create_zip(tmp_path, files)
    with pytest.raises(ValueError, match="contains no supported log files"):
        process_workflow_archive(zip_path)


def test_rejects_archive_exceeding_file_count_limit(tmp_path: Path) -> None:
    zip_path = tmp_path / "too_many_files.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for i in range(MAX_ARCHIVE_FILE_COUNT + 5):
            zf.writestr(f"file_{i}.txt", "test log\n")

    with pytest.raises(ValueError, match="exceeding safety limit"):
        process_workflow_archive(zip_path)


def test_rejects_entry_exceeding_single_file_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Lower limit temporarily for testing
    import whyci.github_actions as ga
    monkeypatch.setattr(ga, "MAX_SINGLE_FILE_BYTES", 500)

    files = {
        "normal.txt": "short log\n",
        "huge.txt": "A" * 600,
    }
    zip_path = _create_zip(tmp_path, files)
    with pytest.raises(ValueError, match="exceeds single file limit|decompressed file size limit"):
        process_workflow_archive(zip_path)


def test_rejects_archive_exceeding_total_decompressed_size_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import whyci.github_actions as ga
    monkeypatch.setattr(ga, "MAX_TOTAL_UNCOMPRESSED_BYTES", 800)

    files = {
        "file1.txt": "A" * 500,
        "file2.txt": "B" * 500,
    }
    zip_path = _create_zip(tmp_path, files)
    with pytest.raises(ValueError, match="exceeds total decompression limit"):
        process_workflow_archive(zip_path)


def test_cli_archive_integration(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = {
        "build.txt": (
            "Starting build\n"
            "Error: Cannot connect to database\n"
            "Database connection refused at postgres:5432\n"
        ),
        "test.txt": "Starting test\nFAIL: test_orders\n",
    }
    zip_path = _create_zip(tmp_path, files)

    # Test with --archive
    exit_code = main(["--archive", str(zip_path)])
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "WHYCI GITHUB ACTIONS WORKFLOW ANALYSIS" in captured
    assert "Database connection refused" in captured
    assert "LIKELY WORKFLOW ROOT-CAUSE CANDIDATE" in captured
    assert "JOB SUMMARIES" in captured
    assert "build.txt" in captured
    assert "test.txt" in captured
    assert "This is a deterministic heuristic analysis, not a guaranteed root-cause diagnosis." in captured

    # Test with --zip alias
    exit_code_zip = main(["--zip", str(zip_path)])
    assert exit_code_zip == 0


def test_cli_archive_errors_handled_gracefully(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "not_there.zip"
    code = main(["--archive", str(missing)])
    assert code == 1
    err = capsys.readouterr().err
    assert "error: Workflow archive not found" in err


def test_binary_file_in_archive_is_detected_and_skipped(tmp_path: Path) -> None:
    zip_path = tmp_path / "mixed_binary.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        # Valid text log
        zf.writestr("valid_job.txt", "Starting job\nok\n")
        # Binary file with null bytes disguised as .txt
        zf.writestr("binary_payload.txt", b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00")

    result = process_workflow_archive(zip_path)
    assert result.total_jobs == 1
    assert "valid_job.txt" in str(result.job_results[0].source_path)
    assert any("binary_payload.txt" in f for f in result.unsupported_files)


def test_archive_with_only_binary_files_is_rejected(tmp_path: Path) -> None:
    zip_path = tmp_path / "only_binary.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("binary1.txt", b"\x00\x01\x02\x03")
        zf.writestr("binary2.log", b"ELF\x00data")

    with pytest.raises(ValueError, match="contains no supported log files"):
        process_workflow_archive(zip_path)
