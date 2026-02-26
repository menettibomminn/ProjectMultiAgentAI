"""Generate a report.json with proposed UI component actions from a validated task.

This module does NOT call any external API. It transforms the task into a
structured proposal that can be reviewed and approved before execution.

NOTE: Frontend agent does not access Google Sheets directly.
Only UI component metadata (component type, description, template hints) appear
in the output.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Component type mapping per operation
# ---------------------------------------------------------------------------

_OP_COMPONENT: dict[str, str] = {
    "render_dashboard": "dashboard",
    "render_approval_form": "approval_form",
    "render_audit_log": "audit_table",
    "validate_input": "validation_result",
    "format_error": "error_display",
}

_OP_DESCRIPTION: dict[str, str] = {
    "render_dashboard": (
        "Render dashboard view for user {user_id} "
        "with {sheet_count} sheet(s)"
    ),
    "render_approval_form": (
        "Render approval form for change {change_id} "
        "on sheet {sheet_id}"
    ),
    "render_audit_log": (
        "Render audit log table for user {user_id}"
    ),
    "validate_input": (
        "Validate form data against schema '{schema_name}' "
        "for user {user_id}"
    ),
    "format_error": (
        "Format error display for code '{error_code}': {error_message}"
    ),
}

_OP_TEMPLATE_HINT: dict[str, str] = {
    "render_dashboard": "components/dashboard/sheet-grid.html",
    "render_approval_form": "components/approval/change-review.html",
    "render_audit_log": "components/audit/log-table.html",
    "validate_input": "components/forms/validation-feedback.html",
    "format_error": "components/errors/error-banner.html",
}

# ---------------------------------------------------------------------------
# Risk / confidence heuristics per operation type
# ---------------------------------------------------------------------------

_OP_RISK: dict[str, str] = {
    "render_dashboard": "low",
    "render_approval_form": "low",
    "render_audit_log": "low",
    "validate_input": "low",
    "format_error": "low",
}

_OP_CONFIDENCE: dict[str, float] = {
    "render_dashboard": 0.95,
    "render_approval_form": 0.95,
    "render_audit_log": 0.95,
    "validate_input": 0.99,
    "format_error": 0.90,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_report(
    task: dict[str, Any],
    agent_id: str,
    *,
    version: int = 1,
) -> dict[str, Any]:
    """Transform a validated frontend task into a report dict.

    Args:
        task: A validated task dict (must have passed parse_task).
        agent_id: The agent identifier.
        version: Report schema version.

    Returns:
        A dict conforming to the report schema.
    """
    now_utc = datetime.now(timezone.utc)
    local_tz = timezone(timedelta(hours=1))
    now_local = now_utc.astimezone(local_tz)

    ui_req = task["ui_request"]
    op = ui_req["operation"]
    user_id = task["user_id"]

    # Build description format kwargs
    fmt_kwargs: dict[str, Any] = {"user_id": user_id}
    if op == "render_dashboard":
        fmt_kwargs["sheet_count"] = len(ui_req.get("sheets", []))
    elif op == "render_approval_form":
        change = ui_req.get("change", {})
        fmt_kwargs["change_id"] = change.get("change_id", "unknown")
        fmt_kwargs["sheet_id"] = change.get("sheet_id", "unknown")
    elif op == "validate_input":
        fmt_kwargs["schema_name"] = ui_req.get("schema_name", "unknown")
    elif op == "format_error":
        error = ui_req.get("error", {})
        fmt_kwargs["error_code"] = error.get("code", "unknown")
        fmt_kwargs["error_message"] = error.get("message", "unknown")

    # Approval is required for approval forms
    approval_required = op == "render_approval_form"

    # Build proposed change
    proposed = {
        "component_type": _OP_COMPONENT.get(op, "unknown"),
        "description": _OP_DESCRIPTION.get(op, "Unknown operation").format(
            **fmt_kwargs
        ),
        "approval_required": approval_required,
        "html_template_hint": _OP_TEMPLATE_HINT.get(op, "components/unknown.html"),
        "confidence": _OP_CONFIDENCE.get(op, 0.5),
        "estimated_risk": _OP_RISK.get(op, "low"),
    }

    # Validation entries
    validation_entries: list[dict[str, Any]] = [
        {
            "field": "ui_request.operation",
            "ok": True,
            "notes": f"Operation '{op}' is valid",
        },
        {
            "field": "ui_request",
            "ok": True,
            "notes": "All required fields present for operation",
        },
        {
            "field": "metadata",
            "ok": True,
            "notes": "Metadata is valid",
        },
    ]

    # Risk notes — frontend never touches sheets
    risks: list[str] = [
        "Frontend agent does not access Google Sheets directly",
    ]

    description = _OP_DESCRIPTION.get(op, "Unknown operation").format(**fmt_kwargs)
    ts_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        # report_v1 required fields (Controller compatibility)
        "agent": agent_id,
        "timestamp": ts_utc,
        "task_id": task["task_id"],
        "status": "success",
        "summary": description,
        "metrics": {"duration_ms": 0},
        "artifacts": [],
        "next_actions": [],
        # Agent-specific fields
        "agent_id": agent_id,
        "proposed_changes": [proposed],
        "validation": validation_entries,
        "risks": risks,
        "errors": [],
        "timestamp_utc": ts_utc,
        "timestamp_local": now_local.isoformat(),
        "version": version,
    }


def generate_error_report(
    task_id: str,
    agent_id: str,
    errors: list[str],
    *,
    version: int = 1,
) -> dict[str, Any]:
    """Generate an error report when task processing fails."""
    now_utc = datetime.now(timezone.utc)
    local_tz = timezone(timedelta(hours=1))
    now_local = now_utc.astimezone(local_tz)

    ts_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        # report_v1 required fields (Controller compatibility)
        "agent": agent_id,
        "timestamp": ts_utc,
        "task_id": task_id,
        "status": "error",
        "summary": f"Error processing task {task_id}",
        "metrics": {"duration_ms": 0},
        "artifacts": [],
        "next_actions": [],
        # Agent-specific fields
        "agent_id": agent_id,
        "proposed_changes": [],
        "validation": [],
        "risks": [],
        "errors": errors,
        "timestamp_utc": ts_utc,
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
