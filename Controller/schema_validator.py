"""JSON Schema validation for Controller data structures.

Defines strict schemas for:
- Task objects (as managed by TaskManager)
- Audit log entries (as written by AuditManager)

Uses jsonschema Draft 7 for validation. Raises SchemaValidationError when
data does not conform to the schema.
"""
from __future__ import annotations

from typing import Any

from jsonschema import Draft7Validator, ValidationError

# ---------------------------------------------------------------------------
# Task schema
# ---------------------------------------------------------------------------

TASK_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ControllerManagedTask",
    "type": "object",
    "required": [
        "task_id",
        "status",
        "created_at",
        "updated_at",
        "payload",
        "retries",
    ],
    "additionalProperties": False,
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "task_type": {"type": "string"},
        "status": {
            "type": "string",
            "enum": [
                "PENDING",
                "ASSIGNED",
                "RUNNING",
                "WAITING_APPROVAL",
                "APPROVED",
                "REJECTED",
                "FAILED",
                "COMPLETED",
            ],
        },
        "created_at": {"type": "string", "minLength": 1},
        "updated_at": {"type": "string", "minLength": 1},
        "payload": {"type": "object"},
        "retries": {"type": "integer", "minimum": 0},
    },
}

# ---------------------------------------------------------------------------
# Audit log entry schema
# ---------------------------------------------------------------------------

AUDIT_LOG_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AuditLogEntry",
    "type": "object",
    "required": ["timestamp", "task_id", "agent", "action", "status"],
    "additionalProperties": False,
    "properties": {
        "timestamp": {"type": "string", "minLength": 1},
        "task_id": {"type": "string", "minLength": 1},
        "agent": {"type": "string"},
        "action": {"type": "string", "minLength": 1},
        "status": {"type": "string", "minLength": 1},
        "details": {"type": "object"},
    },
}

# Pre-compiled validators
_task_validator = Draft7Validator(TASK_SCHEMA)
_audit_validator = Draft7Validator(AUDIT_LOG_SCHEMA)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class SchemaValidationError(Exception):
    """Raised when data fails schema validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_task(data: dict[str, Any]) -> None:
    """Validate a task dict against the task schema.

    Raises SchemaValidationError if the data is invalid.
    """
    _validate(data, _task_validator)


def validate_audit(data: dict[str, Any]) -> None:
    """Validate an audit log entry against the audit schema.

    Raises SchemaValidationError if the data is invalid.
    """
    _validate(data, _audit_validator)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _validate(data: dict[str, Any], validator: Draft7Validator) -> None:
    """Run validation and collect all errors."""
    errors: list[str] = []
    err: ValidationError
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"{path}: {err.message}")
    if errors:
        raise SchemaValidationError(errors)
