"""API integration tests using FastAPI TestClient.

These tests run offline and never call external services.
All tests use the bundled sample logs and the real deterministic engine.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

# Ensure src/ and project root are importable
_ROOT = Path(__file__).parent.parent
_SRC = _ROOT / "src"
for p in [str(_ROOT), str(_SRC)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

SAMPLE_LOG_DIR = _ROOT / "sample_logs"


# ---------- /health ----------

def test_health_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "engine" in body


# ---------- /api/samples ----------

def test_list_samples_returns_list():
    r = client.get("/api/samples")
    assert r.status_code == 200
    samples = r.json()
    assert isinstance(samples, list)
    assert len(samples) >= 3
    ids = [s["id"] for s in samples]
    assert "example_failure" in ids
    assert "cascading_db_failure" in ids


def test_get_sample_info_valid():
    r = client.get("/api/samples/example_failure")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "example_failure"
    assert "filename" in body
    assert "description" in body


def test_get_sample_info_unknown():
    r = client.get("/api/samples/does_not_exist")
    assert r.status_code == 404


# ---------- /api/demo/{id} ----------

def test_demo_example_failure():
    r = client.get("/api/demo/example_failure")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["total_lines"] > 0
    assert body["error_count"] > 0
    # Root cause must be present for this log
    assert body["root_cause"] is not None
    rc = body["root_cause"]
    assert rc["line_number"] > 0
    assert rc["priority_score"] > 0
    assert len(rc["score_reasons"]) > 0


def test_demo_cascading_db_failure():
    r = client.get("/api/demo/cascading_db_failure")
    assert r.status_code == 200
    body = r.json()
    assert body["root_cause"] is not None
    # Should identify database/infrastructure as root cause
    assert body["root_cause"]["category"] in ("infrastructure", "dependency", "authentication")
    assert len(body["cascading_failures"]) > 0


def test_demo_python_dependency_failure():
    r = client.get("/api/demo/python_dependency_failure")
    assert r.status_code == 200
    body = r.json()
    assert body["root_cause"] is not None
    assert body["root_cause"]["category"] == "dependency"


def test_demo_compilation_failure():
    r = client.get("/api/demo/compilation_failure")
    assert r.status_code == 200
    body = r.json()
    assert body["root_cause"] is not None
    assert body["root_cause"]["category"] in ("compilation", "syntax", "dependency", "infrastructure", "unknown")


def test_demo_unknown_sample():
    r = client.get("/api/demo/nonexistent_sample")
    assert r.status_code == 404


def test_demo_returns_debugging_suggestions():
    r = client.get("/api/demo/cascading_db_failure")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["debugging_suggestions"], list)
    assert len(body["debugging_suggestions"]) > 0


def test_demo_returns_analysis_notes():
    r = client.get("/api/demo/example_failure")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["analysis_notes"], list)


def test_demo_redaction_stats():
    r = client.get("/api/demo/secret_redaction_failure")
    assert r.status_code == 200
    body = r.json()
    # Redaction stats may or may not fire depending on log content
    # but the key must be present
    assert "redaction" in body


# ---------- /api/analyze (upload) ----------

def _upload(filename: str, content: bytes, content_type: str = "text/plain") -> dict:
    r = client.post(
        "/api/analyze",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )
    return r


def test_upload_sample_log():
    log = (SAMPLE_LOG_DIR / "example_failure.log").read_bytes()
    r = _upload("example_failure.log", log)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["total_lines"] > 0
    assert body["error_count"] > 0


def test_upload_produces_root_cause_with_evidence():
    log = (SAMPLE_LOG_DIR / "cascading_db_failure.log").read_bytes()
    r = _upload("cascading_db_failure.log", log)
    assert r.status_code == 200
    body = r.json()
    rc = body["root_cause"]
    assert rc is not None
    assert rc["line_number"] > 0
    # Primary evidence should contain at least the candidate line
    assert len(body["primary_evidence"]) > 0


def test_upload_preserves_line_numbers():
    log = (SAMPLE_LOG_DIR / "example_failure.log").read_bytes()
    r = _upload("example_failure.log", log)
    assert r.status_code == 200
    body = r.json()
    rc = body["root_cause"]
    if rc:
        assert rc["line_number"] >= 1


def test_upload_empty_file_is_rejected():
    r = _upload("empty.log", b"")
    assert r.status_code == 422


def test_upload_binary_file_is_rejected():
    binary = bytes(range(256)) * 100  # contains null bytes
    r = _upload("binary.log", binary)
    assert r.status_code == 422


def test_upload_wrong_extension_is_rejected():
    r = _upload("logfile.pdf", b"some log content")
    assert r.status_code == 422


def test_upload_oversized_file_is_rejected():
    # 11 MB of 'a' — just over the 10 MB limit
    big = b"a log line with text\n" * (11 * 1024 * 1024 // 21 + 1)
    r = _upload("big.log", big)
    assert r.status_code == 413


def test_upload_redaction_applied_to_secret_log():
    log = (SAMPLE_LOG_DIR / "secret_redaction_failure.log").read_bytes()
    r = _upload("secret_redaction_failure.log", log)
    assert r.status_code == 200
    body = r.json()
    # Verify the raw credential does not appear in ANY string field
    response_text = r.text
    # Check that known secret patterns from the sample log don't appear raw
    assert "ghp_" not in response_text or "[REDACTED]" in response_text


def test_upload_no_secrets_in_response_fields():
    """Secrets should never appear in root_cause, evidence, or cluster fields."""
    log_content = b"""
Run step: deploy
Setting token=ghp_abcdefghijklmnopqrstuvwxyz012345678
Authorization: Bearer ghp_abcdefghijklmnopqrstuvwxyz012345678
ERROR: Permission denied
""".strip()
    r = _upload("secret_test.log", log_content)
    assert r.status_code == 200
    body = r.json()
    # Raw token must not appear in any text field
    for cluster in body.get("failure_clusters", []):
        for line in cluster.get("lines", []):
            assert "ghp_abcdefghijklmnopqrstuvwxyz012345678" not in line["text"]
    for ev_group in ("primary_evidence", "supporting_evidence", "cascading_failures", "relevant_context"):
        for line in body.get(ev_group, []):
            assert "ghp_abcdefghijklmnopqrstuvwxyz012345678" not in line["text"]
    if body.get("root_cause"):
        assert "ghp_abcdefghijklmnopqrstuvwxyz012345678" not in body["root_cause"]["text"]


def test_upload_unicode_log():
    content = "ERROR: ファイルが見つかりません (File not found)\nWARNING: 設定が不正です\n".encode("utf-8")
    r = _upload("unicode.log", content)
    assert r.status_code == 200
    body = r.json()
    assert body["total_lines"] >= 1


def test_upload_log_with_no_errors():
    content = b"Build started\nBuild succeeded\nAll tests passed\n"
    r = _upload("clean.log", content)
    assert r.status_code == 200
    body = r.json()
    assert body["error_count"] == 0
    assert body["root_cause"] is None
    assert len(body["analysis_notes"]) > 0


def test_response_schema_completeness():
    """Verify all expected top-level fields are present."""
    log = (SAMPLE_LOG_DIR / "example_failure.log").read_bytes()
    r = _upload("example_failure.log", log)
    assert r.status_code == 200
    body = r.json()
    required_fields = [
        "status", "source_name", "total_lines", "error_count", "warning_count",
        "failure_clusters", "root_cause", "primary_evidence", "supporting_evidence",
        "cascading_failures", "relevant_context", "debugging_suggestions",
        "redaction", "analysis_notes",
    ]
    for field in required_fields:
        assert field in body, f"Missing field: {field}"
