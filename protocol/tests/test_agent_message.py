"""Tests for AgentMessage protocol."""

from __future__ import annotations

import pytest

from protocol.message import (
    VALID_STATUSES,
    AgentMessage,
    InvalidMessageStatusError,
)


# -----------------------------------------------------------------------
# Creation
# -----------------------------------------------------------------------


class TestCreation:
    def test_success_message(self) -> None:
        msg = AgentMessage(
            status="success", agent="sheets_agent", action="process_task",
        )
        assert msg.status == "success"
        assert msg.agent == "sheets_agent"
        assert msg.action == "process_task"
        assert msg.error == ""
        assert msg.protocol_version == 1

    def test_error_message(self) -> None:
        msg = AgentMessage(
            status="error", agent="auth_agent", action="validate",
            error="token expired",
        )
        assert msg.status == "error"
        assert msg.error == "token expired"

    def test_retry_message(self) -> None:
        msg = AgentMessage(
            status="retry", agent="backend_agent", action="fetch",
        )
        assert msg.status == "retry"

    def test_timestamp_auto_generated(self) -> None:
        msg = AgentMessage(
            status="success", agent="a", action="b",
        )
        assert msg.timestamp  # non-empty
        assert "T" in msg.timestamp  # ISO format

    def test_frozen_immutability(self) -> None:
        msg = AgentMessage(
            status="success", agent="a", action="b",
        )
        with pytest.raises(AttributeError):
            msg.status = "error"  # type: ignore[misc]


# -----------------------------------------------------------------------
# Invalid status
# -----------------------------------------------------------------------


class TestInvalidStatus:
    def test_invalid_status_raises(self) -> None:
        with pytest.raises(InvalidMessageStatusError) as exc_info:
            AgentMessage(status="pending", agent="a", action="b")
        assert exc_info.value.status == "pending"

    def test_empty_status_raises(self) -> None:
        with pytest.raises(InvalidMessageStatusError):
            AgentMessage(status="", agent="a", action="b")

    @pytest.mark.parametrize("status", sorted(VALID_STATUSES))
    def test_all_valid_statuses_accepted(self, status: str) -> None:
        msg = AgentMessage(status=status, agent="a", action="b")
        assert msg.status == status


# -----------------------------------------------------------------------
# to_dict
# -----------------------------------------------------------------------


class TestToDict:
    def test_includes_envelope_fields(self) -> None:
        msg = AgentMessage(
            status="success", agent="x", action="y",
        )
        d = msg.to_dict()
        assert d["agent"] == "x"
        assert d["status"] == "success"
        assert d["action"] == "y"
        assert d["protocol_version"] == 1

    def test_merges_data_as_top_level(self) -> None:
        msg = AgentMessage(
            status="success", agent="x", action="y",
            data={"task_id": "t1", "summary": "ok"},
        )
        d = msg.to_dict()
        assert d["task_id"] == "t1"
        assert d["summary"] == "ok"

    def test_envelope_not_overridable_by_data(self) -> None:
        msg = AgentMessage(
            status="success", agent="real_agent", action="y",
            data={"agent": "fake_agent", "status": "fake"},
        )
        d = msg.to_dict()
        assert d["agent"] == "real_agent"
        assert d["status"] == "success"


# -----------------------------------------------------------------------
# from_dict
# -----------------------------------------------------------------------


class TestFromDict:
    def test_roundtrip(self) -> None:
        original = AgentMessage(
            status="success", agent="a", action="run",
            data={"task_id": "t1"},
        )
        restored = AgentMessage.from_dict(original.to_dict())
        assert restored.status == original.status
        assert restored.agent == original.agent
        assert restored.action == original.action
        assert restored.data is not None
        assert restored.data["task_id"] == "t1"

    def test_legacy_report_v1(self) -> None:
        legacy = {
            "agent_id": "sheets-worker-01",
            "status": "success",
            "task_id": "abc",
            "summary": "done",
        }
        msg = AgentMessage.from_dict(legacy)
        assert msg.agent == "sheets-worker-01"
        assert msg.status == "success"
        assert msg.data is not None
        assert msg.data["task_id"] == "abc"

    def test_fallback_agent_id_to_agent(self) -> None:
        d = {"agent_id": "old_agent", "status": "error", "error": "oops"}
        msg = AgentMessage.from_dict(d)
        assert msg.agent == "old_agent"
