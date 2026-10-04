"""Local CI log loader and signal detector.

This module classifies error/warning signals and attaches a deterministic
root-cause *candidate* analysis. It does not claim a guaranteed root cause.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from whyci.config import CAUSE_RULES, ERROR_PATTERNS, LOG_ENCODING, WARNING_PATTERNS

if TYPE_CHECKING:
    from whyci.log_processor.analyzer import FailureCluster
    from whyci.log_processor.redactor import RedactionSummary


@dataclass(frozen=True)
class LogLine:
    """A single log line with its original 1-based line number."""

    line_number: int
    text: str


@dataclass(frozen=True)
class ProcessingResult:
    """Structured output of the log scan plus heuristic analysis."""

    source_path: Path
    total_lines: int
    error_lines: tuple[LogLine, ...]
    warning_lines: tuple[LogLine, ...]
    root_cause_candidate: LogLine | None = None
    root_cause_score: float | None = None
    root_cause_line_number: int | None = None
    evidence_lines: tuple[LogLine, ...] = ()
    cascading_failure_lines: tuple[LogLine, ...] = ()
    failure_clusters: tuple[FailureCluster, ...] = ()
    root_cause_reasons: tuple[str, ...] = ()
    root_cause_category: str | None = None
    root_cause_explanation: str | None = None
    score_reasons: tuple[str, ...] = ()
    primary_evidence: tuple[LogLine, ...] = ()
    supporting_evidence: tuple[LogLine, ...] = ()
    cascading_evidence: tuple[LogLine, ...] = ()
    relevant_context: tuple[LogLine, ...] = ()
    redaction: RedactionSummary | None = None

    @property
    def error_count(self) -> int:
        return len(self.error_lines)

    @property
    def warning_count(self) -> int:
        return len(self.warning_lines)


def load_log_lines(log_path: Path) -> list[LogLine]:
    """Read a log file and preserve original line numbers."""
    if not log_path.is_file():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    lines: list[LogLine] = []
    with log_path.open(encoding=LOG_ENCODING, errors="replace") as handle:
        for index, raw_line in enumerate(handle, start=1):
            lines.append(LogLine(line_number=index, text=raw_line.rstrip("\r\n")))
    return lines


def is_error_line(text: str) -> bool:
    """Return True if the line matches a known error-like pattern."""
    return any(pattern.search(text) for pattern in ERROR_PATTERNS)


def is_warning_line(text: str) -> bool:
    """Return True if the line matches a known warning-like pattern."""
    return any(pattern.search(text) for pattern in WARNING_PATTERNS)


def is_cause_signal(text: str) -> bool:
    """Return True if the line matches a high-priority cause pattern."""
    return any(rule.pattern.search(text) for rule in CAUSE_RULES)


def classify_lines(lines: list[LogLine]) -> tuple[tuple[LogLine, ...], tuple[LogLine, ...]]:
    """Split lines into error-like and warning-like groups.

    Cause-pattern matches are included as error-like signals even without a
    generic ERROR/FAIL token. A line that matches both error and warning is
    treated as an error so it is not counted twice.
    """
    errors: list[LogLine] = []
    warnings: list[LogLine] = []

    for line in lines:
        if is_error_line(line.text) or is_cause_signal(line.text):
            errors.append(line)
        elif is_warning_line(line.text):
            warnings.append(line)

    return tuple(errors), tuple(warnings)


def process_log_file(log_path: str | Path) -> ProcessingResult:
    """Load a CI log, detect signals, and attach a heuristic candidate analysis."""
    from whyci.log_processor.analyzer import FailureCluster, analyze_error_lines
    from whyci.log_processor.evidence import extract_relevant_context
    from whyci.log_processor.redactor import (
        redact_lines,
        redacted_line_map,
        remap_line,
        remap_lines,
        summarize_redactions,
    )

    path = Path(log_path)
    lines = load_log_lines(path)
    error_lines, warning_lines = classify_lines(lines)
    analysis = analyze_error_lines(error_lines)
    context_lines = extract_relevant_context(lines, analysis)

    redacted = redact_lines(lines)
    by_number = redacted_line_map(redacted)
    summary = summarize_redactions(redacted)

    return ProcessingResult(
        source_path=path,
        total_lines=len(lines),
        error_lines=remap_lines(error_lines, by_number),
        warning_lines=remap_lines(warning_lines, by_number),
        root_cause_candidate=remap_line(analysis.root_cause_candidate, by_number),
        root_cause_score=analysis.root_cause_score,
        root_cause_line_number=analysis.root_cause_line_number,
        evidence_lines=remap_lines(analysis.evidence_lines, by_number),
        cascading_failure_lines=remap_lines(analysis.cascading_failure_lines, by_number),
        failure_clusters=tuple(
            FailureCluster(lines=remap_lines(cluster.lines, by_number))
            for cluster in analysis.failure_clusters
        ),
        root_cause_reasons=analysis.root_cause_reasons,
        root_cause_category=analysis.root_cause_category,
        root_cause_explanation=analysis.root_cause_explanation,
        score_reasons=analysis.score_reasons,
        primary_evidence=remap_lines(analysis.primary_evidence, by_number),
        supporting_evidence=remap_lines(analysis.supporting_evidence, by_number),
        cascading_evidence=remap_lines(analysis.cascading_evidence, by_number),
        relevant_context=remap_lines(context_lines, by_number),
        redaction=summary,
    )
