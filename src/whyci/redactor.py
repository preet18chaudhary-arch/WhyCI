"""Deterministic secret redaction for WhyCI.

Detects and redacts common credential formats from CI logs before analysis
or external export, preserving useful diagnostic context and original line numbers.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from whyci.log_processor.processor import LogLine

REDACTED_MARKER: str = "[REDACTED]"

# 1. URL credentials: e.g. https://user:password@example.test/path
_URL_CRED_PATTERN = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://)([^:\s/@]+):([^@\s/]+)@"
)

# 2. HTTP Authorization & Proxy-Authorization headers
# e.g. Authorization: Bearer <token>, Authorization: Basic <creds>, Authorization: <raw>
_AUTH_HEADER_SCHEME_PATTERN = re.compile(
    r"""(?xi)
    \b(
        (?:Authorization|Proxy-Authorization)
        \s*:\s*
        (?:Bearer|Basic|Token)
        \s+
    )
    (
        (["'])(?:(?!\[REDACTED\]).)*?\3
        |
        (?:(?!\[REDACTED\])[^\s,;'\"\)]+)
    )
    """
)
_AUTH_HEADER_RAW_PATTERN = re.compile(
    r"""(?xi)
    \b(
        (?:Authorization|Proxy-Authorization)
        \s*:\s*
    )
    (?!(?:Bearer|Basic|Token\b|\[REDACTED\]))
    (
        (["'])(?:(?!\[REDACTED\]).)*?\3
        |
        (?:(?!\[REDACTED\])[^\s,;'\"\)]+)
    )
    """
)

# 3. Known vendor token prefixes
_PREFIXED_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    # GitHub personal access tokens (classic, fine-grained, app, oauth)
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{36,})\b"),
    re.compile(r"\b(github_pat_[A-Za-z0-9_]{50,})\b"),
    # Slack tokens
    re.compile(r"\b(xox[baprs]-[0-9a-zA-Z-]{10,})\b"),
    # AWS Access Key IDs
    re.compile(r"\b(A[KS]IA[0-9A-Z]{16,20})\b"),
    # Stripe API keys
    re.compile(r"\b([rs]k_(?:live|test)_[0-9a-zA-Z]{24,})\b"),
    # GitLab Personal Access Tokens
    re.compile(r"\b(glpat-[0-9a-zA-Z\-_]{20,})\b"),
    # Hugging Face tokens
    re.compile(r"\b(hf_[0-9a-zA-Z]{34,})\b"),
    # NPM access tokens
    re.compile(r"\b(npm_[0-9a-zA-Z]{36})\b"),
    # JSON Web Tokens (JWT)
    re.compile(r"\b(eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"),
)

# 4. Credential-bearing environment variable and key-value assignments
# e.g. PASSWORD=secret, AWS_SECRET_ACCESS_KEY=secret, "client_secret": "secret"
_ASSIGNMENT_PATTERN = re.compile(
    r"""(?xi)
    (?:\b|(?<=["']))
    (
        (?:export\s+)?
        ["']?
        [a-z0-9_-]*(?:secret|password|passwd|api[_-]?key|access[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key|session[_-]?token)
        [a-z0-9_-]*
        ["']?
        \s*[:=]\s*
    )
    (
        (["'])(?:(?!\[REDACTED\]).)*?\3
        |
        (?:(?!\[REDACTED\])[^\s"';,)])+
    )
    """
)

# Generic label assignments like token=... or apiKey: ...
_LABELED_KEY_PATTERN = re.compile(
    r"""(?xi)
    (?:\b|(?<=["']))
    (
        ["']?
        (?:token|api[_-]?key|client[_-]?secret)
        ["']?
        \s*[:=]\s*
    )
    (
        (["'])(?:(?!\[REDACTED\]).)*?\3
        |
        (?:(?!\[REDACTED\])[^\s"';,)])+
    )
    """
)

# 5. Multiline / inline private key blocks
_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9_-]+ )?PRIVATE KEY-----"
)


def redact_url_credentials(text: str) -> str:
    """Redact user:password credentials from URLs while preserving host and path."""
    def _replace_url(match: re.Match[str]) -> str:
        protocol = match.group(1)
        user = match.group(2)
        return f"{protocol}{user}:{REDACTED_MARKER}@"

    return _URL_CRED_PATTERN.sub(_replace_url, text)


def redact_authorization_headers(text: str) -> str:
    """Redact HTTP Authorization / Proxy-Authorization header values."""
    def _replace_auth(match: re.Match[str]) -> str:
        prefix = match.group(1)
        val = match.group(2)
        stripped = val.strip()
        if stripped == REDACTED_MARKER or stripped in (f'"{REDACTED_MARKER}"', f"'{REDACTED_MARKER}'"):
            return match.group(0)
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            quote = val[0]
            return f"{prefix}{quote}{REDACTED_MARKER}{quote}"
        return f"{prefix}{REDACTED_MARKER}"

    text = _AUTH_HEADER_SCHEME_PATTERN.sub(_replace_auth, text)
    text = _AUTH_HEADER_RAW_PATTERN.sub(_replace_auth, text)
    return text


def redact_prefixed_tokens(text: str) -> str:
    """Redact tokens with recognizable vendor prefixes."""
    for pattern in _PREFIXED_TOKEN_PATTERNS:
        text = pattern.sub(REDACTED_MARKER, text)
    return text


def redact_assignments(text: str) -> str:
    """Redact credential assignments like PASSWORD=secret or AWS_SECRET_ACCESS_KEY=val."""
    def _replace(match: re.Match[str]) -> str:
        prefix = match.group(1)
        val = match.group(2)
        stripped = val.strip()
        if stripped == REDACTED_MARKER or stripped in (f'"{REDACTED_MARKER}"', f"'{REDACTED_MARKER}'"):
            return match.group(0)

        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            quote = val[0]
            return f"{prefix}{quote}{REDACTED_MARKER}{quote}"
        return f"{prefix}{REDACTED_MARKER}"

    text = _ASSIGNMENT_PATTERN.sub(_replace, text)
    text = _LABELED_KEY_PATTERN.sub(_replace, text)
    return text


def redact_private_keys(text: str) -> str:
    """Redact PEM-formatted private key blocks."""
    return _PRIVATE_KEY_PATTERN.sub(REDACTED_MARKER, text)


def redact_text(text: str) -> str:
    """Apply all deterministic secret redactions to text while preserving context.

    Handles multiple secrets of different types on a single line and remains
    idempotent when run repeatedly.
    """
    text = redact_private_keys(text)
    text = redact_url_credentials(text)
    text = redact_authorization_headers(text)
    text = redact_assignments(text)
    text = redact_prefixed_tokens(text)
    return text


def redact_line(line: LogLine) -> LogLine:
    """Redact sensitive values from a LogLine, preserving its original line_number."""
    line_type = type(line)
    return line_type(
        line_number=line.line_number,
        text=redact_text(line.text),
    )


_PEM_BEGIN_PATTERN = re.compile(r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----")
_PEM_END_PATTERN = re.compile(r"-----END (?:[A-Z0-9_-]+ )?PRIVATE KEY-----")


def redact_log_lines(lines: Iterable[LogLine]) -> tuple[LogLine, ...]:
    """Redact sensitive values across an iterable of LogLines, preserving line numbers."""
    result: list[LogLine] = []
    in_pem_block = False

    for line in lines:
        text = line.text
        line_type = type(line)

        if in_pem_block:
            if _PEM_END_PATTERN.search(text):
                in_pem_block = False
            result.append(line_type(line_number=line.line_number, text=REDACTED_MARKER))
            continue

        if _PEM_BEGIN_PATTERN.search(text):
            if not _PEM_END_PATTERN.search(text):
                in_pem_block = True
            result.append(line_type(line_number=line.line_number, text=REDACTED_MARKER))
            continue

        result.append(redact_line(line))

    return tuple(result)


def contains_secret(text: str) -> bool:
    """Return True if the text contains credentials that would be redacted."""
    return redact_text(text) != text
