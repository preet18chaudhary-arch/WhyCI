from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from whyci.log_processor.processor import LogLine, process_log_file
from whyci.main import format_summary, main
from whyci.redactor import (
    contains_secret,
    redact_assignments,
    redact_authorization_headers,
    redact_line,
    redact_log_lines,
    redact_prefixed_tokens,
    redact_text,
    redact_url_credentials,
)


def _write_log(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "ci.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_redact_url_credentials() -> None:
    text = "Connecting to https://user:password@example.test/path"
    redacted = redact_url_credentials(text)
    assert redacted == "Connecting to https://user:[REDACTED]@example.test/path"
    assert "password" not in redacted

    db_url = "postgres://dbadmin:my_s3cr3t_pass@localhost:5432/app_db"
    assert redact_url_credentials(db_url) == "postgres://dbadmin:[REDACTED]@localhost:5432/app_db"

    http_url = "http://admin:pass@10.0.0.1:8080/v1/health"
    assert redact_url_credentials(http_url) == "http://admin:[REDACTED]@10.0.0.1:8080/v1/health"


def test_redact_authorization_headers() -> None:
    bearer = "curl -H 'Authorization: Bearer my-secret-bearer-token' https://api.test"
    assert redact_authorization_headers(bearer) == "curl -H 'Authorization: Bearer [REDACTED]' https://api.test"

    basic = "Authorization: Basic dXNlcjpwYXNz"
    assert redact_authorization_headers(basic) == "Authorization: Basic [REDACTED]"

    raw = "Authorization: my-custom-secret-token"
    assert redact_authorization_headers(raw) == "Authorization: [REDACTED]"

    proxy = "Proxy-Authorization: Basic cHJveHk6c2VjcmV0"
    assert redact_authorization_headers(proxy) == "Proxy-Authorization: Basic [REDACTED]"

    lower = "authorization: bearer lowercase-token"
    assert redact_authorization_headers(lower) == "authorization: bearer [REDACTED]"


def test_redact_prefixed_tokens() -> None:
    github_pat = "Failed with token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890 in request"
    assert redact_prefixed_tokens(github_pat) == "Failed with token [REDACTED] in request"

    fine_grained = "Using github_pat_1111111111111111111111111111111111111111111111111111111111111111111111111111111111"
    assert redact_prefixed_tokens(fine_grained) == "Using [REDACTED]"

    slack = "Slack alert posted with xoxb-123456789012-1234567890123-abcdef123456"
    assert redact_prefixed_tokens(slack) == "Slack alert posted with [REDACTED]"

    aws_key = "Found AWS key AKIAIOSFODNN7EXAMPLE in config"
    assert redact_prefixed_tokens(aws_key) == "Found AWS key [REDACTED] in config"

    stripe = "Stripe charge failed with " + "sk_live_" + "51Abcdefghijklmnopqrstuvwx"
    assert redact_prefixed_tokens(stripe) == "Stripe charge failed with [REDACTED]"

    gitlab = "GitLab PAT glpat-abcdefghijklmnopqrst failed"
    assert redact_prefixed_tokens(gitlab) == "GitLab PAT [REDACTED] failed"

    hf = "HuggingFace token hf_abcdefghijklmnopqrstuvwxyz01234567"
    assert redact_prefixed_tokens(hf) == "HuggingFace token [REDACTED]"

    npm = "npm login token npm_abcdefghijklmnopqrstuvwxyz0123456789"
    assert redact_prefixed_tokens(npm) == "npm login token [REDACTED]"


def test_redact_password_and_secret_assignments() -> None:
    unquoted = "Setting PASSWORD=my-secret-value in environment"
    assert redact_assignments(unquoted) == "Setting PASSWORD=[REDACTED] in environment"

    quoted_double = 'Setting password="my-secret-value" for user'
    assert redact_assignments(quoted_double) == 'Setting password="[REDACTED]" for user'

    quoted_single = "Setting password='my-secret-value' for user"
    assert redact_assignments(quoted_single) == "Setting password='[REDACTED]' for user"

    db_pass = "Database init failed: db_password=db_secret_999 connection refused"
    assert redact_assignments(db_pass) == "Database init failed: db_password=[REDACTED] connection refused"

    secret_assign = "SECRET=super-secret-key-12345"
    assert redact_assignments(secret_assign) == "SECRET=[REDACTED]"

    json_client_secret = '{"client_secret": "my-super-secret"}'
    assert redact_assignments(json_client_secret) == '{"client_secret": "[REDACTED]"}'

    yaml_api_key = "api_key: my-super-secret-key"
    assert redact_assignments(yaml_api_key) == "api_key: [REDACTED]"


def test_redact_credential_environment_variables() -> None:
    aws_secret = "AWS_SECRET_ACCESS_KEY=example-secret-access-key"
    assert redact_assignments(aws_secret) == "AWS_SECRET_ACCESS_KEY=[REDACTED]"

    export_aws = "export AWS_SECRET_ACCESS_KEY=example-secret-access-key"
    assert redact_assignments(export_aws) == "export AWS_SECRET_ACCESS_KEY=[REDACTED]"

    gh_token = "GITHUB_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
    assert redact_text(gh_token) == "GITHUB_TOKEN=[REDACTED]"

    aws_access = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
    assert redact_text(aws_access) == "AWS_ACCESS_KEY_ID=[REDACTED]"


def test_redact_multiple_secrets_on_single_line() -> None:
    line = (
        "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE "
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY "
        "PASSWORD=my-secret-value "
        "https://user:dbpass@example.test/path "
        "Authorization: Bearer secret-bearer-token"
    )
    expected = (
        "export AWS_ACCESS_KEY_ID=[REDACTED] "
        "AWS_SECRET_ACCESS_KEY=[REDACTED] "
        "PASSWORD=[REDACTED] "
        "https://user:[REDACTED]@example.test/path "
        "Authorization: Bearer [REDACTED]"
    )
    assert redact_text(line) == expected


def test_preserves_original_line_numbers() -> None:
    line = LogLine(line_number=42, text="Error: failed with PASSWORD=secret-pass-123")
    redacted = redact_line(line)

    assert redacted.line_number == 42
    assert redacted.text == "Error: failed with PASSWORD=[REDACTED]"

    lines = [
        LogLine(10, "Starting job"),
        LogLine(25, "AWS_SECRET_ACCESS_KEY=secret-access-key"),
        LogLine(100, "FAIL: test failed with token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"),
    ]
    redacted_lines = redact_log_lines(lines)
    assert [line.line_number for line in redacted_lines] == [10, 25, 100]
    assert redacted_lines[0].text == "Starting job"
    assert redacted_lines[1].text == "AWS_SECRET_ACCESS_KEY=[REDACTED]"
    assert redacted_lines[2].text == "FAIL: test failed with token [REDACTED]"


def test_preserves_diagnostic_context() -> None:
    line = "Error: Database connection refused at https://postgres:superpass123@db.internal:5432/app"
    redacted = redact_text(line)

    assert "Error: Database connection refused at https://postgres:[REDACTED]@db.internal:5432/app" == redacted
    assert "Database connection refused" in redacted
    assert "postgres" in redacted
    assert "db.internal:5432/app" in redacted
    assert "superpass123" not in redacted


def test_idempotence() -> None:
    samples = [
        "PASSWORD=my-secret-value",
        'password="my-secret-value"',
        "Authorization: Bearer secret-token-value",
        "Authorization: Basic dXNlcjpwYXNz",
        "https://user:password@example.test/path",
        "AWS_SECRET_ACCESS_KEY=example-secret",
        "Token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
        "Key AKIAIOSFODNN7EXAMPLE",
        "api_key: my-secret-api-key-999",
        '{"client_secret": "topsecret"}',
        "plain text with no secret at all",
    ]
    for sample in samples:
        once = redact_text(sample)
        twice = redact_text(once)
        assert once == twice, f"Idempotence failed for: {sample}"


def test_non_secret_lines_remain_unchanged() -> None:
    normal_lines = [
        "2026-10-04T09:12:01.001Z ##[group]Run npm ci",
        "npm WARN deprecated inflight@1.0.6: This module is not supported",
        "FAIL: src/auth.test.js",
        "Error: expected 200, received 401",
        "Database connection refused at postgres:5432",
        "Build completed with failures",
    ]
    for line in normal_lines:
        assert redact_text(line) == line
        assert not contains_secret(line)


def test_process_log_file_redacts_by_default(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "Starting workflow",
            "export AWS_SECRET_ACCESS_KEY=my-super-secret-value",
            "Error: Cannot connect to database at https://dbuser:mypassword123@postgres.internal:5432",
            "Database connection refused with PASSWORD=my-secret-db-pass",
            "FAIL: test_login failed with Authorization: Bearer token-xyz-789",
        ],
    )
    result = process_log_file(log_path)

    # Secrets must not appear in any result fields
    assert "mypassword123" not in result.root_cause_candidate.text
    assert "my-secret-db-pass" not in result.root_cause_candidate.text
    assert "token-xyz-789" not in str(result.cascading_failure_lines)
    assert "[REDACTED]" in result.root_cause_candidate.text

    # Diagnostic context and ranking preserved
    assert result.root_cause_candidate.line_number == 4
    assert result.root_cause_category == "infrastructure"
    assert result.root_cause_score is not None and result.root_cause_score >= 0.90
    assert any("[REDACTED]" in line.text for line in result.primary_evidence)
    assert any("[REDACTED]" in line.text for line in result.supporting_evidence)


