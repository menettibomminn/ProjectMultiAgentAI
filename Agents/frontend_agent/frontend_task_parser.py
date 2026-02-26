"""Parse and validate incoming frontend task JSON files against a strict JSON Schema.

Operations supported:
- render_dashboard: Render a dashboard view with sheet data.
- render_approval_form: Render a form for approving changes.
- render_audit_log: Render an audit log table with optional filters.
- validate_input: Validate user-submitted form data against a schema.
- format_error: Format an error for UI display.

NOTE: This agent NEVER accesses Google Sheets directly.
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
    "title": "FrontendAgentTask",
    "type": "object",
    "required": [
        "task_id",
        "user_id",
        "team_id",
        "ui_request",
        "metadata",
    ],
    "additionalProperties": False,
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "user_id": {"type": "string", "minLength": 1},
        "team_id": {"type": "string", "minLength": 1},
        "ui_request": {
            "type": "object",
            "required": ["operation"],
            "additionalProperties": False,
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "render_dashboard",
                        "render_approval_form",
                        "render_audit_log",
                        "validate_input",
                        "format_error",
                    ],
                },
                "sheets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "name", "status"],
                        "additionalProperties": False,
                        "properties": {
                            "id": {"type": "string", "minLength": 1},
                            "name": {"type": "string", "minLength": 1},
                            "status": {"type": "string", "minLength": 1},
                        },
                    },
                },
                "change": {
                    "type": "object",
                    "required": ["change_id", "sheet_id", "changes"],
                    "additionalProperties": False,
                    "properties": {
                        "change_id": {"type": "string", "minLength": 1},
                        "sheet_id": {"type": "string", "minLength": 1},
                        "changes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": [
                                    "cell",
                                    "old_value",
                                    "new_value",
                                ],
                                "additionalProperties": False,
                                "properties": {
                                    "cell": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                    "old_value": {"type": "string"},
                                    "new_value": {"type": "string"},
                                },
                            },
                            "minItems": 1,
                        },
                    },
                },
                "filters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "agent": {"type": "string"},
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"},
                    },
                },
                "form_data": {"type": "object"},
                "schema_name": {"type": "string", "minLength": 1},
                "error": {
                    "type": "object",
                    "required": ["code", "message"],
                    "additionalProperties": False,
                    "properties": {
                        "code": {"type": "string", "minLength": 1},
                        "message": {"type": "string", "minLength": 1},
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
                    "enum": ["web-ui", "api", "system"],
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
    """Validate a raw JSON string as a frontend agent task."""
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
    ui_req = task["ui_request"]
    op = ui_req["operation"]

    # render_dashboard requires sheets (non-empty array)
    if op == "render_dashboard":
        sheets = ui_req.get("sheets")
        if not sheets or not isinstance(sheets, list) or len(sheets) == 0:
            errors.append(
                "Operation 'render_dashboard' requires a non-empty 'sheets' array"
            )

    # render_approval_form requires change object
    if op == "render_approval_form":
        if not ui_req.get("change"):
            errors.append(
                "Operation 'render_approval_form' requires a 'change' object"
            )

    # validate_input requires form_data AND schema_name
    if op == "validate_input":
        if not ui_req.get("form_data"):
            errors.append(
                "Operation 'validate_input' requires 'form_data'"
            )
        if not ui_req.get("schema_name"):
            errors.append(
                "Operation 'validate_input' requires 'schema_name'"
            )

    # format_error requires error object
    if op == "format_error":
        if not ui_req.get("error"):
            errors.append(
                "Operation 'format_error' requires an 'error' object"
            )

    return errors
