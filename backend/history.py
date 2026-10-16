"""Local SQLite storage for redacted WhyCI analysis history."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).resolve().parent.parent / ".whyci" / "history.sqlite3"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(_DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_history() -> None:
    """Create the local history table if it doesn't exist."""
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signature TEXT NOT NULL,
                source_name TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_history_signature "
            "ON analysis_history(signature)"
        )


def _stable_signature(result: dict[str, Any]) -> str:
    """Build a signature from the redacted root cause, not the filename."""
    root_cause = result.get("root_cause") or {}
    text = str(root_cause.get("text") or "").strip().lower()
    category = str(root_cause.get("category") or "").strip().lower()

    if not text:
        evidence = result.get("primary_evidence") or []
        text = str(evidence[0].get("text") if evidence else "").strip().lower()

    # If no useful error is available, avoid grouping unrelated empty analyses.
    if not text:
        text = "no-root-cause:" + str(result.get("error_count", 0))

    normalized = " ".join(text.split())
    raw = f"{category}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def record_analysis(result: dict[str, Any]) -> dict[str, Any]:
    """Save a redacted analysis summary and report whether it has occurred before."""
    initialize_history()

    # Persist only the redacted API result; never save the original uploaded log.
    safe_result = dict(result)
    signature = _stable_signature(safe_result)

    with _connect() as connection:
        previous_count = connection.execute(
            "SELECT COUNT(*) FROM analysis_history WHERE signature = ?",
            (signature,),
        ).fetchone()[0]

        cursor = connection.execute(
            """
            INSERT INTO analysis_history(signature, source_name, summary_json)
            VALUES (?, ?, ?)
            """,
            (
                signature,
                str(safe_result.get("source_name") or "unknown"),
                json.dumps(safe_result, ensure_ascii=False),
            ),
        )

    safe_result["repeat_detected"] = previous_count > 0
    safe_result["repeat_count"] = previous_count + 1
    safe_result["history_id"] = cursor.lastrowid
    return safe_result


def list_history(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent history entries without exposing the signature."""
    initialize_history()
    limit = max(1, min(int(limit), 200))

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, source_name, summary_json, created_at
            FROM analysis_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    entries = []
    for row in rows:
        summary = json.loads(row["summary_json"])
        entries.append(
            {
                "id": row["id"],
                "source_name": row["source_name"],
                "created_at": row["created_at"],
                "error_count": summary.get("error_count", 0),
                "warning_count": summary.get("warning_count", 0),
                "repeat_detected": summary.get("repeat_detected", False),
                "repeat_count": summary.get("repeat_count", 1),
            }
        )
    return entries


def clear_history() -> int:
    """Delete all locally stored analysis history and return the deleted count."""
    initialize_history()
    with _connect() as connection:
        deleted = connection.execute(
            "SELECT COUNT(*) FROM analysis_history"
        ).fetchone()[0]
        connection.execute("DELETE FROM analysis_history")
        connection.execute(
            "DELETE FROM sqlite_sequence WHERE name = 'analysis_history'"
        )
    return int(deleted)