def test_process_log_file_allows_disabling_redaction(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "Error: Cannot connect to database with PASSWORD=rawsecret",
            "Database connection refused",
        ],
    )
    unredacted = process_log_file(log_path, redact=False)
    assert "rawsecret" in unredacted.error_lines[0].text


def test_cli_integration_with_redaction(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "Error: Cannot connect to database",
            "Database connection refused at https://admin:supersecret@db:5432",
            "FAIL: user test",
        ],
    )
    exit_code = main(["--log", str(log_path)])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "supersecret" not in captured.out
    assert "https://admin:[REDACTED]@db:5432" in captured.out


def test_synthetic_secrets_never_appear_in_any_processing_result_field_or_cli_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secrets = {
        "aws_key": "AKIAIOSFODNN7EXAMPLE",
        "aws_secret": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "password": "super-secret-password-xyz123",
        "url_pass": "db_pass_987654321",
        "bearer_token": "secret-bearer-token-val-456",
        "gh_token": "ghp_111111111111111111111111111111111111",
        "stripe_key": "sk_live_" + "51Abcdefghijklmnopqrstuvwx",
        "slack_token": "xoxb-123456789012-1234567890123-abcdef123456",
        "raw_secret": "top-secret-config-value-999",
    }

    log_path = _write_log(
        tmp_path,
        [
            "2026-10-15T12:00:00Z Starting CI job",
            f"2026-10-15T12:00:01Z export AWS_ACCESS_KEY_ID={secrets['aws_key']} AWS_SECRET_ACCESS_KEY={secrets['aws_secret']}",
            f"2026-10-15T12:00:02Z Error: Cannot connect to database at https://admin:{secrets['url_pass']}@db.internal:5432",
            f"2026-10-15T12:00:03Z Database connection refused with PASSWORD={secrets['password']}",
            f"2026-10-15T12:00:04Z Warning: stripe check failed with {secrets['stripe_key']}",
            f"2026-10-15T12:00:05Z FAIL: auth test failed with Authorization: Bearer {secrets['bearer_token']}",
            f"2026-10-15T12:00:06Z FAIL: slack alert with {secrets['slack_token']} and token={secrets['gh_token']}",
            f"2026-10-15T12:00:07Z SECRET={secrets['raw_secret']}",
            "2026-10-15T12:00:08Z ##[error]Process completed with exit code 1.",
        ],
    )

    result = process_log_file(log_path, redact=True)

    # Collect all text representation from all fields of ProcessingResult
    all_result_texts = [
        result.root_cause_candidate.text if result.root_cause_candidate else "",
        result.root_cause_explanation or "",
        " ".join(result.score_reasons),
        " ".join(line.text for line in result.error_lines),
        " ".join(line.text for line in result.warning_lines),
        " ".join(line.text for line in result.primary_evidence),
        " ".join(line.text for line in result.supporting_evidence),
        " ".join(line.text for line in result.cascading_evidence),
        " ".join(line.text for line in result.cascading_failure_lines),
        " ".join(line.text for cluster in result.failure_clusters for line in cluster.lines),
    ]

    formatted_summary = format_summary(result)
    all_result_texts.append(formatted_summary)

    # Run CLI and capture stdout
    exit_code = main(["--log", str(log_path)])
    assert exit_code == 0
    cli_out = capsys.readouterr().out
    all_result_texts.append(cli_out)

    combined_output = "\n".join(all_result_texts)

    # Prove that NOT A SINGLE synthetic secret appears anywhere
    for name, secret_val in secrets.items():
        assert secret_val not in combined_output, f"Synthetic secret '{name}' leaked into output!"


