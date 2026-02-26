"""Generate a report.json with proposed backend actions from a validated task.

This module does NOT call any external API. It transforms the task into a
structured proposal that can be reviewed and approved before execution.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Risk / confidence heuristics per operation type
# ---------------------------------------------------------------------------

_OP_CONFIDENCE: dict[str, float] = {
    "process_sheet_request": 0.90,
    "validate_payload": 0.99,
    "aggregate_reports": 0.95,
    "route_directive": 0.90,
    "compute_diff": 0.95,
}

_OP_BASE_RISK: dict[str, str] = {
    "process_sheet_request": "low",
    "validate_payload": "low",
    "aggregate_reports": "low",
    "route_directive": "medium",
    "compute_diff": "low",
}

# Thresholds: operations matching these trigger needs_review
_NEEDS_REVIEW_RISK_LEVELS = frozenset({"high"})
_NEEDS_REVIEW_CONFIDENCE_THRESHOLD = 0.85

_OP_EXPLANATION: dict[str, str] = {
    "process_sheet_request": (
        "Process sheet request for sheet {sheet_id} "
        "with {change_count} change(s)"
    ),
    "validate_payload": (
        "Validate payload against schema '{schema_name}' "
        "for user {user_id}"
    ),
    "aggregate_reports": (
        "Aggregate {report_count} report(s) into a summary"
    ),
    "route_directive": (
        "Route directive '{directive}' for user {user_id}"
    ),
    "compute_diff": (
        "Compute diff for sheet {sheet_id} for user {user_id}"
    ),
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
    """Transform a validated backend task into a report dict.

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

    req = task["request"]
    op = req["operation"]
    user_id = task["user_id"]
    sheet_id = req.get("sheet_id", "")
    changes = req.get("changes", [])
    schema_name = req.get("schema_name", "")
    reports = req.get("reports", [])
    directive = req.get("directive", "")

    # Determine risk: process_sheet_request with > 100 changes is "high"
    risk = _compute_risk(op, changes)

    # Build details based on operation
    details = _build_details(op, req)

    # Build proposed change
    proposed = {
        "operation": op,
        "details": details,
        "confidence": _OP_CONFIDENCE.get(op, 0.5),
        "risk": risk,
        "explanation": _OP_EXPLANATION.get(op, "Unknown operation").format(
            user_id=user_id,
            sheet_id=sheet_id,
            change_count=len(changes),
            schema_name=schema_name,
            report_count=len(reports),
            directive=directive,
        ),
    }

    # Determine status: needs_review if risk is high or confidence is low
    review_reasons: list[str] = []
    confidence = _OP_CONFIDENCE.get(op, 0.5)
    if risk in _NEEDS_REVIEW_RISK_LEVELS:
        review_reasons.append(
            f"{op}: risk={risk} (changes={len(changes)})"
        )
    elif confidence < _NEEDS_REVIEW_CONFIDENCE_THRESHOLD:
        review_reasons.append(
            f"{op}: confidence={confidence}"
        )
    status = "needs_review" if review_reasons else "success"

    # Validation entries
    validation_entries: list[dict[str, Any]] = [
        {
            "field": "request.operation",
            "ok": True,
            "notes": f"Operation '{op}' is valid",
        },
        {
            "field": "metadata.source",
            "ok": True,
            "notes": "Source is within allowed set",
        },
    ]

    if op == "process_sheet_request":
        validation_entries.append({
            "field": "request.sheet_id",
            "ok": True,
            "notes": f"Sheet ID '{sheet_id}' is present",
        })
        validation_entries.append({
            "field": "request.changes",
            "ok": True,
            "notes": f"{len(changes)} change(s) validated",
        })

    if op == "validate_payload":
        validation_entries.append({
            "field": "request.payload",
            "ok": True,
            "notes": "Payload is present",
        })
        validation_entries.append({
            "field": "request.schema_name",
            "ok": True,
            "notes": f"Schema '{schema_name}' specified",
        })

    # Risk warnings
    risks: list[str] = []
    if risk == "high":
        risks.append(
            f"Bulk write: {len(changes)} changes exceeds 100 — "
            "consider batching"
        )
    if op == "route_directive":
        risks.append(
            f"Routing directive '{directive}' — ensure target handler exists"
        )

    summary = _OP_EXPLANATION.get(op, "Unknown operation").format(
        user_id=user_id,
        sheet_id=sheet_id,
        change_count=len(changes),
        schema_name=schema_name,
        report_count=len(reports),
        directive=directive,
    )
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
        "proposed_changes": [proposed],
        "validation": validation_entries,
        "risks": risks,
        "errors": [],
        "review_reasons": review_reasons,
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


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _compute_risk(op: str, changes: list[Any]) -> str:
    """Compute risk level based on operation and payload size."""
    if op == "process_sheet_request" and len(changes) > 100:
        return "high"
    return _OP_BASE_RISK.get(op, "high")


def _build_details(op: str, req: dict[str, Any]) -> dict[str, Any]:
    """Build operation-specific details dict."""
    if op == "process_sheet_request":
        return {
            "sheet_id": req.get("sheet_id", ""),
            "change_count": len(req.get("changes", [])),
            "changes_preview": req.get("changes", [])[:5],
        }
    if op == "validate_payload":
        return {
            "validated_payload": True,
            "schema_name": req.get("schema_name", ""),
        }
    if op == "aggregate_reports":
        return {
            "report_count": len(req.get("reports", [])),
            "aggregated": True,
        }
    if op == "route_directive":
        return {
            "routing_target": req.get("directive", ""),
            "routed": True,
        }
    if op == "compute_diff":
        return {
            "computed_diff": True,
            "sheet_id": req.get("sheet_id", ""),
        }
    return {}
