"""Write structured audit log entries for Controller processing.

Each processing cycle produces one file:
    audit/controller/{controller_id}/{timestamp}.json

Content includes checksums, timestamps, processed reports, and directives.

Design decisions (see ARCHITECTURE.md):
- Timestamps use ISO 8601 UTC.
- Report checksums are SHA-256 of the serialised JSON.
- Hash verification on incoming reports (tamper detection).
- Secrets / PII are never included — only structural metadata.
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


def verify_report_checksum(report_path: Path) -> tuple[bool, str]:
    """Verify the integrity of a report file.

    Returns (is_valid, checksum). If a .hash companion exists, verifies
    against it. Otherwise computes and returns the checksum.
    """
    try:
        content = report_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"read_error: {exc}"

    actual_hash = compute_checksum(data)
    hash_file = report_path.with_suffix(report_path.suffix + ".hash")

    if hash_file.exists():
        expected_hash = hash_file.read_text(encoding="utf-8").strip()
        return actual_hash == expected_hash, actual_hash

    # No companion hash file — report is assumed valid, return its hash
    return True, actual_hash


def write_hash_file(report_path: Path, checksum: str) -> Path:
    """Write a .hash companion file for a report."""
    hash_path = report_path.with_suffix(report_path.suffix + ".hash")
    hash_path.write_text(checksum + "\n", encoding="utf-8")
    return hash_path


def write_audit_entry(
    audit_dir: Path,
    *,
    task_id: str,
    controller_id: str,
    op_steps: list[dict[str, Any]],
    processed_reports: list[dict[str, Any]],
    directives_emitted: list[str],
    report: dict[str, Any] | None,
    error: Exception | None = None,
    duration_ms: float = 0.0,
) -> Path:
    """Create an audit JSON file and return its path.

    Args:
        audit_dir: Target directory (created if missing).
        task_id: The controller task being processed.
        controller_id: This controller's identifier.
        op_steps: List of operation steps with timestamps.
        processed_reports: Summaries of processed reports.
        directives_emitted: List of directive IDs.
        report: The generated self-report (used for checksum). None on error.
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
        "controller_id": controller_id,
        "op_steps": op_steps,
        "processed_reports": processed_reports,
        "directives_emitted": directives_emitted,
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
