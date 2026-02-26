"""Generate a report.json with proposed_changes from a validated task.

This module does NOT call any external API — it transforms the task into a
structured proposal that can be reviewed and approved before execution.

Design decisions (see ARCHITECTURE.md):
- old_values is always null because the agent never reads live sheet data.
- confidence and estimated_risk are derived from the operation type.
- explanation is auto-generated from the operation parameters.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Risk / confidence heuristics per operation type
# ---------------------------------------------------------------------------

_OP_RISK: dict[str, str] = {
    "update": "low",
    "append_row": "low",
    "delete_row": "medium",
    "clear_range": "high",
}

_OP_CONFIDENCE: dict[str, float] = {
    "update": 0.95,
    "append_row": 0.95,
    "delete_row": 0.85,
    "clear_range": 0.80,
}

# Threshold: operations with risk >= this level trigger needs_review
_NEEDS_REVIEW_RISK_LEVELS = frozenset({"high"})
_NEEDS_REVIEW_CONFIDENCE_THRESHOLD = 0.85  # also review if confidence < this


_OP_EXPLANATION: dict[str, str] = {
    "update": "Update cells {range} on {sheet_name} with provided values",
    "append_row": "Append new row(s) at {range} on {sheet_name}",
    "delete_row": "Delete row(s) at {range} on {sheet_name}",
    "clear_range": "Clear all values in {range} on {sheet_name}",
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
    """Transform a validated task into a report dict with proposed_changes.

    Args:
        task: A validated task dict (must have passed parse_task validation).
        agent_id: The agent identifier.
        version: Report schema version.

    Returns:
        A dict conforming to the report schema.
    """
    now_utc = datetime.now(timezone.utc)
    # Conservative choice: use UTC+1 for local (CET), matching the project locale.
    local_tz = timezone(timedelta(hours=1))
    now_local = now_utc.astimezone(local_tz)

    sheet = task["sheet"]
    proposed_changes: list[dict[str, Any]] = []
    validation_entries: list[dict[str, Any]] = []
    risks: list[str] = []

    for i, change in enumerate(task["requested_changes"]):
        op = change["op"]

        # Build proposed change
        proposed = {
            "op": op,
            "sheet": {
                "spreadsheet_id": sheet["spreadsheet_id"],
                "sheet_name": sheet["sheet_name"],
            },
            "range": change["range"],
            "old_values": None,  # not available — agent does not read from Sheets
            "new_values": change.get("values"),
            "explanation": _OP_EXPLANATION.get(op, "Unknown operation").format(
                range=change["range"],
                sheet_name=sheet["sheet_name"],
            ),
            "confidence": _OP_CONFIDENCE.get(op, 0.5),
            "estimated_risk": _OP_RISK.get(op, "high"),
        }
        proposed_changes.append(proposed)

        # Validation entry per change
        validation_entries.append(
            {
                "field": f"requested_changes[{i}].range",
                "ok": True,
                "notes": "",
            }
        )
        validation_entries.append(
            {
                "field": f"requested_changes[{i}].op",
                "ok": True,
                "notes": "",
            }
        )

        # Risk warnings
        if op == "delete_row":
            risks.append(
                f"Change [{i}]: delete_row at {change['range']} — "
                "possible data loss if row contains formulas or linked data"
            )
        elif op == "clear_range":
            risks.append(
                f"Change [{i}]: clear_range at {change['range']} — "
                "all values in range will be permanently removed"
            )

    # Build human-readable summary for Controller report_v1 compatibility
    change_descs = []
    for c in task["requested_changes"]:
        change_descs.append(f"{c['op']} {c['range']} on {sheet['sheet_name']}")
    summary = "; ".join(change_descs) if change_descs else "No changes proposed"

    # Determine status: needs_review if any change is high-risk or low-confidence
    review_reasons: list[str] = []
    for pc in proposed_changes:
        risk = pc.get("estimated_risk", "low")
        confidence = pc.get("confidence", 1.0)
        if risk in _NEEDS_REVIEW_RISK_LEVELS:
            review_reasons.append(
                f"{pc['op']} on {pc['range']}: risk={risk}"
            )
        elif confidence < _NEEDS_REVIEW_CONFIDENCE_THRESHOLD:
            review_reasons.append(
                f"{pc['op']} on {pc['range']}: confidence={confidence}"
            )

    status = "needs_review" if review_reasons else "success"

    ts_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        # report_v1 required fields (Controller compatibility)
        "agent": agent_id,
        "timestamp": ts_utc,
        "task_id": task["task_id"],
        "status": status,
        "summary": summary,
        "metrics": {"duration_ms": 0},
        "artifacts": [],
        "next_actions": [],
        # Agent-specific fields
        "agent_id": agent_id,
        "proposed_changes": proposed_changes,
        "validation": validation_entries,
        "risks": risks,
        "review_reasons": review_reasons,
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
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
