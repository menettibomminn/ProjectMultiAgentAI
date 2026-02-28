"""End-to-end test: simulate a real write via run_once_from_dict.

All Google Sheets API calls are mocked, but the test verifies the full
pipeline: task dict → validate → lock → rate limit → ExecutionEngine
→ SheetsClient.write_range → report → outbox → audit → HEALTH.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from Agents.sheets_agent.config import SheetsAgentConfig
from Agents.sheets_agent.health_reporter import HealthReporter
from Agents.sheets_agent.sheets_agent import SheetsAgent


SAMPLE_TASK: dict[str, Any] = {
    "task_id": "real-write-001",
    "user_id": "user@example.com",
    "team_id": "sheets-team",
    "sheet": {
        "spreadsheet_id": "sp-real",
        "sheet_name": "Sheet1",
    },
    "requested_changes": [
        {
            "op": "update",
            "range": "A2:C2",
            "values": [["Mario", "Rossi", "100"]],
        },
    ],
    "metadata": {
        "source": "web-ui",
        "priority": "normal",
        "timestamp": "2026-02-28T10:00:00Z",
    },
}


def _make_config(
    tmp_path: Path, *, enabled: bool = True, verify: bool = False
) -> SheetsAgentConfig:
    agent_id = "real-agent"
    inbox = tmp_path / "inbox" / "sheets" / agent_id
    inbox.mkdir(parents=True)
    (tmp_path / "audit" / "sheets" / agent_id).mkdir(parents=True)
    (tmp_path / "locks").mkdir(parents=True)
    health = tmp_path / "HEALTH.md"
    health.write_text("# HEALTH\n", encoding="utf-8")
    return SheetsAgentConfig(
        agent_id=agent_id,
        team_id="sheets-team",
        project_root=tmp_path,
        health_file_override=health,
        google_sheets_enabled=enabled,
        verify_writes=verify,
    )


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


class TestRealWrite:
    """Simulate a full write cycle through run_once_from_dict."""

    @patch("infra.adapter_factory.get_queue_adapter")
    @patch("utils.sheets_client.SheetsClient")
    def test_write_produces_execution_results(
        self,
        mock_client_cls: MagicMock,
        mock_factory: MagicMock,
        tmp_path: Path,
    ) -> None:
        """The report contains execution_results with status=success."""
        mock_client = MagicMock()
        mock_client.write_range.return_value = _mock_response(
            status="success", updated_cells=3,
        )
        mock_client_cls.return_value = mock_client

        mock_adapter = MagicMock()
        mock_factory.return_value = mock_adapter

        config = _make_config(tmp_path, enabled=True)
        agent = SheetsAgent(config)
        success = agent.run_once_from_dict(SAMPLE_TASK)

        assert success is True

        # Verify the report was pushed to outbox
        mock_adapter.push.assert_called_once()
        call_args = mock_adapter.push.call_args
        assert call_args[0][0] == "outbox:sheets-team"
        report: dict[str, Any] = call_args[0][1]
        assert report["task_id"] == "real-write-001"
        assert report["status"] == "success"
        assert "execution_results" in report
        assert report["execution_results"][0]["status"] == "success"
        assert report["execution_results"][0]["updated_cells"] == 3

    @patch("infra.adapter_factory.get_queue_adapter")
    @patch("utils.sheets_client.SheetsClient")
    def test_audit_log_written(
        self,
        mock_client_cls: MagicMock,
        mock_factory: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Audit log is created after run_once_from_dict."""
        mock_client = MagicMock()
        mock_client.write_range.return_value = _mock_response(
            status="success", updated_cells=3,
        )
        mock_client_cls.return_value = mock_client
        mock_factory.return_value = MagicMock()

        config = _make_config(tmp_path, enabled=True)
        agent = SheetsAgent(config)
        agent.run_once_from_dict(SAMPLE_TASK)

        audit_files = list(config.audit_dir.glob("*.json"))
        assert len(audit_files) == 1
        audit = json.loads(audit_files[0].read_text(encoding="utf-8"))
        assert audit["task_id"] == "real-write-001"
        assert audit["agent_id"] == "real-agent"
        assert audit["error"] is None

    @patch("infra.adapter_factory.get_queue_adapter")
    @patch("utils.sheets_client.SheetsClient")
    def test_health_updated(
        self,
        mock_client_cls: MagicMock,
        mock_factory: MagicMock,
        tmp_path: Path,
    ) -> None:
        """HEALTH.md is updated after run_once_from_dict."""
        mock_client = MagicMock()
        mock_client.write_range.return_value = _mock_response(
            status="success", updated_cells=3,
        )
        mock_client_cls.return_value = mock_client
        mock_factory.return_value = MagicMock()

        config = _make_config(tmp_path, enabled=True)
        agent = SheetsAgent(config)
        agent.run_once_from_dict(SAMPLE_TASK)

        health_text = config.health_file.read_text(encoding="utf-8")
        assert "real-write-001" in health_text
        assert "healthy" in health_text

    @patch("infra.adapter_factory.get_queue_adapter")
    def test_disabled_no_execution(
        self,
        mock_factory: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When google_sheets_enabled=False, no execution_results."""
        mock_adapter = MagicMock()
        mock_factory.return_value = mock_adapter

        config = _make_config(tmp_path, enabled=False)
        agent = SheetsAgent(config)
        success = agent.run_once_from_dict(SAMPLE_TASK)

        assert success is True
        report: dict[str, Any] = mock_adapter.push.call_args[0][1]
        assert "execution_results" not in report
        assert report["status"] == "success"

    @patch("infra.adapter_factory.get_queue_adapter")
    def test_invalid_task_returns_false(
        self,
        mock_factory: MagicMock,
        tmp_path: Path,
    ) -> None:
        """An invalid task dict produces an error report and returns False."""
        mock_adapter = MagicMock()
        mock_factory.return_value = mock_adapter

        config = _make_config(tmp_path, enabled=False)
        agent = SheetsAgent(config)
        success = agent.run_once_from_dict({"bad": "task"})

        assert success is False
        report: dict[str, Any] = mock_adapter.push.call_args[0][1]
        assert report["status"] == "error"

    @patch("infra.adapter_factory.get_queue_adapter")
    @patch("utils.sheets_client.SheetsClient")
    def test_verify_writes_read_back(
        self,
        mock_client_cls: MagicMock,
        mock_factory: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When verify_writes=True, read-back is performed."""
        mock_client = MagicMock()
        mock_client.write_range.return_value = _mock_response(
            status="success", updated_cells=3,
        )
        mock_client.read_range.return_value = _mock_response(
            data=[["Mario", "Rossi", "100"]],
        )
        mock_client_cls.return_value = mock_client
        mock_factory.return_value = MagicMock()

        config = _make_config(tmp_path, enabled=True, verify=True)
        agent = SheetsAgent(config)
        success = agent.run_once_from_dict(SAMPLE_TASK)

        assert success is True
        mock_client.read_range.assert_called_once()


class TestHealthReporter:
    def test_report_snapshot(self) -> None:
        hr = HealthReporter(agent_id="test-agent")
        hr.record_success("t1")
        hr.record_success("t2")
        snap = hr.report()

        assert snap["agent_id"] == "test-agent"
        assert snap["status"] == "healthy"
        assert snap["tasks_processed"] == 2
        assert snap["tasks_failed"] == 0
        assert snap["consecutive_errors"] == 0
        assert snap["last_task_id"] == "t2"
        assert "last_health_check" in snap

    def test_is_healthy_false_after_errors(self) -> None:
        hr = HealthReporter(agent_id="test-agent", max_consecutive_errors=3)
        hr.record_error("t1", "err1")
        hr.record_error("t2", "err2")
        assert hr.is_healthy() is True

        hr.record_error("t3", "err3")
        assert hr.is_healthy() is False

    def test_success_resets_consecutive(self) -> None:
        hr = HealthReporter(agent_id="test-agent", max_consecutive_errors=3)
        hr.record_error("t1", "err1")
        hr.record_error("t2", "err2")
        hr.record_success("t3")
        assert hr.is_healthy() is True
        assert hr._consecutive_errors == 0


class TestConfigNewParams:
    def test_from_env_loop_params(
        self, monkeypatch: Any,
    ) -> None:
        import pytest
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("SHEETS_LOOP_ENABLED", "true")
        monkeypatch.setenv("SHEETS_POLL_INTERVAL", "10")
        monkeypatch.setenv("SHEETS_HEALTH_INTERVAL", "20")
        monkeypatch.setenv("SHEETS_MAX_CONSECUTIVE_ERRORS", "8")
        monkeypatch.setenv("SHEETS_VERIFY_WRITES", "true")

        cfg = SheetsAgentConfig.from_env()
        assert cfg.loop_enabled is True
        assert cfg.poll_interval_seconds == 10
        assert cfg.health_interval_cycles == 20
        assert cfg.max_consecutive_errors == 8
        assert cfg.verify_writes is True

        monkeypatch.undo()
