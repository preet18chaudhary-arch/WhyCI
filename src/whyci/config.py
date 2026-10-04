"""Shared configuration for the local log-processing prototype."""

from __future__ import annotations

import re
from dataclasses import dataclass

# These patterns flag likely failure *signals* in CI output.
# They do not identify the true root cause of a job failure.
ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"##\[error\]", re.IGNORECASE),
    re.compile(r"\bnpm ERR!", re.IGNORECASE),
    re.compile(r"\bfatal:", re.IGNORECASE),
    re.compile(r"\bTraceback\b"),
    re.compile(r"\bException\b"),
    re.compile(r"\bFAILED\b"),
    re.compile(r"\bFAIL:"),
    re.compile(r"\bERROR\b", re.IGNORECASE),
    re.compile(r"\bError:"),
)

WARNING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"##\[warning\]", re.IGNORECASE),
    re.compile(r"\bnpm WARN\b", re.IGNORECASE),
    re.compile(r"\bWARNING\b", re.IGNORECASE),
    re.compile(r"\bWarning:"),
    re.compile(r"\bWARN:", re.IGNORECASE),
)

LOG_ENCODING = "utf-8"

# Consecutive error lines whose numbers differ by at most this gap form a cluster.
CLUSTER_LINE_GAP = 3

# Heuristic floor for calling a signal a "clear" root-cause candidate.
# This is not AI confidence.
MIN_CANDIDATE_SCORE = 0.45

GENERIC_SIGNAL_WEIGHT = 0.30


VALID_CATEGORIES = (
    "dependency",
    "infrastructure",
    "configuration",
    "authentication",
    "permission",
    "compilation",
    "syntax",
    "environment",
    "test",
    "unknown",
)


@dataclass(frozen=True)
class ScoringRule:
    """Named, weighted pattern used by the deterministic analyzer."""

    name: str
    pattern: re.Pattern[str]
    weight: float
    kind: str  # "cause" or "cascade"
    category: str
    label: str


def _rule(
    name: str,
    pattern: str,
    weight: float,
    kind: str,
    category: str,
    label: str,
) -> ScoringRule:
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Unknown failure category: {category}")
    return ScoringRule(
        name=name,
        pattern=re.compile(pattern, re.IGNORECASE),
        weight=weight,
        kind=kind,
        category=category,
        label=label,
    )


# Higher weights mark signals that often explain *why* later steps failed.
CAUSE_RULES: tuple[ScoringRule, ...] = (
    _rule("connection_refused", r"connection refused", 0.92, "cause", "infrastructure", "connection refused"),
    _rule("cannot_connect", r"cannot connect|can't connect|could not connect|unable to connect", 0.88, "cause", "infrastructure", "cannot connect"),
    _rule("command_not_found", r"command not found|not recognized as an internal or external command", 0.90, "cause", "infrastructure", "command not found"),
    _rule("module_not_found", r"module not found|cannot find module|modulenotfounderror|no module named", 0.90, "cause", "dependency", "cannot find module"),
    _rule("dependency_resolution", r"could not resolve|unable to resolve dependency|erresolve|dependency conflict", 0.88, "cause", "dependency", "dependency conflict"),
    _rule("permission_denied", r"permission denied|access denied|\beacces\b", 0.86, "cause", "permission", "permission denied"),
    _rule("authentication_failure", r"authentication failed|authentication failure|unauthorized|invalid credentials|could not read username", 0.84, "cause", "authentication", "authentication failure"),
    _rule("missing_env", r"missing environment variable|environment variable .* not (set|defined)|is not set", 0.86, "cause", "environment", "missing environment variable"),
    _rule("version_mismatch", r"version mismatch|incompatible version|engine-strict", 0.82, "cause", "dependency", "version mismatch"),
    _rule("compilation_failure", r"compilation failed|compile error|failed to compile", 0.85, "cause", "compilation", "compilation failure"),
    _rule("syntax_error", r"syntaxerror|syntax error", 0.88, "cause", "syntax", "syntax error"),
    _rule("configuration_error", r"configuration error|invalid configuration|misconfigured", 0.84, "cause", "configuration", "configuration error"),
    _rule("setup_failure", r"failed to (initialize|initialise|init|start|setup)|initialization failed|database init", 0.87, "cause", "infrastructure", "failed setup/init"),
)

