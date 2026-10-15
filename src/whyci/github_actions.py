"""GitHub Actions workflow log archive loader and processor.

Safely processes downloaded GitHub Actions workflow log ZIP archives in memory,
defending against path traversal (Zip Slip), decompression bombs, and unsafe entries.
Integrates with WhyCI's deterministic redaction, classification, and heuristic ranking.
"""

from __future__ import annotations

import io
import re
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

from whyci.config import LOG_ENCODING
from whyci.log_processor.processor import LogLine, ProcessingResult, process_log_lines

# Security limits for untrusted archive decompression
MAX_SINGLE_FILE_BYTES: int = 20 * 1024 * 1024  # 20 MB per log file
MAX_TOTAL_UNCOMPRESSED_BYTES: int = 50 * 1024 * 1024  # 50 MB total across archive
MAX_ARCHIVE_FILE_COUNT: int = 100  # Max entries in a single workflow archive
SUPPORTED_LOG_EXTENSIONS: tuple[str, ...] = (".txt", ".log")

# Regex to detect absolute paths across Windows and POSIX
_ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:[a-zA-Z]:|[/\\])")
# Reserved Windows device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
_RESERVED_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


@dataclass(frozen=True)
class WorkflowResult:
    """Aggregated analysis for a GitHub Actions workflow run archive."""

    archive_path: Path
    job_results: tuple[ProcessingResult, ...]
    unsupported_files: tuple[str, ...]

    @property
    def total_jobs(self) -> int:
        return len(self.job_results)

    @property
    def failing_jobs(self) -> tuple[ProcessingResult, ...]:
        return tuple(j for j in self.job_results if j.error_count > 0)

    @property
    def top_candidate_job(self) -> ProcessingResult | None:
        """The job result containing the highest-priority root-cause candidate."""
        candidates = [j for j in self.job_results if j.root_cause_candidate is not None]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda j: j.root_cause_score if j.root_cause_score is not None else -1.0,
        )


def validate_archive_entry_path(name: str) -> None:
    """Validate archive member name against path traversal and unsafe constructs.

    Raises ValueError if an entry contains traversal sequences, absolute paths,
    control characters, or reserved device names.
    """
    if "\x00" in name:
        raise ValueError(f"Unsafe archive entry: null byte detected in {name!r}")

    # Reject terminal escape and control characters (e.g. \x1b, \r, \n)
    if any(ord(c) < 32 and c not in "\t" for c in name):
        raise ValueError(f"Unsafe archive entry: control characters detected in {name!r}")

    # Check for absolute path (POSIX root / or Windows drive C:\)
    if _ABSOLUTE_PATH_PATTERN.search(name):
        raise ValueError(f"Unsafe archive entry: absolute path detected in {name!r}")

    # Normalize separators and inspect each segment
    normalized = name.replace("\\", "/")
    segments = normalized.split("/")
    for segment in segments:
        if segment == "..":
            raise ValueError(f"Unsafe archive entry: path traversal '..' in {name!r}")
        stem = segment.split(".")[0].lower()
        if stem in _RESERVED_DEVICE_NAMES:
            raise ValueError(f"Unsafe archive entry: reserved device name in {name!r}")


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    """Return True if archive entry is a symbolic link."""
    # S_IFLNK (0o120000) in upper 16 bits of external_attr
    return bool((info.external_attr >> 16) & 0o120000 == 0o120000)


def is_supported_log_file(filename: str) -> bool:
    """Check if the filename has a supported log extension."""
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in SUPPORTED_LOG_EXTENSIONS)


def _read_entry_lines_safe(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    cumulative_bytes: int,
) -> tuple[list[LogLine] | None, int]:
    """Read a single archive entry in memory with strict byte limit and binary checks.

    Returns the parsed LogLines (or None if binary content detected) and the
    updated cumulative byte count.
    """
    if info.file_size > MAX_SINGLE_FILE_BYTES:
        raise ValueError(
            f"Archive entry '{info.filename}' exceeds single file limit "
            f"({info.file_size} > {MAX_SINGLE_FILE_BYTES} bytes)"
        )

    read_bytes = 0
    buffer = io.BytesIO()

    try:
        with archive.open(info, mode="r") as stream:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                read_bytes += len(chunk)
                if read_bytes > MAX_SINGLE_FILE_BYTES:
                    raise ValueError(
                        f"Archive entry '{info.filename}' exceeded decompressed file size limit "
                        f"({MAX_SINGLE_FILE_BYTES} bytes)"
                    )
                if cumulative_bytes + read_bytes > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise ValueError(
                        f"Archive exceeds total decompression limit "
                        f"({MAX_TOTAL_UNCOMPRESSED_BYTES} bytes)"
                    )
                buffer.write(chunk)
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError) as exc:
        raise ValueError(f"Corrupted or invalid entry '{info.filename}' in archive: {exc}") from exc

    cumulative_bytes += read_bytes
    raw_bytes = buffer.getvalue()

    # Binary file detection: text logs do not contain null bytes
    if b"\x00" in raw_bytes:
        return None, cumulative_bytes

    raw_content = raw_bytes.decode(encoding=LOG_ENCODING, errors="replace")

    lines: list[LogLine] = []
    for index, text in enumerate(raw_content.splitlines(), start=1):
        lines.append(LogLine(line_number=index, text=text))

    return lines, cumulative_bytes


def process_workflow_archive(
    archive_path: str | Path,
    redact: bool = True,
) -> WorkflowResult:
    """Safely process a downloaded GitHub Actions workflow log ZIP archive.

    Decompresses supported log entries in memory, applies secret redaction,
    runs deterministic heuristic signal detection, and aggregates results.
    """
    path = Path(archive_path)
    if not path.exists():
        raise FileNotFoundError(f"Workflow archive not found: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a regular file: {path}")

    try:
        archive = zipfile.ZipFile(path, mode="r")
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Invalid or corrupted ZIP archive '{path}': {exc}") from exc

    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_FILE_COUNT:
            raise ValueError(
                f"Archive contains {len(entries)} entries, exceeding safety limit of "
                f"{MAX_ARCHIVE_FILE_COUNT}"
            )

        job_results: list[ProcessingResult] = []
        unsupported_files: list[str] = []
        cumulative_bytes = 0

        # Sort entries for deterministic processing order
        sorted_entries = sorted(entries, key=lambda e: e.filename)

        for info in sorted_entries:
            filename = info.filename

            # Skip directory entries
            if info.is_dir() or filename.endswith(("/", "\\")):
                continue

            # Validate entry path against path traversal / Zip Slip
            validate_archive_entry_path(filename)

            # Prevent extracting symlinks
            if _is_symlink(info):
                raise ValueError(f"Unsafe archive entry: symlink detected in {filename!r}")

            # Check supported log format
            if not is_supported_log_file(filename):
                unsupported_files.append(filename)
                continue

            # Safely read and parse log lines in memory
            lines, cumulative_bytes = _read_entry_lines_safe(archive, info, cumulative_bytes)
            if lines is None:
                unsupported_files.append(f"{filename} (binary content)")
                continue

            # Run through WhyCI pipeline (redaction happens before analysis)
            result = process_log_lines(lines, source_path=filename, redact=redact)
            job_results.append(result)

        if not job_results:
            supported = ", ".join(SUPPORTED_LOG_EXTENSIONS)
            raise ValueError(f"Archive '{path.name}' contains no supported log files ({supported})")

        return WorkflowResult(
            archive_path=path,
            job_results=tuple(job_results),
            unsupported_files=tuple(unsupported_files),
        )
