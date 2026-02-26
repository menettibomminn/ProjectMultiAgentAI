"""Generate directives and processing reports for the Controller.

The Controller produces two kinds of output:
1. Directives (directive_v1) written to outbox for target agents.
2. Self-reports summarising inbox processing results.

This module does NOT call any external API.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Directive generation
# ---------------------------------------------------------------------------


def generate_directive(
    *,
    directive_id: str,
    target_agent: str,
    command: str,
    parameters: dict[str, Any],
    controller_id: str,
) -> dict[str, Any]:
    """Build a directive_v1 dict with SHA-256 signature.

    Args:
        directive_id: Unique directive identifier.
        target_agent: The agent that should execute this directive.
        command: The command to execute (e.g. "write_range").
        parameters: Command-specific parameters.
        controller_id: The controller that issued this directive.

    Returns:
        A directive_v1 dict ready for serialisation.
    """
    payload = {
        "directive_id": directive_id,
        "target_agent": target_agent,
        "command": command,
        "parameters": parameters,
    }
    # Compute signature over the canonical payload
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    signature = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    now_utc = datetime.now(timezone.utc)
    return {
        **payload,
        "issued_by": controller_id,
        "issued_at": now_utc.isoformat(),
        "signature": signature,
    }


def write_directive(directive: dict[str, Any], path: Path) -> None:
    """Atomically write a directive dict to *path* as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(directive, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Processing report generation
# ---------------------------------------------------------------------------


def generate_processing_report(
    *,
    controller_id: str,
    task_id: str,
    processed_reports: list[dict[str, Any]],
    directives_emitted: list[str],
    state_changes: list[dict[str, Any]],
    errors: list[str] | None = None,
    version: int = 1,
) -> dict[str, Any]:
    """Generate a self-report summarising one processing cycle.

    Args:
        controller_id: This controller's identifier.
        task_id: The controller task being processed.
        processed_reports: List of report summaries that were processed.
        directives_emitted: List of directive IDs that were emitted.
        state_changes: List of state changes applied to STATE.md.
        errors: Optional list of error messages.
        version: Report schema version.
    """
    now_utc = datetime.now(timezone.utc)
    local_tz = timezone(timedelta(hours=1))
    now_local = now_utc.astimezone(local_tz)

    status = "success" if not errors else "error"

    return {
        "agent": "controller",
        "controller_id": controller_id,
        "task_id": task_id,
        "status": status,
        "summary": (
            f"Processed {len(processed_reports)} reports, "
            f"emitted {len(directives_emitted)} directives"
        ),
        "processed_reports": processed_reports,
        "directives_emitted": directives_emitted,
        "state_changes": state_changes,
        "errors": errors or [],
        "metrics": {
            "reports_processed": len(processed_reports),
            "directives_emitted": len(directives_emitted),
        },
        "timestamp_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timestamp_local": now_local.isoformat(),
        "version": version,
    }


def generate_error_report(
    task_id: str,
    controller_id: str,
    errors: list[str],
    *,
    version: int = 1,
) -> dict[str, Any]:
    """Generate an error report when processing fails."""
    now_utc = datetime.now(timezone.utc)
    local_tz = timezone(timedelta(hours=1))
    now_local = now_utc.astimezone(local_tz)

    return {
        "agent": "controller",
        "controller_id": controller_id,
        "task_id": task_id,
        "status": "error",
        "summary": f"Processing failed: {errors[0] if errors else 'unknown'}",
        "processed_reports": [],
        "directives_emitted": [],
        "state_changes": [],
        "errors": errors,
        "metrics": {"reports_processed": 0, "directives_emitted": 0},
        "timestamp_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timestamp_local": now_local.isoformat(),
        "version": version,
    }


def write_report(report: dict[str, Any], path: Path) -> None:
    """Atomically write the report dict to *path* as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(path)