def test_multiline_pem_private_key_redaction(tmp_path: Path) -> None:
    pem_key_body = "MIIEowIBAAKCAQEA0Y1+syntheticprivatekeydata1234567890abcdef=="
    log_path = _write_log(
        tmp_path,
        [
            "2026-10-15T10:00:00Z Initializing deployment credentials",
            "-----BEGIN RSA PRIVATE KEY-----",
            pem_key_body,
            "anotherlineofprivatekeymaterialnotreal==",
            "-----END RSA PRIVATE KEY-----",
            "2026-10-15T10:00:05Z Deployment continues",
        ],
    )

    result = process_log_file(log_path, redact=True)

    # Verify line count and line numbers
    assert result.total_lines == 6
    lines = [result.root_cause_candidate] if result.root_cause_candidate else []
    for line in result.error_lines:
        assert pem_key_body not in line.text

    # Directly check load_log_lines with redact=True
    from whyci.log_processor.processor import load_log_lines
    redacted_lines = load_log_lines(log_path, redact=True)
    assert len(redacted_lines) == 6
    assert [line.line_number for line in redacted_lines] == [1, 2, 3, 4, 5, 6]

    # Verify PEM block was completely replaced with [REDACTED]
    assert redacted_lines[0].text == "2026-10-15T10:00:00Z Initializing deployment credentials"
    assert redacted_lines[1].text == "[REDACTED]"
    assert redacted_lines[2].text == "[REDACTED]"
    assert redacted_lines[3].text == "[REDACTED]"
    assert redacted_lines[4].text == "[REDACTED]"
    assert redacted_lines[5].text == "2026-10-15T10:00:05Z Deployment continues"
    assert pem_key_body not in "\n".join(line.text for line in redacted_lines)


