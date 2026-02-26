"""Generate a report.json with proposed token management actions from a validated task.

This module does NOT call any external API. It transforms the task into a
structured proposal that can be reviewed and approved before execution.

SECURITY: Actual token values are NEVER included in reports.
Only metadata (user_id, scopes, expiry estimates) appear in the output.
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
    "issue_token": "low",
    "refresh_token": "low",
    "revoke_token": "medium",
    "validate_scopes": "low",
}

_OP_CONFIDENCE: dict[str, float] = {
    "issue_token": 0.95,
    "refresh_token": 0.95,
    "revoke_token": 0.90,
    "validate_scopes": 0.99,
}

# Thresholds: operations matching these trigger needs_review
_NEEDS_REVIEW_RISK_LEVELS = frozenset({"high"})
_NEEDS_REVIEW_CONFIDENCE_THRESHOLD = 0.85

_OP_EXPLANATION: dict[str, str] = {
    "issue_token": (
        "Issue new {auth_type} token for user {user_id} "
        "with scopes {scopes}"
    ),
    "refresh_token": (
        "Refresh existing {auth_type} token for user {user_id}"
    ),
    "revoke_token": (
        "Revoke {auth_type} token for target user {target_user_id}"
    ),
    "validate_scopes": (
        "Validate scopes {scopes} against policy for user {user_id}"
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
    """Transform a validated auth task into a report dict.

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

    auth_req = task["auth_request"]
    op = auth_req["operation"]
    user_id = task["user_id"]
    target_user_id = auth_req.get("target_user_id", user_id)
    scopes = auth_req.get("scopes", [])
    auth_type = auth_req["auth_type"]

    # Compute effective risk — revoke on service_account is elevated to high
    base_risk = _OP_RISK.get(op, "high")
    effective_risk = base_risk
    if op == "revoke_token" and auth_type == "service_account":
        effective_risk = "high"

    # Build proposed change — NEVER include actual tokens
    proposed = {
        "token_action": op,
        "auth_type": auth_type,
        "user_id": user_id,
        "target_user_id": target_user_id,
        "scopes": scopes,
        "estimated_expiry_hours": _estimate_expiry(op, auth_type),
        "explanation": _OP_EXPLANATION.get(op, "Unknown operation").format(
            user_id=user_id,
            target_user_id=target_user_id,
            auth_type=auth_type,
            scopes=", ".join(scopes),
        ),
        "confidence": _OP_CONFIDENCE.get(op, 0.5),
        "estimated_risk": effective_risk,
    }

    # Determine status: needs_review if risk is high or confidence is low
    review_reasons: list[str] = []
    confidence = _OP_CONFIDENCE.get(op, 0.5)
    if effective_risk in _NEEDS_REVIEW_RISK_LEVELS:
        review_reasons.append(
            f"{op} ({auth_type}): risk={effective_risk}"
        )
    elif confidence < _NEEDS_REVIEW_CONFIDENCE_THRESHOLD:
        review_reasons.append(
            f"{op}: confidence={confidence}"
        )
    status = "needs_review" if review_reasons else "success"

    # Validation entries
    validation_entries: list[dict[str, Any]] = [
        {
            "field": "auth_request.operation",
            "ok": True,
            "notes": f"Operation '{op}' is valid",
        },
        {
            "field": "auth_request.scopes",
            "ok": True,
            "notes": "All scopes within allowed set",
        },
        {
            "field": "auth_request.auth_type",
            "ok": True,
            "notes": f"Auth type '{auth_type}' is valid",
        },
    ]

    # Risk warnings
    risks: list[str] = []
    if op == "revoke_token":
        risks.append(
            f"Revoking token for {target_user_id} — "
            "user will need to re-authenticate"
        )
    if auth_type == "service_account":
        risks.append(
            "Service account operation — ensure job is in allowlist "
            "(infra/mcp_config.yml)"
        )

    summary = _OP_EXPLANATION.get(op, "Unknown operation").format(
        user_id=user_id,
        target_user_id=target_user_id,
        auth_type=auth_type,
        scopes=", ".join(scopes),
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


def _estimate_expiry(op: str, auth_type: str) -> float | None:
    """Estimate token expiry in hours based on operation and auth type."""
    if op in ("revoke_token", "validate_scopes"):
        return None
    if auth_type == "service_account":
        return 1.0  # SA tokens typically last 1h
    return 1.0  # OAuth access tokens typically last 1h
