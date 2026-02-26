"""Write structured audit log entries for every backend agent execution.

Each run produces one file: ops/audit/backend-agent/{timestamp}.json
Content includes checksums, timestamps, operation details, and runtime metrics.
"""
from __future__ import annotations

import hashlib
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def compute_checksum(data: dict[str, Any]) -> str:
    """SHA-256 hex digest of the canonical JSON serialisation of *data*."""
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_audit_entry(
    audit_dir: Path,
    *,
    task_id: str,
    agent_id: str,
    user_id: str,
    team_id: str,
    config_version: int,
    op_steps: list[dict[str, Any]],
    report: dict[str, Any] | None,
    error: Exception | None = None,
    duration_ms: float = 0.0,
) -> Path:
    """Create an audit JSON file and return its path.

    Args:
        audit_dir: Target directory (created if missing).
        task_id: The task being processed.
        agent_id: This agent's identifier.
        user_id: The user who requested the task.
        team_id: The team owning this task.
        config_version: Config schema version.
        op_steps: List of operation steps with their own timestamps.
        report: The generated report dict (used for checksum). None on error.
        error: Exception instance if an error occurred.
        duration_ms: Total runtime in milliseconds.

    Returns:
        Path to the written audit file.
    """
    audit_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    ts_slug = now.strftime("%Y%m%dT%H%M%SZ")

    entry: dict[str, Any] = {
        "audit_version": 1,
        "timestamp_utc": now.isoformat(),
        "task_id": task_id,
        "agent_id": agent_id,
        "user_id": user_id,
        "team_id": team_id,
        "config_version": config_version,
        "op_steps": op_steps,
        "report_checksum": compute_checksum(report) if report else None,
        "runtime_metrics": {
            "duration_ms": round(duration_ms, 2),
        },
        "error": None,
    }

    if error:
        entry["error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "stack": traceback.format_exception(
                type(error), error, error.__traceback__
            ),
        }

    filename = f"{ts_slug}_{task_id}.json"
    path = audit_dir / filename
    path.write_text(
        json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path