def test_ordinary_text_is_not_unnecessarily_redacted() -> None:
    safe_samples = [
        "the token expired",
        "The token expired",
        "Authentication token expired: please log in again",
        "password mismatch: could not verify hash",
        "Invalid password specified by user",
        "secret recipe for test cookies",
        "api key not found in header",
        "session token invalid or expired",
        "token refresh failed due to network timeout",
        "password incorrect for user admin",
        "process completed with exit code 0",
        "status: token expired",
    ]
    for sample in safe_samples:
        assert redact_text(sample) == sample, f"Falsely redacted: {sample}"
        assert not contains_secret(sample), f"Falsely identified secret in: {sample}"


def test_1_based_line_numbers_remain_correct_after_redaction(tmp_path: Path) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "Line 1 normal",
            "Line 2 export AWS_SECRET_ACCESS_KEY=my-secret-key-1",
            "Line 3 normal",
            "Line 4 Error: Cannot connect to database",
            "Line 5 Database connection refused at https://u:p@db:5432",
            "Line 6 PASSWORD=secret-pass",
            "Line 7 normal",
            "Line 8 FAIL: test_order",
        ],
    )
    result = process_log_file(log_path, redact=True)

    assert result.total_lines == 8
    # Error lines detected at lines 4, 5, 8
    detected_line_numbers = [line.line_number for line in result.error_lines]
    assert 4 in detected_line_numbers
    assert 5 in detected_line_numbers
    assert 8 in detected_line_numbers

    # Candidate line number
    assert result.root_cause_candidate is not None
    assert result.root_cause_candidate.line_number == 5
    assert result.root_cause_line_number == 5
    assert result.primary_evidence[0].line_number == 5


