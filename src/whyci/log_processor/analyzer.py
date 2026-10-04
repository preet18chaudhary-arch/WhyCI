"""Deterministic root-cause candidate analysis.

Scores and clusters error-like lines. This is a heuristic ranking, not a
guaranteed diagnosis and not model confidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from whyci.config import (
    ALL_SCORING_RULES,
    CAUSE_RULES,
    CLUSTER_LINE_GAP,
    GENERIC_SIGNAL_WEIGHT,
    MIN_CANDIDATE_SCORE,
    ScoringRule,
)
from whyci.log_processor.processor import LogLine

# Exit-status / annotation lines are too generic to call a clear candidate.
WEAK_TERMINAL_RULES = frozenset({"build_failed", "github_error_annotation", "generic_error"})

CATEGORY_NOUN_PHRASE = {
    "dependency": "a dependency failure",
    "infrastructure": "an infrastructure failure",
    "configuration": "a configuration failure",
    "authentication": "an authentication failure",
    "permission": "a permission failure",
    "compilation": "a compilation failure",
    "syntax": "a syntax error",
    "environment": "an environment/configuration failure",
    "test": "a test failure",
    "unknown": "a failure signal",
}


@dataclass(frozen=True)
class FailureCluster:
    """Nearby error-like lines that likely belong to one failure event."""

    lines: tuple[LogLine, ...]

    @property
    def start_line(self) -> int:
        return self.lines[0].line_number

    @property
    def end_line(self) -> int:
        return self.lines[-1].line_number


@dataclass(frozen=True)
class ScoredSignal:
    line: LogLine
    score: float
    kind: str
    matched_rules: tuple[str, ...]
    category: str
    rule_label: str


@dataclass(frozen=True)
class AnalysisResult:
    root_cause_candidate: LogLine | None
    root_cause_score: float | None
    root_cause_line_number: int | None
    evidence_lines: tuple[LogLine, ...]
    cascading_failure_lines: tuple[LogLine, ...]
    failure_clusters: tuple[FailureCluster, ...]
    root_cause_reasons: tuple[str, ...]
    root_cause_category: str | None = None
    root_cause_explanation: str | None = None
    score_reasons: tuple[str, ...] = ()
    primary_evidence: tuple[LogLine, ...] = ()
    supporting_evidence: tuple[LogLine, ...] = ()
    cascading_evidence: tuple[LogLine, ...] = ()


def _matching_rules(text: str, rules: tuple[ScoringRule, ...]) -> list[ScoringRule]:
    return [rule for rule in rules if rule.pattern.search(text)]


def score_error_line(line: LogLine) -> ScoredSignal:
    """Assign a transparent heuristic score to one error-like line."""
    cause_hits = _matching_rules(line.text, CAUSE_RULES)
    if cause_hits:
        best = max(cause_hits, key=lambda rule: rule.weight)
        return ScoredSignal(
            line=line,
            score=best.weight,
            kind="cause",
            matched_rules=tuple(rule.name for rule in cause_hits),
            category=best.category,
            rule_label=best.label,
        )

    other_hits = _matching_rules(line.text, ALL_SCORING_RULES)
    if other_hits:
        best = max(other_hits, key=lambda rule: rule.weight)
        return ScoredSignal(
            line=line,
            score=best.weight,
            kind=best.kind,
            matched_rules=tuple(rule.name for rule in other_hits),
            category=best.category,
            rule_label=best.label,
        )

    return ScoredSignal(
        line=line,
        score=GENERIC_SIGNAL_WEIGHT,
        kind="generic",
        matched_rules=("generic_error",),
        category="unknown",
        rule_label="generic error",
    )


def cluster_error_lines(
    error_lines: tuple[LogLine, ...] | list[LogLine],
    max_gap: int = CLUSTER_LINE_GAP,
) -> tuple[FailureCluster, ...]:
    """Group error lines that appear close together in the original log."""
    if not error_lines:
        return ()

    ordered = sorted(error_lines, key=lambda line: line.line_number)
    groups: list[list[LogLine]] = [[ordered[0]]]

    for line in ordered[1:]:
        previous = groups[-1][-1]
        if line.line_number - previous.line_number <= max_gap:
            groups[-1].append(line)
        else:
            groups.append([line])

    return tuple(FailureCluster(lines=tuple(group)) for group in groups)


def _select_candidate_cluster(
    clusters: tuple[FailureCluster, ...],
    scores_by_line: dict[int, ScoredSignal],
) -> FailureCluster | None:
    """Prefer the first cluster that contains a cause-like signal."""
    if not clusters:
        return None

    for cluster in clusters:
        if any(scores_by_line[line.line_number].kind == "cause" for line in cluster.lines):
            return cluster
    return clusters[0]


def _is_weak_terminal(signal: ScoredSignal) -> bool:
    return signal.kind != "cause" and all(name in WEAK_TERMINAL_RULES for name in signal.matched_rules)


def _mentions_database(lines: tuple[LogLine, ...] | list[LogLine]) -> bool:
    return any("database" in line.text.lower() or "postgres" in line.text.lower() for line in lines)


def _count_test_failures(lines: tuple[LogLine, ...]) -> int:
    return sum(1 for line in lines if "FAIL:" in line.text or "test failed" in line.text.lower())


def candidate_failure_phrase(chosen: ScoredSignal, supporting: tuple[LogLine, ...]) -> str:
    """Short noun phrase used in the human-readable explanation."""
    related = (chosen.line,) + supporting
    if chosen.category == "infrastructure" and _mentions_database(related):
        if "refused" in chosen.line.text.lower() or "connect" in chosen.line.text.lower():
            return "a database connection failure"
        return "a database initialization failure"
    if chosen.category == "dependency" and "module" in chosen.rule_label:
        return "a missing-module / dependency failure"
    return CATEGORY_NOUN_PHRASE.get(chosen.category, "a failure signal")


def build_score_reasons(
    chosen: ScoredSignal,
    supporting: tuple[LogLine, ...],
    cascading: tuple[LogLine, ...],
) -> tuple[str, ...]:
    """Explain the heuristic score in plain language (not AI confidence)."""
    reasons: list[str] = []
    if chosen.kind == "cause":
        reasons.append(
            f'"{chosen.rule_label}" matched a high-priority {chosen.category} rule'
        )
    else:
        reasons.append(
            f'"{chosen.rule_label}" was the strongest signal in the earliest failure cluster'
        )

    test_count = _count_test_failures(cascading)
    if test_count:
        reasons.append("it occurred before downstream test failures")
    elif cascading:
        reasons.append("it occurred before later failure signals")

    if supporting:
        if _mentions_database(supporting):
            reasons.append("nearby database initialization errors support the signal")
        else:
            reasons.append("nearby related error lines in the same cluster support the signal")

    return tuple(reasons)


def build_explanation(
    chosen: ScoredSignal,
    supporting: tuple[LogLine, ...],
    cascading: tuple[LogLine, ...],
) -> str:
    """Write a short candidate explanation; this is not a guaranteed diagnosis."""
    phrase = candidate_failure_phrase(chosen, supporting)
    sentences = [
        f"WhyCI identified {phrase} as the most likely root-cause candidate.",
    ]

    test_count = _count_test_failures(cascading)
    related = (chosen.line,) + supporting
    if _mentions_database(related) and test_count:
        sentences.append(
            "The database initialization failed before multiple downstream tests reported failures."
        )
    elif test_count:
        noun = "test failure" if test_count == 1 else "test failures"
        sentences.append(
            f"The signal occurred before {test_count} downstream {noun}."
        )
    elif cascading:
        sentences.append(
            f"The signal occurred before {len(cascading)} later failure signal(s)."
        )
    else:
        sentences.append("No later cascading failures were detected after this candidate.")

    return " ".join(sentences)


def _pick_cluster_candidate(
    cluster: FailureCluster,
    scores_by_line: dict[int, ScoredSignal],
) -> ScoredSignal:
    scored = [scores_by_line[line.line_number] for line in cluster.lines]
    return max(scored, key=lambda item: (item.score, -item.line.line_number))


def analyze_error_lines(error_lines: tuple[LogLine, ...] | list[LogLine]) -> AnalysisResult:
    """Rank error lines and separate a likely origin cluster from later symptoms."""
    empty = AnalysisResult(
        root_cause_candidate=None,
        root_cause_score=None,
        root_cause_line_number=None,
        evidence_lines=(),
        cascading_failure_lines=(),
        failure_clusters=(),
        root_cause_reasons=(),
        root_cause_category=None,
        root_cause_explanation=None,
        score_reasons=(),
        primary_evidence=(),
        supporting_evidence=(),
        cascading_evidence=(),
    )
    if not error_lines:
        return empty

    scored = [score_error_line(line) for line in error_lines]
    scores_by_line = {item.line.line_number: item for item in scored}
    clusters = cluster_error_lines(error_lines)
    candidate_cluster = _select_candidate_cluster(clusters, scores_by_line)
    if candidate_cluster is None:
        return empty

    chosen = _pick_cluster_candidate(candidate_cluster, scores_by_line)
    cluster_is_weak = all(
        _is_weak_terminal(scores_by_line[line.line_number]) for line in candidate_cluster.lines
    )
    if cluster_is_weak and chosen.score < MIN_CANDIDATE_SCORE:
        return AnalysisResult(
            root_cause_candidate=None,
            root_cause_score=None,
            root_cause_line_number=None,
            evidence_lines=(),
            cascading_failure_lines=(),
            failure_clusters=clusters,
            root_cause_reasons=(),
            root_cause_category=None,
            root_cause_explanation=None,
            score_reasons=(),
            primary_evidence=(),
            supporting_evidence=(),
            cascading_evidence=(),
        )

    supporting = tuple(
        line for line in candidate_cluster.lines if line.line_number != chosen.line.line_number
    )
    cascading = tuple(
        line
        for line in error_lines
        if line.line_number > candidate_cluster.end_line
    )
    score_reasons = build_score_reasons(chosen, supporting, cascading)
    explanation = build_explanation(chosen, supporting, cascading)
    primary = (chosen.line,)

    return AnalysisResult(
        root_cause_candidate=chosen.line,
        root_cause_score=chosen.score,
        root_cause_line_number=chosen.line.line_number,
        evidence_lines=supporting,
        cascading_failure_lines=cascading,
        failure_clusters=clusters,
        root_cause_reasons=score_reasons,
        root_cause_category=chosen.category,
        root_cause_explanation=explanation,
        score_reasons=score_reasons,
        primary_evidence=primary,
        supporting_evidence=supporting,
        cascading_evidence=cascading,
    )
