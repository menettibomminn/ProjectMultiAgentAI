"""Parse and validate incoming task JSON files against a strict JSON Schema.

Design decisions (documented in ARCHITECTURE.md):
- old_values is NOT required in the task — the agent does not read from Google Sheets.
- values is required for 'update' and 'append_row' ops; optional for 'delete_row'/'clear_range'.
- Additional semantic checks run after schema validation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator, ValidationError

# ---------------------------------------------------------------------------
# JSON Schema for task.json
# ---------------------------------------------------------------------------

TASK_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "SheetsWorkerTask",
    "type": "object",
    "required": [
        "task_id",
        "user_id",
        "team_id",
        "sheet",
        "requested_changes",
        "metadata",
    ],
    "additionalProperties": False,
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "user_id": {"type": "string", "minLength": 1},
        "team_id": {"type": "string", "minLength": 1},
        "sheet": {
            "type": "object",
            "required": ["spreadsheet_id", "sheet_name"],
            "additionalProperties": False,
            "properties": {
                "spreadsheet_id": {"type": "string", "minLength": 1},
                "sheet_name": {"type": "string", "minLength": 1},
            },
        },
        "requested_changes": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["op", "range"],
                "additionalProperties": False,
                "properties": {
                    "op": {
                        "type": "string",
                        "enum": ["update", "append_row", "delete_row", "clear_range"],
                    },
                    "range": {"type": "string", "minLength": 1},
                    "values": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
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
                    "enum": ["web-ui", "email", "api"],
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
    """Validate a raw JSON string as a sheets worker task."""
    try:
        task = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return ParseResult(ok=False, errors=[f"Invalid JSON: {exc}"])

    return validate_task(task)


def validate_task(task: dict[str, Any]) -> ParseResult:
    """Validate an already-parsed dict against schema + semantic rules."""
    schema_errors = sorted(_validator.iter_errors(task), key=lambda e: list(e.path))
    if schema_errors:
        msgs = [
            f"Schema: {'.'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}"
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
    for i, change in enumerate(task["requested_changes"]):
        op = change["op"]
        has_values = bool(change.get("values"))
        if op in ("update", "append_row") and not has_values:
            errors.append(
                f"requested_changes[{i}]: op '{op}' requires non-empty 'values'"
            )
        if op == "delete_row" and has_values:
            errors.append(
                f"requested_changes[{i}]: op 'delete_row' should not include 'values'"
            )
    return errors
