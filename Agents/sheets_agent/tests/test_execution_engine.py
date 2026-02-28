"""Tests for ExecutionEngine, ChangeResult and ExecutionResult."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from Agents.sheets_agent.execution_engine import (
    ChangeResult,
    ExecutionEngine,
    ExecutionResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(
    *,
    status: str = "success",
    updated_cells: int = 0,
    cleared_range: str = "",
    retries_used: int = 0,
    data: list[list[str]] | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status = MagicMock()
    resp.status.value = status
    resp.updated_cells = updated_cells
    resp.cleared_range = cleared_range
    resp.retries_used = retries_used
    resp.data = data
    return resp


SAMPLE_TASK: dict[str, Any] = {
    "task_id": "exec-001",
    "user_id": "u@example.com",
    "team_id": "team",
    "sheet": {
        "spreadsheet_id": "sp-123",
        "sheet_name": "Sheet1",
    },
    "requested_changes": [
        {
            "op": "update",
            "range": "A1:B1",
            "values": [["x", "y"]],
        },
    ],
    "metadata": {
        "source": "api",
        "priority": "normal",
        "timestamp": "2026-02-28T10:00:00Z",
    },
}

MULTI_TASK: dict[str, Any] = {
    "task_id": "exec-002",
    "user_id": "u@example.com",
    "team_id": "team",
    "sheet": {
        "spreadsheet_id": "sp-123",
        "sheet_name": "Sheet1",
    },
    "requested_changes": [
        {"op": "update", "range": "A1:B1", "values": [["a", "b"]]},
        {"op": "clear_range", "range": "C1:D1"},
        {"op": "unknown_op", "range": "X1:X1"},
    ],
    "metadata": {
        "source": "api",
        "priority": "normal",
        "timestamp": "2026-02-28T10:00:00Z",
    },
}


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------

class TestDataClasses:
    def test_change_result_to_dict(self) -> None:
        cr = ChangeResult(
            op="update", range="A1:B1", status="success",
            updated_cells=4, verified=True, retries_used=1,
            duration_ms=50.0,
        )
        d = cr.to_dict()
        assert d["op"] == "update"
        assert d["status"] == "success"
        assert d["updated_cells"] == 4
        assert d["verified"] is True

    def test_execution_result_all_success(self) -> None:
        changes = [
            ChangeResult(op="update", range="A1", status="success"),
            ChangeResult(op="clear_range", range="B1", status="success"),
        ]
        er = ExecutionResult(
            task_id="t1", spreadsheet_id="sp",
            changes=changes, total_duration_ms=100.0,
        )
        assert er.all_success is True

    def test_execution_result_not_all_success(self) -> None:
        changes = [
            ChangeResult(op="update", range="A1", status="success"),
            ChangeResult(op="update", range="B1", status="error",
                         error_message="fail"),
        ]
        er = ExecutionResult(
            task_id="t1", spreadsheet_id="sp",
            changes=changes, total_duration_ms=100.0,
        )
        assert er.all_success is False


# ---------------------------------------------------------------------------
# Execute tests
# ---------------------------------------------------------------------------

class TestExecute:
    @patch("utils.sheets_client.SheetsClient")
    def test_single_write_success(
        self, mock_cls: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.write_range.return_value = _mock_response(
            status="success", updated_cells=2,
        )
        mock_cls.return_value = mock_client

        engine = ExecutionEngine()
        result = engine.execute(SAMPLE_TASK)

        assert len(result.changes) == 1
        assert result.changes[0].status == "success"
        assert result.changes[0].updated_cells == 2
        assert result.all_success is True
        assert result.task_id == "exec-001"
        assert result.spreadsheet_id == "sp-123"

    @patch("utils.sheets_client.SheetsClient")
    def test_mixed_success_and_error(
        self, mock_cls: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.write_range.return_value = _mock_response(
            status="success", updated_cells=2,
        )
        mock_client.clear_range.return_value = _mock_response(
            status="success", cleared_range="C1:D1",
        )
        mock_cls.return_value = mock_client

        engine = ExecutionEngine()
        result = engine.execute(MULTI_TASK)

        assert len(result.changes) == 3
        assert result.changes[0].status == "success"  # update
        assert result.changes[1].status == "success"  # clear_range
        assert result.changes[2].status == "skipped"  # unknown_op
        assert result.all_success is False

    @patch("utils.sheets_client.SheetsClient")
    def test_verify_writes_read_back(
        self, mock_cls: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.write_range.return_value = _mock_response(
            status="success", updated_cells=2,
        )
        mock_client.read_range.return_value = _mock_response(
            data=[["x", "y"]],
        )
        mock_cls.return_value = mock_client

        engine = ExecutionEngine(verify_writes=True)
        result = engine.execute(SAMPLE_TASK)

        assert result.changes[0].verified is True
        mock_client.read_range.assert_called_once_with("sp-123", "A1:B1")

    @patch("utils.sheets_client.SheetsClient")
    def test_sheets_client_error(
        self, mock_cls: MagicMock,
    ) -> None:
        from utils.sheets_client import SheetsPermissionError

        mock_client = MagicMock()
        mock_client.write_range.side_effect = SheetsPermissionError(
            "Permission denied", code=403,
        )
        mock_cls.return_value = mock_client

        engine = ExecutionEngine()
        result = engine.execute(SAMPLE_TASK)

        assert result.changes[0].status == "error"
        assert "Permission denied" in result.changes[0].error_message

    @patch("utils.sheets_client.SheetsClient")
    def test_auth_error_fails_all(
        self, mock_cls: MagicMock,
    ) -> None:
        from utils.sheets_client import SheetsAuthError

        mock_cls.side_effect = SheetsAuthError("no creds")

        engine = ExecutionEngine()
        result = engine.execute(SAMPLE_TASK)

        assert len(result.changes) == 1
        assert result.changes[0].status == "error"
        assert "no creds" in result.changes[0].error_message


# ---------------------------------------------------------------------------
# Per-op tests
# ---------------------------------------------------------------------------

class TestSingleChangeOps:
    @patch("utils.sheets_client.SheetsClient")
    def test_update_op(self, mock_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.write_range.return_value = _mock_response(
            status="success", updated_cells=4,
        )
        mock_cls.return_value = mock_client

        engine = ExecutionEngine()
        task = {**SAMPLE_TASK, "requested_changes": [
            {"op": "update", "range": "A1:B2", "values": [["1", "2"]]},
        ]}
        result = engine.execute(task)
        assert result.changes[0].op == "update"
        assert result.changes[0].updated_cells == 4

    @patch("utils.sheets_client.SheetsClient")
    def test_append_row_op(self, mock_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.write_range.return_value = _mock_response(
            status="success", updated_cells=3,
        )
        mock_cls.return_value = mock_client

        engine = ExecutionEngine()
        task = {**SAMPLE_TASK, "requested_changes": [
            {"op": "append_row", "range": "A5:C5", "values": [["a", "b", "c"]]},
        ]}
        result = engine.execute(task)
        assert result.changes[0].op == "append_row"
        mock_client.write_range.assert_called_once()

    @patch("utils.sheets_client.SheetsClient")
    def test_delete_row_op(self, mock_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.clear_range.return_value = _mock_response(
            status="success",
        )
        mock_cls.return_value = mock_client

        engine = ExecutionEngine()
        task = {**SAMPLE_TASK, "requested_changes": [
            {"op": "delete_row", "range": "A5:C5"},
        ]}
        result = engine.execute(task)
        assert result.changes[0].op == "delete_row"
        mock_client.clear_range.assert_called_once()

    @patch("utils.sheets_client.SheetsClient")
    def test_clear_range_op(self, mock_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.clear_range.return_value = _mock_response(
            status="success", cleared_range="Sheet1!A1:B2",
        )
        mock_cls.return_value = mock_client

        engine = ExecutionEngine()
        task = {**SAMPLE_TASK, "requested_changes": [
            {"op": "clear_range", "range": "A1:B2"},
        ]}
        result = engine.execute(task)
        assert result.changes[0].op == "clear_range"

    @patch("utils.sheets_client.SheetsClient")
    def test_unknown_op_skipped(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value = MagicMock()

        engine = ExecutionEngine()
        task = {**SAMPLE_TASK, "requested_changes": [
            {"op": "pivot_table", "range": "A1"},
        ]}
        result = engine.execute(task)
        assert result.changes[0].status == "skipped"
        assert "Unsupported op" in result.changes[0].error_message