# Lower weights mark signals that often report *that* something failed downstream.
CASCADE_RULES: tuple[ScoringRule, ...] = (
    _rule("assertion_failed", r"assertion (error|failed)|expected .+, (got|received)", 0.34, "cascade", "test", "assertion failed"),
    _rule("named_test_fail", r"\bFAIL:", 0.28, "cascade", "test", "named test failure"),
    _rule("tests_failed", r"\btests? failed\b|npm ERR! Test failed", 0.24, "cascade", "test", "tests failed"),
    _rule("build_failed", r"\bbuild failed\b|process completed with exit code", 0.22, "cascade", "unknown", "generic build/process failure"),
    _rule("generic_failed", r"\bFAILED\b", 0.25, "cascade", "unknown", "generic FAILED"),
    _rule("github_error_annotation", r"##\[error\]", 0.22, "cascade", "unknown", "GitHub error annotation"),
    _rule("traceback", r"\bTraceback\b", 0.33, "cascade", "unknown", "Python traceback"),
)

ALL_SCORING_RULES: tuple[ScoringRule, ...] = CAUSE_RULES + CASCADE_RULES

# Nearby non-evidence lines around the candidate cluster shown as context.
CONTEXT_LINE_WINDOW = 2

REDACTION_PLACEHOLDER = "[REDACTED]"

# Named keys whose assigned values are treated as secrets.
# This is a transparent allowlist, not a complete secret detector.
SENSITIVE_ASSIGNMENT_KEYS = (
    r"api[_-]?key",
    r"access[_-]?token",
    r"auth[_-]?token",
    r"client[_-]?secret",
    r"secret[_-]?key",
    r"secret",
    r"password",
    r"passwd",
    r"pwd",
    r"token",
)


@dataclass(frozen=True)
class RedactionRule:
    """Named regex used to replace a secret value with REDACTION_PLACEHOLDER."""

    name: str
    pattern: re.Pattern[str]
    replacement: str
    description: str


def _redaction_rule(name: str, pattern: str, replacement: str, description: str) -> RedactionRule:
    return RedactionRule(
        name=name,
        pattern=re.compile(pattern),
        replacement=replacement,
        description=description,
    )


_SENSITIVE_KEY = "(?:" + "|".join(SENSITIVE_ASSIGNMENT_KEYS) + ")"
_NOT_PLACEHOLDER = r"(?!\[REDACTED\])"
_SECRET_VALUE = rf"""(?:"[^"]*"|'[^']*'|{_NOT_PLACEHOLDER}[^\s,;]+)"""

# Assignments and Bearer run first so a token inside KEY=value is one replacement.
# Raw token formats then catch secrets that are not named assignments.
REDACTION_RULES: tuple[RedactionRule, ...] = (
    _redaction_rule(
        "quoted_assignment",
        rf"(?i)([\"']{_SENSITIVE_KEY}[\"']\s*:\s*){_SECRET_VALUE}",
        rf"\1{REDACTION_PLACEHOLDER}",
        "JSON/quoted sensitive key/value pairs",
    ),
    _redaction_rule(
        "env_assignment",
        rf"(?i)(\b{_SENSITIVE_KEY})(\s*[=:]\s*){_SECRET_VALUE}",
        rf"\1\2{REDACTION_PLACEHOLDER}",
        "PASSWORD=, API_KEY=, TOKEN= and similar assignments",
    ),
    _redaction_rule(
        "bearer_token",
        r"(?i)(\b(?:Authorization:\s*)?Bearer\s+)" + _SECRET_VALUE,
        rf"\1{REDACTION_PLACEHOLDER}",
        "Authorization Bearer headers and Bearer tokens",
    ),
    _redaction_rule(
        "github_token",
        r"(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{36})",
        REDACTION_PLACEHOLDER,
        "GitHub personal, OAuth, and fine-grained token prefixes",
    ),
    _redaction_rule(
        "aws_access_key_id",
        r"AKIA[0-9A-Z]{16}",
        REDACTION_PLACEHOLDER,
        "AWS-style access key IDs",
    ),
)
