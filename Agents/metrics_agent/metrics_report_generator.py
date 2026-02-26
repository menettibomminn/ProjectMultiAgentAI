"""Generate a report.json with metrics analysis results from a validated task.

This module does NOT call any external API. It transforms the task into a
structured proposal that can be reviewed before execution.

Supported operations:
- collect_agent_metrics: Metrics for a single agent.
- collect_team_metrics: Aggregated metrics for a team.
- compute_cost: Token cost estimation using model pricing.
- check_slo: SLO compliance check.
- generate_report: General metrics report.
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
    "collect_agent_metrics": "low",
    "collect_team_metrics": "low",
    "compute_cost": "low",
    "check_slo": "low",
    "generate_report": "low",
}

_OP_CONFIDENCE: dict[str, float] = {
    "collect_agent_metrics": 0.95,
    "collect_team_metrics": 0.95,
    "compute_cost": 0.99,
    "check_slo": 0.90,
    "generate_report": 0.95,
}

_OP_EXPLANATION: dict[str, str] = {
    "collect_agent_metrics": (
        "Collect metrics for agent {target_agent_id} "
        "in period {period}"
    ),
    "collect_team_metrics": (
        "Aggregate metrics for team {target_team_id} "
        "in period {period}"
    ),
    "compute_cost": (
        "Compute token cost estimate for team {target_team_id}"
    ),
    "check_slo": (
        "Check SLO compliance for team {target_team_id} "
        "against configured thresholds"
    ),
    "generate_report": (
        "Generate full metrics report for team {target_team_id}"
    ),
}

# ---------------------------------------------------------------------------
# Model pricing (EUR per 1M tokens) from ops/cost_estimator.py
# ---------------------------------------------------------------------------

MODEL_PRICING: dict[str, dict[str, float]] = {
    "haiku": {"input": 0.74, "output": 3.68},
    "sonnet": {"input": 2.76, "output": 13.80},
    "opus": {"input": 13.80, "output": 69.00},
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
    """Transform a validated metrics task into a report dict.

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

    metrics_req = task["metrics_request"]
    op = metrics_req["operation"]
    target_agent_id = metrics_req.get("target_agent_id", "")
    target_team_id = metrics_req.get("target_team_id", "")
    period = metrics_req.get("period", "")

    # Build proposed change based on operation
    proposed = _build_proposed_changes(op, metrics_req, task)

    # Build explanation
    explanation = _OP_EXPLANATION.get(op, "Unknown operation").format(
        target_agent_id=target_agent_id,
        target_team_id=target_team_id,
        period=period,
    )
    proposed["explanation"] = explanation
    proposed["confidence"] = _OP_CONFIDENCE.get(op, 0.5)
    proposed["estimated_risk"] = _OP_RISK.get(op, "high")

    # Validation entries
    validation_entries: list[dict[str, Any]] = [
        {
            "field": "metrics_request.operation",
            "ok": True,
            "notes": f"Operation '{op}' is valid",
        },
    ]

    if target_team_id:
        validation_entries.append({
            "field": "metrics_request.target_team_id",
            "ok": True,
            "notes": f"Team '{target_team_id}' specified",
        })

    if target_agent_id:
        validation_entries.append({
            "field": "metrics_request.target_agent_id",
            "ok": True,
            "notes": f"Agent '{target_agent_id}' specified",
        })

    # Risk warnings
    risks: list[str] = []
    if op == "check_slo":
        risks.append(
            "SLO check results may trigger alerts — "
            "ensure notification channels are configured"
        )

    ts_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        # report_v1 required fields (Controller compatibility)
        "agent": agent_id,
        "timestamp": ts_utc,
        "task_id": task["task_id"],
        "status": "success",
        "summary": explanation,
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


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_proposed_changes(
    op: str,
    metrics_req: dict[str, Any],
    task: dict[str, Any],
) -> dict[str, Any]:
    """Build the proposed_changes payload based on operation type."""
    proposed: dict[str, Any] = {
        "operation": op,
    }

    if op == "collect_team_metrics":
        proposed["target_team_id"] = metrics_req.get("target_team_id", "")
        proposed["period"] = metrics_req.get("period", "")
        proposed["aggregated_metrics"] = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "avg_duration_ms": 0.0,
            "p95_duration_ms": 0.0,
            "tokens_in_total": 0,
            "tokens_out_total": 0,
            "cost_eur_total": 0.0,
            "error_rate": 0.0,
            "throughput": 0.0,
            "slo_compliance": 1.0,
        }

    elif op == "collect_agent_metrics":
        proposed["target_agent_id"] = metrics_req.get("target_agent_id", "")
        proposed["period"] = metrics_req.get("period", "")
        proposed["agent_metrics"] = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "avg_duration_ms": 0.0,
            "error_rate": 0.0,
        }

    elif op == "compute_cost":
        proposed["target_team_id"] = metrics_req.get("target_team_id", "")
        proposed["cost_estimate"] = _compute_cost_estimate(metrics_req)

    elif op == "check_slo":
        slo_config = metrics_req.get("slo_config", {})
        proposed["target_team_id"] = metrics_req.get("target_team_id", "")
        proposed["slo_config"] = slo_config
        proposed["slo_result"] = {
            "latency_p95_ok": True,
            "error_rate_ok": True,
            "throughput_ok": True,
            "overall_compliant": True,
        }

    elif op == "generate_report":
        proposed["target_team_id"] = metrics_req.get("target_team_id", "")
        proposed["report_type"] = "full"

    return proposed


def _compute_cost_estimate(metrics_req: dict[str, Any]) -> list[dict[str, Any]]:
    """Compute cost estimates for all known models."""
    estimates: list[dict[str, Any]] = []
    # Default token counts (placeholder — real values come from collected data)
    tokens_in = 100_000
    tokens_out = 50_000

    for model, pricing in MODEL_PRICING.items():
        cost_eur = (
            (tokens_in / 1_000_000) * pricing["input"]
            + (tokens_out / 1_000_000) * pricing["output"]
        )
        estimates.append({
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_eur": round(cost_eur, 6),
        })

    return estimates
