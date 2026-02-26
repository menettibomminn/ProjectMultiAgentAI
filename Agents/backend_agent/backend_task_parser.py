"""Parse and validate incoming backend task JSON files against a strict JSON Schema.

Operations supported:
- process_sheet_request: Apply changes to a sheet.
- validate_payload: Validate a payload against a named schema.
- aggregate_reports: Aggregate a list of reports into a summary.
- route_directive: Route a directive to the appropriate handler.
- compute_diff: Compute the diff between two versions of a resource.
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
    "title": "BackendAgentTask",
    "type": "object",
    "required": [
        "task_id",
        "user_id",
        "team_id",
        "request",
        "metadata",
    ],
    "additionalProperties": False,
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "user_id": {"type": "string", "minLength": 1},
        "team_id": {"type": "string", "minLength": 1},
        "request": {
            "type": "object",
            "required": ["operation"],
            "additionalProperties": False,
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "process_sheet_request",
                        "validate_payload",
                        "aggregate_reports",
                        "route_directive",
                        "compute_diff",
                    ],
                },
                "sheet_id": {"type": "string", "minLength": 1},
                "changes": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "payload": {"type": "object"},
                "schema_name": {"type": "string", "minLength": 1},
                "reports": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "directive": {"type": "string", "minLength": 1},
            },
        },
        "metadata": {
            "type": "object",
            "required": ["source", "priority", "timestamp"],
            "additionalProperties": False,
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["web-ui", "api", "system", "scheduler"],
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
    """Validate a raw JSON string as a backend agent task."""
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
    req = task["request"]
    op = req["operation"]

    # process_sheet_request requires sheet_id AND changes (non-empty)
    if op == "process_sheet_request":
        if not req.get("sheet_id"):
            errors.append(
                "Operation 'process_sheet_request' requires 'sheet_id'"
            )
        changes = req.get("changes")
        if not changes or len(changes) == 0:
            errors.append(
                "Operation 'process_sheet_request' requires non-empty 'changes'"
            )

    # validate_payload requires payload AND schema_name
    if op == "validate_payload":
        if not req.get("payload"):
            errors.append(
                "Operation 'validate_payload' requires 'payload'"
            )
        if not req.get("schema_name"):
            errors.append(
                "Operation 'validate_payload' requires 'schema_name'"
            )

    # aggregate_reports requires reports (non-empty)
    if op == "aggregate_reports":
        reports = req.get("reports")
        if not reports or len(reports) == 0:
            errors.append(
                "Operation 'aggregate_reports' requires non-empty 'reports'"
            )

    return errors
