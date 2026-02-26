"""Parse and validate incoming auth task JSON files against a strict JSON Schema.

Operations supported:
- issue_token: Issue a new OAuth token for a user.
- refresh_token: Refresh an expiring token.
- revoke_token: Revoke a user's token.
- validate_scopes: Validate that requested scopes comply with policy.

SECURITY: This module NEVER handles actual token values.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

# ---------------------------------------------------------------------------
# Allowed scopes (policy-enforced)
# ---------------------------------------------------------------------------

ALLOWED_SCOPES = frozenset({"spreadsheets", "drive.file"})

# ---------------------------------------------------------------------------
# JSON Schema for task.json
# ---------------------------------------------------------------------------

TASK_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AuthAgentTask",
    "type": "object",
    "required": [
        "task_id",
        "user_id",
        "team_id",
        "auth_request",
        "metadata",
    ],
    "additionalProperties": False,
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "user_id": {"type": "string", "minLength": 1},
        "team_id": {"type": "string", "minLength": 1},
        "auth_request": {
            "type": "object",
            "required": ["operation", "auth_type", "scopes"],
            "additionalProperties": False,
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "issue_token",
                        "refresh_token",
                        "revoke_token",
                        "validate_scopes",
                    ],
                },
                "auth_type": {
                    "type": "string",
                    "enum": ["oauth_user", "service_account"],
                },
                "scopes": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                },
                "target_user_id": {"type": "string", "minLength": 1},
            },
        },
        "metadata": {
            "type": "object",
            "required": ["source", "priority", "timestamp"],
            "additionalProperties": False,
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["web-ui", "api", "scheduler", "system"],
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
    """Validate a raw JSON string as an auth agent task."""
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
    auth_req = task["auth_request"]
    op = auth_req["operation"]
    scopes = set(auth_req.get("scopes", []))

    # Scope policy: only allowed scopes
    invalid_scopes = scopes - ALLOWED_SCOPES
    if invalid_scopes:
        errors.append(
            f"Scope violation: {sorted(invalid_scopes)} not in allowed set "
            f"{sorted(ALLOWED_SCOPES)}"
        )

    # revoke_token requires target_user_id
    if op == "revoke_token" and not auth_req.get("target_user_id"):
        errors.append(
            "Operation 'revoke_token' requires 'target_user_id'"
        )

    return errors
