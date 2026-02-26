"""Parse and validate incoming metrics task JSON files against a strict JSON Schema.

Operations supported:
- collect_agent_metrics: Collect metrics for a specific agent.
- collect_team_metrics: Collect and aggregate metrics for an entire team.
- compute_cost: Compute token cost estimates for a given usage.
- check_slo: Check if an agent/team meets SLO targets.
- generate_report: Generate a full metrics report.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

# ---------------------------------------------------------------------------
# JSON Schema for task.json
# ---------------------------------------------------------------------------

TASK_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "MetricsAgentTask",
    "type": "object",
    "required": [
        "task_id",
        "user_id",
        "team_id",
        "metrics_request",
        "metadata",
    ],
    "additionalProperties": False,
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "user_id": {"type": "string", "minLength": 1},
        "team_id": {"type": "string", "minLength": 1},
        "metrics_request": {
            "type": "object",
            "required": ["operation"],
            "additionalProperties": False,
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "collect_agent_metrics",
                        "collect_team_metrics",
                        "compute_cost",
                        "check_slo",
                        "generate_report",
                    ],
                },
                "target_agent_id": {"type": "string", "minLength": 1},
                "target_team_id": {"type": "string", "minLength": 1},
                "period": {"type": "string", "minLength": 1},
                "slo_config": {
                    "type": "object",
                    "required": [
                        "latency_p95_ms",
                        "error_rate_pct",
                        "throughput_min",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "latency_p95_ms": {"type": "number", "minimum": 0},
                        "error_rate_pct": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                        },
                        "throughput_min": {"type": "number", "minimum": 0},
                    },
                },
            },
        },
        "metadata": {
            "type": "object",
            "required": ["source", "priority", "timestamp"],
            "additionalProperties": False,
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["system", "scheduler", "api", "manual"],
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high"],
                },
                "timestamp": {"type": "string", "minLength": 1},
            },
        },
    },
}

_validator = Draft7Validator(TASK_SCHEMA)

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class ParseResult:
    """Outcome of parsing a task file."""

    ok: bool
    task: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_task_file(task_path: Path) -> ParseResult:
    """Read *task_path*, validate against schema + semantics, return result."""
    if not task_path.exists():
        return ParseResult(ok=False, errors=[f"Task file not found: {task_path}"])

    try:
        raw = task_path.read_text(encoding="utf-8")
    except OSError as exc:
        return ParseResult(ok=False, errors=[f"Cannot read task file: {exc}"])

    return parse_task(raw)


def parse_task(raw_json: str) -> ParseResult:
    """Validate a raw JSON string as a metrics agent task."""
    try:
        task = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return ParseResult(ok=False, errors=[f"Invalid JSON: {exc}"])

    return validate_task(task)


def validate_task(task: dict[str, Any]) -> ParseResult:
    """Validate an already-parsed dict against schema + semantic rules."""
    schema_errors = sorted(
        _validator.iter_errors(task), key=lambda e: list(e.path)
    )
    if schema_errors:
        msgs = [
            f"Schema: "
            f"{'.'.join(str(p) for p in e.absolute_path) or '(root)'}: "
            f"{e.message}"
            for e in schema_errors
        ]
        return ParseResult(ok=False, errors=msgs)

    semantic_errors = _semantic_checks(task)
    if semantic_errors:
        return ParseResult(ok=False, errors=semantic_errors)

    return ParseResult(ok=True, task=task)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _semantic_checks(task: dict[str, Any]) -> list[str]:
    """Business-rule validations beyond JSON Schema."""
    errors: list[str] = []
    metrics_req = task["metrics_request"]
    op = metrics_req["operation"]

    # collect_agent_metrics requires target_agent_id
    if op == "collect_agent_metrics" and not metrics_req.get("target_agent_id"):
        errors.append(
            "Operation 'collect_agent_metrics' requires 'target_agent_id'"
        )

    # collect_team_metrics requires target_team_id
    if op == "collect_team_metrics" and not metrics_req.get("target_team_id"):
        errors.append(
            "Operation 'collect_team_metrics' requires 'target_team_id'"
        )

    # check_slo requires slo_config
    if op == "check_slo" and not metrics_req.get("slo_config"):
        errors.append(
            "Operation 'check_slo' requires 'slo_config'"
        )

    return errors
