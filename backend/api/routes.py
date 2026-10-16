"""FastAPI route handlers for the WhyCI API."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

# Ensure src/ is importable
_SRC_DIR = Path(__file__).parent.parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from whyci.log_processor.processor import LogLine, process_log_lines
from backend.api.schemas import AnalysisResponse, HealthResponse, SampleInfo
from backend.service import processing_result_to_response
from backend.history import record_analysis, list_history, clear_history
from fastapi import status
router = APIRouter()

# --- Constants ---
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_LINE_COUNT = 100_000

_SAMPLE_LOGS_DIR = Path(__file__).parent.parent.parent / "sample_logs"

SAMPLES: list[SampleInfo] = [
    SampleInfo(
        id="example_failure",
        name="Auth Test Failure",
        description="npm test suite with a failing auth test and cascading npm/git errors",
        filename="example_failure.log",
    ),
    SampleInfo(
        id="cascading_db_failure",
        name="Cascading Database Failure",
        description="Postgres connection refused at startup causing multiple downstream test failures",
        filename="cascading_db_failure.log",
    ),
    SampleInfo(
        id="secret_redaction_failure",
        name="Secret Redaction Demo",
        description="Log containing credentials that WhyCI redacts before analysis",
        filename="secret_redaction_failure.log",
    ),
    SampleInfo(
        id="python_dependency_failure",
        name="Python Dependency Missing",
        description="pip install fails due to a missing package causing ModuleNotFoundError",
        filename="python_dependency_failure.log",
    ),
    SampleInfo(
        id="compilation_failure",
        name="TypeScript Compilation Failure",
        description="TypeScript type errors prevent the build from completing",
        filename="compilation_failure.log",
    ),
]

_SAMPLE_BY_ID = {s.id: s for s in SAMPLES}


# --- Helpers ---

def _read_upload_to_lines(content: bytes, filename: str) -> list[LogLine]:
    """Decode upload bytes to LogLine list with safety limits."""
    # Basic binary detection
    if b"\x00" in content:
        raise HTTPException(
            status_code=422,
            detail="File appears to be binary. Only plain-text log files are supported.",
        )
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="Could not decode file as UTF-8 text.",
        )
    raw_lines = text.splitlines()
    if len(raw_lines) > MAX_LINE_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"Log file exceeds the {MAX_LINE_COUNT:,}-line limit ({len(raw_lines):,} lines).",
        )
    return [LogLine(line_number=i + 1, text=line) for i, line in enumerate(raw_lines)]



def _analyze_lines(lines: list[LogLine], source_name: str) -> AnalysisResponse:
    result = process_log_lines(lines, source_path=source_name, redact=True)
    response = processing_result_to_response(result, source_name=source_name)

    # Persist only the redacted API response.
    saved = record_analysis(response.model_dump())
    return AnalysisResponse(**saved)



# --- Routes ---


@router.get("/api/history", tags=["history"])
def get_analysis_history():
    """Return recent analysis history."""
    return {"items": list_history()}


@router.delete("/api/history", tags=["history"])
def delete_analysis_history():
    """Clear local analysis history."""
    deleted_count = clear_history()
    return {"deleted_count": deleted_count}


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Return application health status."""
    return HealthResponse(
        status="ok",
        version="0.4.0",
        engine="whyci-deterministic",
    )


@router.get("/api/samples", response_model=list[SampleInfo], tags=["samples"])
def list_samples() -> list[SampleInfo]:
    """Return the list of bundled example log files."""
    return SAMPLES


@router.get("/api/samples/{sample_id}", response_model=SampleInfo, tags=["samples"])
def get_sample_info(sample_id: str) -> SampleInfo:
    sample = _SAMPLE_BY_ID.get(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found.")
    return sample


@router.get("/api/demo/{sample_id}", response_model=AnalysisResponse, tags=["analysis"])
def demo_analysis(sample_id: str) -> AnalysisResponse:
    """Analyze a bundled sample log and return the structured result."""
    sample = _SAMPLE_BY_ID.get(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found.")

    log_path = _SAMPLE_LOGS_DIR / sample.filename
    if not log_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Sample file '{sample.filename}' is missing from the server.",
        )

    try:
        content = log_path.read_bytes()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not read sample file: {exc}",
        )

    lines = _read_upload_to_lines(content, sample.filename)
    return _analyze_lines(lines, source_name=sample.filename)


@router.post("/api/analyze", response_model=AnalysisResponse, tags=["analysis"])
async def analyze_upload(
    file: Annotated[UploadFile, File(description="CI log file (.log or .txt, max 10 MB)")],
) -> AnalysisResponse:
    """Accept a CI log file upload and return a structured deterministic analysis."""

    # Validate content type / extension loosely (don't rely solely on filename)
    filename = file.filename or "upload.log"
    lower = filename.lower()
    if not (lower.endswith(".log") or lower.endswith(".txt")):
        raise HTTPException(
            status_code=422,
            detail="Only .log and .txt files are accepted.",
        )

    # Read with size limit
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024*1024)} MB limit.",
        )
    if len(content) == 0:
        raise HTTPException(
            status_code=422,
            detail="Uploaded file is empty.",
        )

    lines = _read_upload_to_lines(content, filename)
    safe_name = Path(filename).name  # strip any path component
    return _analyze_lines(lines, source_name=safe_name)
