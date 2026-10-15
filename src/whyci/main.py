"""Command-line entry point for the local WhyCI log processor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from whyci.github_actions import WorkflowResult, process_workflow_archive
from whyci.log_processor import ProcessingResult, process_log_file
from whyci.log_processor.processor import LogLine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="WhyCI local prototype: scan a CI log or GitHub Actions workflow archive and rank root-cause candidates.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--log",
        help="Path to a single CI log file to process.",
    )
    group.add_argument(
        "--archive",
        "--zip",
        dest="archive",
        help="Path to a downloaded GitHub Actions workflow log ZIP archive.",
    )
    parser.add_argument(
        "--no-redact",
        action="store_true",
        help=(
            "Disable secret redaction on log lines (UNSAFE: allows raw credentials and secrets "
            "to appear in output; use only for offline debugging of non-sensitive logs). "
            "Redaction is enabled by default."
        ),
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


def format_workflow_summary(workflow: WorkflowResult) -> str:
    lines = [
        "WHYCI GITHUB ACTIONS WORKFLOW ANALYSIS",
        "",
        f"Archive: {workflow.archive_path}",
        f"Total logs processed: {workflow.total_jobs}",
        f"Logs with failures: {len(workflow.failing_jobs)}",
    ]
    if workflow.unsupported_files:
        lines.append(f"Unsupported files skipped: {len(workflow.unsupported_files)}")
    lines.append("")

    top_job = workflow.top_candidate_job
    if top_job is None or top_job.root_cause_candidate is None:
        lines.extend(
            [
                "LIKELY WORKFLOW ROOT-CAUSE CANDIDATE",
                "",
                "(no clear deterministic candidate across workflow logs)",
                "",
                "Why this was selected:",
                "* no high-priority cause signal was found in any workflow log",
            ]
        )
    else:
        candidate = top_job.root_cause_candidate
        lines.extend(
            [
                "LIKELY WORKFLOW ROOT-CAUSE CANDIDATE",
                "",
                f"Source log: {top_job.source_path}",
                f"Line {candidate.line_number}:",
                candidate.text,
                "",
                "Category:",
                top_job.root_cause_category or "unknown",
                "",
                "Heuristic score:",
                f"{top_job.root_cause_score:.2f}" if top_job.root_cause_score is not None else "n/a",
                "",
                "Why this was selected:",
            ]
        )
        if top_job.score_reasons:
            lines.extend(f"* {reason}" for reason in top_job.score_reasons)
        else:
            lines.append("* (none)")

        lines.extend(["", "Primary evidence:"])
        _append_line_list(lines, top_job.primary_evidence)

        lines.extend(["", "Supporting evidence:"])
        _append_line_list(lines, top_job.supporting_evidence)

        lines.extend(["", "Possible cascading failures:"])
        _append_line_list(lines, top_job.cascading_evidence or top_job.cascading_failure_lines)

        lines.extend(["", "Explanation:"])
        lines.append(
            top_job.root_cause_explanation
            or "WhyCI did not identify a clear root-cause candidate in this workflow log."
        )

    lines.extend(
        [
            "",
            "JOB SUMMARIES",
            "",
        ]
    )
    for job in workflow.job_results:
        cand_desc = (
            f"Line {job.root_cause_candidate.line_number}: {job.root_cause_candidate.text}"
            if job.root_cause_candidate
            else "(none)"
        )
        status = "FAILED" if job.error_count > 0 else "PASSED"
        lines.append(
            f"* {job.source_path} [{status}]: {job.error_count} error(s), "
            f"{job.warning_count} warning(s) - candidate: {cand_desc}"
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
    redact = not args.no_redact

    if args.archive:
        archive_path = Path(args.archive)
        try:
            workflow_result = process_workflow_archive(archive_path, redact=redact)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"error: could not read workflow archive: {exc}", file=sys.stderr)
            return 1

        print(format_workflow_summary(workflow_result))
        return 0

    log_path = Path(args.log)
    try:
        result = process_log_file(log_path, redact=redact)
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
