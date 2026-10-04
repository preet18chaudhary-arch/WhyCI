"""Structured evidence around a Phase 2 analysis result.

Separates the chosen candidate from supporting cluster lines, later cascade
signals, and nearby non-error context. Line numbers stay 1-based.
"""

from __future__ import annotations

from whyci.config import CONTEXT_LINE_WINDOW
from whyci.log_processor.analyzer import AnalysisResult, FailureCluster
from whyci.log_processor.processor import LogLine


def _candidate_cluster(analysis: AnalysisResult) -> FailureCluster | None:
    if analysis.root_cause_candidate is None:
        return None
    candidate_number = analysis.root_cause_candidate.line_number
    for cluster in analysis.failure_clusters:
        if any(line.line_number == candidate_number for line in cluster.lines):
            return cluster
    return None


def occupied_line_numbers(analysis: AnalysisResult) -> set[int]:
    """Line numbers already classified as primary, supporting, or cascading."""
    numbers: set[int] = set()
    for group in (
        analysis.primary_evidence,
        analysis.supporting_evidence,
        analysis.cascading_evidence,
        analysis.evidence_lines,
        analysis.cascading_failure_lines,
    ):
        numbers.update(line.line_number for line in group)
    if analysis.root_cause_candidate is not None:
        numbers.add(analysis.root_cause_candidate.line_number)
    return numbers


def extract_relevant_context(
    all_lines: list[LogLine] | tuple[LogLine, ...],
    analysis: AnalysisResult,
    window: int = CONTEXT_LINE_WINDOW,
) -> tuple[LogLine, ...]:
    """Return nearby lines around the candidate cluster that are not already evidence."""
    cluster = _candidate_cluster(analysis)
    if cluster is None:
        return ()

    occupied = occupied_line_numbers(analysis)
    low = max(1, cluster.start_line - window)
    high = cluster.end_line + window
    context: list[LogLine] = []
    for line in all_lines:
        if line.line_number < low:
            continue
        if line.line_number > high:
            break
        if line.line_number in occupied:
            continue
        if not line.text.strip():
            continue
        context.append(line)
    return tuple(context)
