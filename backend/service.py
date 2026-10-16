"""Service layer: adapter between the WhyCI engine and the API response schema."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Ensure src/ is on the path so whyci can be imported
_SRC_DIR = Path(__file__).parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from whyci.log_processor.processor import ProcessingResult, LogLine
from backend.api.schemas import (
    AnalysisResponse,
    FailureClusterModel,
    LogLineModel,
    RedactionStats,
    RootCauseModel,
)

# Category → concrete debugging tips
_CATEGORY_SUGGESTIONS: dict[str, list[str]] = {
    "dependency": [
        "Run `pip install -r requirements.txt` or `npm ci` locally to reproduce.",
        "Check for version pinning conflicts in your lock file.",
        "Verify the package name and index URL are correct.",
        "Inspect the full error trail above the 'module not found' line.",
    ],
    "infrastructure": [
        "Check that required services (database, cache, broker) started successfully.",
        "Verify port availability and service health before running tests.",
        "Look for 'connection refused' earlier in the log — the service likely crashed during startup.",
        "Add a health-check/wait step before downstream jobs.",
    ],
    "authentication": [
        "Verify that the required secret or token is set in CI environment variables.",
        "Check token expiry — regenerate if expired.",
        "Confirm the token has the required permissions for this repository or registry.",
        "Never commit credentials to source control.",
    ],
    "permission": [
        "Check file and directory permissions in your workflow.",
        "Ensure the CI runner user has write access to the required paths.",
        "Review any `chmod` or `chown` steps earlier in the workflow.",
    ],
    "compilation": [
        "Run the compiler locally to reproduce the error in full.",
        "Check that all required build tools and SDKs are available in the runner image.",
        "Look at the line number reported by the compiler for the exact error location.",
    ],
    "syntax": [
        "The syntax error location is shown in the log — fix that file first.",
        "Run a linter or formatter locally to catch similar issues.",
        "Check for encoding issues or invisible characters in the affected file.",
    ],
    "configuration": [
        "Validate config files (YAML, JSON, TOML) with a linter.",
        "Compare the config against documentation or a known-good example.",
        "Check that required environment variables or secrets are set in CI.",
    ],
    "environment": [
        "Ensure all required environment variables are set in the CI runner.",
        "Check `.env.example` against secrets configured in your CI provider.",
        "Add explicit validation that required variables are set before running steps.",
    ],
    "test": [
        "Read the assertion failure message — it usually tells you what was expected vs received.",
        "Run the failing test locally: `pytest -x` or `npm test -- --testNamePattern=...`",
        "Look earlier in the log for infrastructure or setup failures that may have caused cascading test failures.",
    ],
    "unknown": [
        "Read the full context around the flagged line for additional clues.",
        "Check if any setup or dependency step failed before this line.",
        "Search the log for 'error' or 'failed' earlier in the run.",
    ],
}

_GENERIC_SUGGESTIONS = [
    "Read the full log around the highlighted lines for additional context.",
    "Check if any earlier step failed — cascading failures are common.",
    "Reproduce the failure locally with the same environment and inputs.",
]


def _to_log_line(line: LogLine) -> LogLineModel:
    return LogLineModel(line_number=line.line_number, text=line.text)


def _debugging_suggestions(result: ProcessingResult) -> list[str]:
    category = result.root_cause_category or "unknown"
    specific = _CATEGORY_SUGGESTIONS.get(category, _CATEGORY_SUGGESTIONS["unknown"])
    notes: list[str] = list(specific)

    # Append a cascading-failure note when relevant
    cascade_count = len(result.cascading_failure_lines) + len(result.cascading_evidence)
    if cascade_count > 0:
        notes.append(
            f"The log shows {cascade_count} likely cascading failure(s) after the root-cause candidate. "
            "Fixing the root cause may resolve those automatically."
        )
    return notes


def _analysis_notes(result: ProcessingResult) -> list[str]:
    notes: list[str] = []
    if result.root_cause_candidate is None:
        notes.append(
            "No high-priority root-cause signal was found. "
            "The log may show only terminal status lines or no recognised failure patterns."
        )
    if result.error_count == 0 and result.warning_count == 0:
        notes.append("No error or warning patterns were detected in this log.")
    notes.append(
        "Scores are deterministic priority weights — not AI confidence and not a guaranteed root cause."
    )
    return notes


def processing_result_to_response(
    result: ProcessingResult,
    source_name: str,
) -> AnalysisResponse:
    """Convert a ProcessingResult into an AnalysisResponse for the API."""

    clusters = [
        FailureClusterModel(
            start_line=cluster.start_line,
            end_line=cluster.end_line,
            lines=[_to_log_line(line) for line in cluster.lines],
        )
        for cluster in result.failure_clusters
    ]

    root_cause: Optional[RootCauseModel] = None
    if result.root_cause_candidate is not None:
        root_cause = RootCauseModel(
            line_number=result.root_cause_candidate.line_number,
            text=result.root_cause_candidate.text,
            category=result.root_cause_category or "unknown",
            priority_score=round(result.root_cause_score or 0.0, 3),
            score_reasons=list(result.score_reasons),
            explanation=result.root_cause_explanation or "",
        )

    redaction: Optional[RedactionStats] = None
    if result.redaction is not None:
        redaction = RedactionStats(
            applied=result.redaction.applied,
            replacement_count=result.redaction.replacement_count,
            matched_rules=list(result.redaction.matched_rules),
        )

    return AnalysisResponse(
        status="ok",
        source_name=source_name,
        total_lines=result.total_lines,
        error_count=result.error_count,
        warning_count=result.warning_count,
        failure_clusters=clusters,
        root_cause=root_cause,
        primary_evidence=[_to_log_line(l) for l in result.primary_evidence],
        supporting_evidence=[_to_log_line(l) for l in result.supporting_evidence],
        cascading_failures=[
            _to_log_line(l)
            for l in (result.cascading_evidence or result.cascading_failure_lines)
        ],
        relevant_context=[_to_log_line(l) for l in result.relevant_context],
        debugging_suggestions=_debugging_suggestions(result),
        redaction=redaction,
        analysis_notes=_analysis_notes(result),
    )
