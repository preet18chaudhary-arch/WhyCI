"""Command-line entry point for the local WhyCI log processor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from whyci.log_processor import ProcessingResult, process_log_file
from whyci.log_processor.processor import LogLine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="WhyCI local prototype: scan a CI log and rank a root-cause candidate.",
    )
    parser.add_argument(
        "--log",
        required=True,
        help="Path to a CI log file to process.",
    )
    return parser


def _format_line(line: LogLine) -> str:
    return f"Line {line.line_number}: {line.text}"


def _append_line_list(lines: list[str], items: tuple[LogLine, ...]) -> None:
    if not items:
        lines.append("(none)")
        return
    lines.extend(_format_line(item) for item in items)


def format_summary(result: ProcessingResult) -> str:
    lines = [
        "WHYCI LOG ANALYSIS",
        "",
        f"Log file: {result.source_path}",
        f"Total lines: {result.total_lines}",
        f"Detected errors: {result.error_count}",
        f"Detected warnings: {result.warning_count}",
        "",
        "LIKELY ROOT-CAUSE CANDIDATE",
        "",
    ]

    if result.root_cause_candidate is None:
        lines.extend(
            [
                "(no clear deterministic candidate)",
                "",
                "Category:",
                "unknown",
                "",
                "Heuristic score:",
                "n/a",
                "",
                "Why this was selected:",
                "* no high-priority cause signal was found",
            ]
        )
    else:
        lines.extend(
            [
                f"Line {result.root_cause_candidate.line_number}:",
                result.root_cause_candidate.text,
                "",
                "Category:",
                result.root_cause_category or "unknown",
                "",
                "Heuristic score:",
                f"{result.root_cause_score:.2f}",
                "",
                "Why this was selected:",
            ]
        )
        if result.score_reasons:
            lines.extend(f"* {reason}" for reason in result.score_reasons)
        else:
            lines.append("* (none)")

    lines.extend(["", "Primary evidence:"])
    _append_line_list(lines, result.primary_evidence)

    lines.extend(["", "Supporting evidence:"])
    _append_line_list(lines, result.supporting_evidence)

    lines.extend(["", "Possible cascading failures:"])
    _append_line_list(lines, result.cascading_evidence or result.cascading_failure_lines)

    lines.extend(["", "Relevant context:"])
    _append_line_list(lines, result.relevant_context)

    lines.extend(["", "Secret redaction:"])
    if result.redaction is not None and result.redaction.applied:
        rule_list = ", ".join(result.redaction.matched_rules) or "(unnamed)"
        lines.append(
            f"applied ({result.redaction.replacement_count} replacement(s); rules: {rule_list})"
        )
    else:
        lines.append("not applied")

    lines.extend(["", "Explanation:"])
    lines.append(
        result.root_cause_explanation
        or "WhyCI did not identify a clear root-cause candidate in this log."
    )
    lines.extend(
        [
            "",
            "Note:",
            "This is a deterministic heuristic analysis, not a guaranteed root-cause diagnosis.",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    log_path = Path(args.log)

    try:
        result = process_log_file(log_path)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: could not read log file: {exc}", file=sys.stderr)
        return 1

    print(format_summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
