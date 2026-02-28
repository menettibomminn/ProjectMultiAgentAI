"""Tests for SheetsClient integration in SheetsAgent.

All tests mock ``utils.sheets_client.SheetsClient`` so they run fully offline.
They verify:
  - With GOOGLE_SHEETS_ENABLED=true → SheetsClient methods are called.
  - With GOOGLE_SHEETS_ENABLED unset → SheetsClient is never invoked.
  - Error handling (429, 403, auth errors) produces structured error output.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from Agents.sheets_agent.config import SheetsAgentConfig
from Agents.sheets_agent.sheets_agent import SheetsAgent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TASK: dict[str, Any] = {
    "task_id": "int-test-001",
    "user_id": "user@example.com",
    "team_id": "sheets-team",
    "sheet": {
        "spreadsheet_id": "spreadsheet-abc",
        "sheet_name": "Sheet1",
    },
    "requested_changes": [
        {
            "op": "update",
            "range": "A1:B1",
            "values": [["hello", "world"]],
        },
    ],
    "metadata": {
        "source": "api",
        "priority": "normal",
        "timestamp": "2026-02-28T10:00:00Z",
    },
}


MULTI_OP_TASK: dict[str, Any] = {
    "task_id": "int-test-002",
    "user_id": "user@example.com",
    "team_id": "sheets-team",
    "sheet": {
        "spreadsheet_id": "spreadsheet-abc",
        "sheet_name": "Sheet1",
    },
    "requested_changes": [
        {
            "op": "update",
            "range": "A1:B1",
            "values": [["a", "b"]],
        },
        {
            "op": "clear_range",
            "range": "C1:D1",
        },
        {
            "op": "delete_row",
            "range": "E5:E5",
        },
    ],
    "metadata": {
        "source": "web-ui",
        "priority": "high",
        "timestamp": "2026-02-28T10:00:00Z",
    },
}


def _make_config(
    tmp_path: Path, *, enabled: bool = False
) -> SheetsAgentConfig:
    """Build a test config rooted at *tmp_path*."""
    agent_id = "int-agent"
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
    )


def _write_task(
    config: SheetsAgentConfig, task: dict[str, Any]
) -> Path:
    path = config.task_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(task), encoding="utf-8")
    return path


def _mock_response(
    *,
    status: str = "success",
    updated_cells: int = 0,
    cleared_range: str = "",
    retries_used: int = 0,
) -> MagicMock:
    resp = MagicMock()
    resp.status = MagicMock()
    resp.status.value = status
    resp.updated_cells = updated_cells
    resp.cleared_range = cleared_range
    resp.retries_used = retries_used
    resp.data = None
    resp.error = ""
    resp.error_code = 0
    return resp


# ---------------------------------------------------------------------------
# Tests — toggle behaviour
# ---------------------------------------------------------------------------


class TestToggle:
    """Verify that SheetsClient is only used when the toggle is on."""

    @patch("Agents.sheets_agent.sheets_agent.SheetsAgent._execute_changes")
    def test_disabled_by_default(
        self, mock_exec: MagicMock, tmp_path: Path
    ) -> None:
        """When google_sheets_enabled=False, _execute_changes is never called."""
        config = _make_config(tmp_path, enabled=False)
        _write_task(config, SAMPLE_TASK)
        agent = SheetsAgent(config)
        agent.run_once()
        mock_exec.assert_not_called()

    @patch("utils.sheets_client.SheetsClient")
    def test_enabled_calls_client(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        """When google_sheets_enabled=True, SheetsClient.write_range is called."""
        mock_client = MagicMock()
        mock_client.write_range.return_value = _mock_response(
            status="success", updated_cells=2
        )
        mock_cls.return_value = mock_client

        config = _make_config(tmp_path, enabled=True)
        _write_task(config, SAMPLE_TASK)
        agent = SheetsAgent(config)
        result = agent.run_once()

        assert result is True
        mock_client.write_range.assert_called_once_with(
            "spreadsheet-abc", "A1:B1", [["hello", "world"]]
        )

        # Verify execution_results in report
        report = json.loads(
            config.report_file.read_text(encoding="utf-8")
        )
        assert "execution_results" in report
        assert report["execution_results"][0]["status"] == "success"
        assert report["execution_results"][0]["updated_cells"] == 2


# ---------------------------------------------------------------------------
# Tests — multi-op mapping
# ---------------------------------------------------------------------------


class TestOpMapping:
    """Verify that task ops map to the correct SheetsClient methods."""

    @patch("utils.sheets_client.SheetsClient")
    def test_multi_op_mapping(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        mock_client = MagicMock()
        mock_client.write_range.return_value = _mock_response(
            status="success", updated_cells=2
        )
        mock_client.clear_range.return_value = _mock_response(
            status="success", cleared_range="Sheet1!C1:D1"
        )
        mock_cls.return_value = mock_client

        config = _make_config(tmp_path, enabled=True)
        _write_task(config, MULTI_OP_TASK)
        agent = SheetsAgent(config)
        agent.run_once()

        # update → write_range
        mock_client.write_range.assert_called_once_with(
            "spreadsheet-abc", "A1:B1", [["a", "b"]]
        )
        # clear_range + delete_row → 2 calls to clear_range
        assert mock_client.clear_range.call_count == 2
        mock_client.clear_range.assert_any_call(
            "spreadsheet-abc", "C1:D1"
        )
        mock_client.clear_range.assert_any_call(
            "spreadsheet-abc", "E5:E5"
        )


# ---------------------------------------------------------------------------
# Tests — error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Verify that SheetsClient errors produce structured error results."""

    @patch("utils.sheets_client.SheetsClient")
    def test_rate_limit_error(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        from utils.sheets_client import SheetsRateLimitError

        mock_client = MagicMock()
        mock_client.write_range.side_effect = SheetsRateLimitError(
            "Rate limit exceeded after 5 retries", code=429
        )
        mock_cls.return_value = mock_client

        config = _make_config(tmp_path, enabled=True)
        _write_task(config, SAMPLE_TASK)
        agent = SheetsAgent(config)
        result = agent.run_once()

        assert result is True  # agent itself succeeds (report written)

        report = json.loads(
            config.report_file.read_text(encoding="utf-8")
        )
        assert report["status"] == "error"
        exec_r = report["execution_results"][0]
        assert exec_r["status"] == "error"
        assert exec_r["error_code"] == 429
        assert "Rate limit" in exec_r["error_message"]

    @patch("utils.sheets_client.SheetsClient")
    def test_permission_error(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        from utils.sheets_client import SheetsPermissionError

        mock_client = MagicMock()
        mock_client.write_range.side_effect = SheetsPermissionError(
            "Permission denied", code=403
        )
        mock_cls.return_value = mock_client

        config = _make_config(tmp_path, enabled=True)
        _write_task(config, SAMPLE_TASK)
        agent = SheetsAgent(config)
        agent.run_once()

        report = json.loads(
            config.report_file.read_text(encoding="utf-8")
        )
        assert report["status"] == "error"
        assert report["execution_results"][0]["error_code"] == 403

    @patch("utils.sheets_client.SheetsClient")
    def test_auth_error_fails_all_changes(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        """If SheetsClient init fails, all changes get error status."""
        from utils.sheets_client import SheetsAuthError

        mock_cls.side_effect = SheetsAuthError(
            "No credentials path provided"
        )

        config = _make_config(tmp_path, enabled=True)
        _write_task(config, SAMPLE_TASK)
        agent = SheetsAgent(config)
        agent.run_once()

        report = json.loads(
            config.report_file.read_text(encoding="utf-8")
        )
        assert report["status"] == "error"
        assert len(report["execution_results"]) == 1
        assert report["execution_results"][0]["status"] == "error"
        assert "credentials" in report["execution_results"][0]["error_message"].lower()

    @patch("utils.sheets_client.SheetsClient")
    def test_not_found_error(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        from utils.sheets_client import SheetsNotFoundError

        mock_client = MagicMock()
        mock_client.write_range.side_effect = SheetsNotFoundError(
            "Spreadsheet not found", code=404
        )
        mock_cls.return_value = mock_client

        config = _make_config(tmp_path, enabled=True)
        _write_task(config, SAMPLE_TASK)
        agent = SheetsAgent(config)
        agent.run_once()

        report = json.loads(
            config.report_file.read_text(encoding="utf-8")
        )
        assert report["status"] == "error"
        assert report["execution_results"][0]["error_code"] == 404


# ---------------------------------------------------------------------------
# Tests — config env var
# ---------------------------------------------------------------------------


class TestConfigEnv:
    """Verify GOOGLE_SHEETS_ENABLED env var parsing."""

    def test_env_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_SHEETS_ENABLED", "true")
        cfg = SheetsAgentConfig.from_env()
        assert cfg.google_sheets_enabled is True

    def test_env_True_uppercase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_SHEETS_ENABLED", "True")
        cfg = SheetsAgentConfig.from_env()
        assert cfg.google_sheets_enabled is True

    def test_env_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_SHEETS_ENABLED", "false")
        cfg = SheetsAgentConfig.from_env()
        assert cfg.google_sheets_enabled is False

    def test_env_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GOOGLE_SHEETS_ENABLED", raising=False)
        cfg = SheetsAgentConfig.from_env()
        assert cfg.google_sheets_enabled is False