def test_redaction_occurs_before_classification_and_scoring(tmp_path: Path) -> None:
    # A line where sensitive credentials might confuse or appear alongside cause patterns
    log_path = _write_log(
        tmp_path,
        [
            "Error: Database connection refused with PASSWORD=supersecretpassword123",
            "FAIL: test failed",
        ],
    )
    result = process_log_file(log_path, redact=True)

    # Candidate must be classified and scored properly from the redacted signal
    assert result.root_cause_candidate is not None
    assert result.root_cause_candidate.line_number == 1
    assert "supersecretpassword123" not in result.root_cause_candidate.text
    assert "Database connection refused with PASSWORD=[REDACTED]" in result.root_cause_candidate.text
    assert result.root_cause_category == "infrastructure"
    assert result.root_cause_score is not None and result.root_cause_score >= 0.90


def test_no_redact_help_and_default_behavior() -> None:
    from whyci.main import build_parser

    parser = build_parser()
    help_text = " ".join(parser.format_help().split())

    # Verify explicitly documented as unsafe and default behavior stated
    assert "--no-redact" in help_text
    assert "UNSAFE" in help_text
    assert "Redaction is enabled by default" in help_text

    # Default value must be False (meaning redaction remains enabled)
    parsed = parser.parse_args(["--log", "dummy.log"])
    assert parsed.no_redact is False


def test_distinguish_observed_evidence_from_heuristic_explanation_and_acknowledge_uncertainty(
    tmp_path: Path,
) -> None:
    log_path = _write_log(
        tmp_path,
        [
            "Error: Cannot connect to database",
            "Database connection refused at postgres:5432",
            "FAIL: user test",
        ],
    )
    result = process_log_file(log_path)

    # 1. Observed evidence must be LogLine instances with original line numbers
    assert isinstance(result.primary_evidence, tuple)
    for ev in result.primary_evidence:
        assert isinstance(ev, LogLine)
        assert isinstance(ev.line_number, int)
        assert ev.line_number > 0

    assert isinstance(result.supporting_evidence, tuple)
    for ev in result.supporting_evidence:
        assert isinstance(ev, LogLine)
        assert isinstance(ev.line_number, int)

    # 2. Heuristic explanation is distinct and acknowledges uncertainty
    assert result.root_cause_explanation is not None
    # Must describe candidate / likely status, not a guaranteed diagnosis
    assert "most likely root-cause candidate" in result.root_cause_explanation

    # 3. CLI summary format explicitly acknowledges heuristic uncertainty
    summary = format_summary(result)
    assert "LIKELY ROOT-CAUSE CANDIDATE" in summary
    assert "This is a deterministic heuristic analysis, not a guaranteed root-cause diagnosis." in summary
