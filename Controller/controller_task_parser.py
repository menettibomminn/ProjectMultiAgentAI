"""Parse and validate incoming reports and controller tasks.

The Controller receives two types of input:
1. Agent/team-lead reports (report_v1) dropped into Controller/inbox/
2. Controller tasks requesting inbox processing or directive emission.

This module validates both against JSON Schema (Draft 7) + semantic checks.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

# ---------------------------------------------------------------------------
# JSON Schema for report_v1 (incoming agent reports)
# ---------------------------------------------------------------------------

REPORT_V1_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ReportV1",
    "type": "object",
    "required": ["agent", "timestamp", "task_id", "status", "summary", "metrics"],
    "additionalProperties": True,
    "properties": {
        "agent": {"type": "string", "minLength": 1},
        "timestamp": {"type": "string", "minLength": 1},
        "task_id": {"type": "string", "minLength": 1},
        "status": {
            "type": "string",
            "enum": ["success", "failure", "partial", "error", "needs_review"],
        },
        "summary": {"type": "string"},
        "metrics": {
            "type": "object",
            "required": ["duration_ms"],
            "properties": {
                "duration_ms": {"type": "number", "minimum": 0},
                "tokens_in": {"type": "integer", "minimum": 0},
                "tokens_out": {"type": "integer", "minimum": 0},
                "cost_eur": {"type": "number", "minimum": 0},
            },
        },
        "artifacts": {"type": "array", "items": {"type": "string"}},
        "next_actions": {"type": "array", "items": {"type": "string"}},
        "review_reasons": {"type": "array", "items": {"type": "string"}},
    },
}

# ---------------------------------------------------------------------------
# JSON Schema for controller task (process_inbox command)
# ---------------------------------------------------------------------------

CONTROLLER_TASK_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ControllerTask",
    "type": "object",
    "required": ["task_id", "skill"],
    "additionalProperties": False,
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "skill": {
            "type": "string",
            "enum": [
                "process_inbox",
                "emit_directive",
                "update_state",
                "reroute_task",
                "aggregate_team_reports",
                "check_health",
                "review_candidate",
            ],
        },
        "input": {
            "type": "object",
            "properties": {
                "team": {"type": "string"},
                "agent": {"type": "string"},
                "directive": {"type": "object"},
                "changes": {"type": "array"},
                "failed_agent": {"type": "string"},
                "task": {"type": "object"},
                "candidate_id": {"type": "string"},
                "decision": {
                    "type": "string",
                    "enum": ["approve", "reject"],
                },
                "reviewer": {"type": "string"},
                "notes": {"type": "string"},
            },
        },
        "metadata": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high", "critical"],
                },
                "timestamp": {"type": "string"},
            },
        },
    },
}

_report_validator = Draft7Validator(REPORT_V1_SCHEMA)
_task_validator = Draft7Validator(CONTROLLER_TASK_SCHEMA)

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class ParseResult:
    """Outcome of parsing a report or task file."""

    ok: bool
    data: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API — report validation
# ---------------------------------------------------------------------------


def parse_report_file(report_path: Path) -> ParseResult:
    """Read and validate an agent report file."""
    if not report_path.exists():
        return ParseResult(ok=False, errors=[f"Report file not found: {report_path}"])

    try:
        raw = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        return ParseResult(ok=False, errors=[f"Cannot read report file: {exc}"])

    return parse_report(raw)


def parse_report(raw_json: str) -> ParseResult:
    """Validate a raw JSON string as a report_v1."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return ParseResult(ok=False, errors=[f"Invalid JSON: {exc}"])

    return validate_report(data)


def validate_report(report: dict[str, Any]) -> ParseResult:
    """Validate an already-parsed dict against report_v1 schema."""
    schema_errors = sorted(
        _report_validator.iter_errors(report), key=lambda e: list(e.path)
    )
    if schema_errors:
        msgs = [
            f"Schema: {'.'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}"
            for e in schema_errors
        ]
        return ParseResult(ok=False, errors=msgs)

    return ParseResult(ok=True, data=report)


# ---------------------------------------------------------------------------
# Public API — controller task validation
# ---------------------------------------------------------------------------


def parse_task_file(task_path: Path) -> ParseResult:
    """Read and validate a controller task file."""
    if not task_path.exists():
        return ParseResult(ok=False, errors=[f"Task file not found: {task_path}"])

    try:
        raw = task_path.read_text(encoding="utf-8")
    except OSError as exc:
        return ParseResult(ok=False, errors=[f"Cannot read task file: {exc}"])

    return parse_task(raw)


def parse_task(raw_json: str) -> ParseResult:
    """Validate a raw JSON string as a controller task."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return ParseResult(ok=False, errors=[f"Invalid JSON: {exc}"])

    return validate_task(data)


def validate_task(task: dict[str, Any]) -> ParseResult:
    """Validate against controller task schema + semantic rules."""
    schema_errors = sorted(
        _task_validator.iter_errors(task), key=lambda e: list(e.path)
    )
    if schema_errors:
        msgs = [
            f"Schema: {'.'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}"
            for e in schema_errors
        ]
        return ParseResult(ok=False, errors=msgs)

    semantic_errors = _semantic_checks(task)
    if semantic_errors:
        return ParseResult(ok=False, errors=semantic_errors)

    return ParseResult(ok=True, data=task)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _semantic_checks(task: dict[str, Any]) -> list[str]:
    """Business-rule validations beyond JSON Schema."""
    errors: list[str] = []
    skill = task["skill"]
    task_input = task.get("input", {})

    if skill == "process_inbox":
        # team is optional (process all if missing), no extra checks
        pass
    elif skill == "emit_directive":
        if not task_input.get("directive"):
            errors.append("emit_directive requires 'input.directive' to be provided")
    elif skill == "reroute_task":
        if not task_input.get("failed_agent"):
            errors.append("reroute_task requires 'input.failed_agent'")
        if not task_input.get("task"):
            errors.append("reroute_task requires 'input.task'")
    elif skill == "aggregate_team_reports":
        if not task_input.get("team"):
            errors.append("aggregate_team_reports requires 'input.team'")
    elif skill == "review_candidate":
        if not task_input.get("candidate_id"):
            errors.append("review_candidate requires 'input.candidate_id'")
        decision = task_input.get("decision")
        if decision not in ("approve", "reject"):
            errors.append("review_candidate requires 'input.decision' = 'approve' | 'reject'")

    return errors
