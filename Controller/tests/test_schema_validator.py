"""Tests for Controller.schema_validator."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from Controller.schema_validator import (
    SchemaValidationError,
    validate_audit,
    validate_task,
)


def _make_task(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "task_id": "abc123",
        "task_type": "process_inbox",
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "payload": {},
        "retries": 0,
    }
    base.update(overrides)
    return base


def _make_audit(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": "abc123",
        "agent": "controller",
        "action": "test_action",
        "status": "ok",
        "details": {},
    }
    base.update(overrides)
    return base


class TestValidateTask:
    def test_valid_task(self) -> None:
        validate_task(_make_task())

    def test_all_statuses(self) -> None:
        for status in [
            "PENDING", "ASSIGNED", "RUNNING", "WAITING_APPROVAL",
            "APPROVED", "REJECTED", "FAILED", "COMPLETED",
        ]:
            validate_task(_make_task(status=status))

    def test_invalid_status(self) -> None:
        with pytest.raises(SchemaValidationError) as exc_info:
            validate_task(_make_task(status="UNKNOWN"))
        assert "status" in exc_info.value.errors[0]

    def test_missing_required_field(self) -> None:
        data = _make_task()
        del data["task_id"]
        with pytest.raises(SchemaValidationError):
            validate_task(data)  # type: ignore[arg-type]

    def test_negative_retries(self) -> None:
        with pytest.raises(SchemaValidationError):
            validate_task(_make_task(retries=-1))

    def test_wrong_payload_type(self) -> None:
        with pytest.raises(SchemaValidationError):
            validate_task(_make_task(payload="not_a_dict"))

    def test_additional_properties_rejected(self) -> None:
        with pytest.raises(SchemaValidationError):
            validate_task(_make_task(extra_field="nope"))

    def test_errors_list_populated(self) -> None:
        try:
            validate_task(_make_task(status="BAD", retries=-1))
        except SchemaValidationError as exc:
            assert len(exc.errors) >= 1


class TestValidateAudit:
    def test_valid_audit(self) -> None:
        validate_audit(_make_audit())

    def test_missing_timestamp(self) -> None:
        data = _make_audit()
        del data["timestamp"]
        with pytest.raises(SchemaValidationError):
            validate_audit(data)  # type: ignore[arg-type]

    def test_missing_action(self) -> None:
        data = _make_audit()
        del data["action"]
        with pytest.raises(SchemaValidationError):
            validate_audit(data)  # type: ignore[arg-type]

    def test_empty_agent_allowed(self) -> None:
        validate_audit(_make_audit(agent=""))

    def test_details_must_be_object(self) -> None:
        with pytest.raises(SchemaValidationError):
            validate_audit(_make_audit(details="string"))

    def test_additional_properties_rejected(self) -> None:
        with pytest.raises(SchemaValidationError):
            validate_audit(_make_audit(extra="bad"))
