"""Deterministic secret redaction for CI log lines.

Patterns live in whyci.config. This module does not detect every possible
secret; it only applies the named rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from whyci.config import REDACTION_PLACEHOLDER, REDACTION_RULES
from whyci.log_processor.processor import LogLine


@dataclass(frozen=True)
class RedactionSummary:
    """How many configured secret patterns matched during processing."""

    applied: bool
    replacement_count: int
    matched_rules: tuple[str, ...]


@dataclass(frozen=True)
class LineRedaction:
    original: LogLine
    redacted: LogLine
    matched_rules: tuple[str, ...]


def redact_text(text: str) -> tuple[str, tuple[str, ...]]:
    """Replace configured secret values in one string with [REDACTED]."""
    current = text
    hits: list[str] = []
    for rule in REDACTION_RULES:
        current, count = rule.pattern.subn(rule.replacement, current)
        if count:
            hits.extend([rule.name] * count)
    return current, tuple(hits)


def redact_line(line: LogLine) -> LineRedaction:
    """Redact one log line without changing its original line number."""
    redacted_text, rules = redact_text(line.text)
    return LineRedaction(
        original=line,
        redacted=LogLine(line_number=line.line_number, text=redacted_text),
        matched_rules=rules,
    )


def redact_lines(lines: list[LogLine] | tuple[LogLine, ...]) -> tuple[LineRedaction, ...]:
    """Redact each line independently so 1-based numbering is preserved."""
    return tuple(redact_line(line) for line in lines)


def summarize_redactions(redacted: tuple[LineRedaction, ...]) -> RedactionSummary:
    ordered_rules: list[str] = []
    seen: set[str] = set()
    replacement_count = 0
    for item in redacted:
        replacement_count += len(item.matched_rules)
        for name in item.matched_rules:
            if name not in seen:
                seen.add(name)
                ordered_rules.append(name)
    return RedactionSummary(
        applied=replacement_count > 0,
        replacement_count=replacement_count,
        matched_rules=tuple(ordered_rules),
    )


def redacted_line_map(redacted: tuple[LineRedaction, ...]) -> dict[int, LogLine]:
    """Map original 1-based line numbers to redacted LogLine copies."""
    return {item.redacted.line_number: item.redacted for item in redacted}


def remap_line(line: LogLine | None, by_number: dict[int, LogLine]) -> LogLine | None:
    if line is None:
        return None
    return by_number.get(line.line_number, line)


def remap_lines(lines: tuple[LogLine, ...], by_number: dict[int, LogLine]) -> tuple[LogLine, ...]:
    return tuple(by_number.get(line.line_number, line) for line in lines)


# Re-export so callers can document the replacement token without importing config.
PLACEHOLDER = REDACTION_PLACEHOLDER
