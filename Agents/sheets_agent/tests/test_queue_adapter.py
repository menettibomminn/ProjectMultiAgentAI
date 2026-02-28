"""Tests for Redis/queue adapter integration in SheetsAgent.

All tests mock the adapter — no real Redis needed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from Agents.sheets_agent.config import SheetsAgentConfig
from Agents.sheets_agent.sheets_agent import SheetsAgent


SAMPLE_TASK: dict[str, Any] = {
    "task_id": "queue-test-001",
    "user_id": "user@example.com",
    "team_id": "sheets-team",
    "sheet": {
        "spreadsheet_id": "sp-abc",
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


def _make_config(
    tmp_path: Path, *, redis: bool = False
) -> SheetsAgentConfig:
    agent_id = "q-agent"
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
        redis_enabled=redis,
    )


# ---------------------------------------------------------------------------
# Toggle behaviour
# ---------------------------------------------------------------------------


class TestRedisToggle:
    """Verify adapter is only used when redis_enabled=True."""

    def test_disabled_uses_filesystem(self, tmp_path: Path) -> None:
        """With redis_enabled=False, agent reads from filesystem as usual."""
        config = _make_config(tmp_path, redis=False)
        task_path = config.task_file
        task_path.write_text(json.dumps(SAMPLE_TASK), encoding="utf-8")

        agent = SheetsAgent(config)
        result = agent.run_once()
        assert result is True

        # Report written to filesystem
        assert config.report_file.exists()

    @patch("infra.adapter_factory.get_queue_adapter")
    def test_enabled_pops_from_adapter(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """With redis_enabled=True, agent pops task from adapter."""
        mock_adapter = MagicMock()
        mock_adapter.pop.return_value = SAMPLE_TASK
        mock_factory.return_value = mock_adapter

        config = _make_config(tmp_path, redis=True)
        agent = SheetsAgent(config)
        result = agent.run_once()

        assert result is True
        mock_adapter.pop.assert_called_once_with("inbox:sheets-team")
        mock_adapter.push.assert_called_once()
        # Verify the push was to the outbox
        call_args = mock_adapter.push.call_args
        assert call_args[0][0] == "outbox:sheets-team"
        report: dict[str, Any] = call_args[0][1]
        assert report["task_id"] == "queue-test-001"
        assert report["status"] == "success"

    @patch("infra.adapter_factory.get_queue_adapter")
    def test_enabled_no_task_returns_false(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """When queue is empty, agent returns False."""
        mock_adapter = MagicMock()
        mock_adapter.pop.return_value = None
        mock_factory.return_value = mock_adapter

        config = _make_config(tmp_path, redis=True)
        agent = SheetsAgent(config)
        result = agent.run_once()

        assert result is False


# ---------------------------------------------------------------------------
# Report output routing
# ---------------------------------------------------------------------------


class TestOutputRouting:
    """Verify reports go to the right destination."""

    @patch("infra.adapter_factory.get_queue_adapter")
    def test_report_pushed_to_outbox(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        mock_adapter = MagicMock()
        mock_adapter.pop.return_value = SAMPLE_TASK
        mock_factory.return_value = mock_adapter

        config = _make_config(tmp_path, redis=True)
        SheetsAgent(config).run_once()

        # Report should NOT be written to filesystem in queue mode
        assert not config.report_file.exists()
        # Should be pushed to adapter
        mock_adapter.push.assert_called_once()

    @patch("infra.adapter_factory.get_queue_adapter")
    def test_error_report_pushed_to_outbox(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """Validation errors are also routed through the adapter."""
        mock_adapter = MagicMock()
        mock_adapter.pop.return_value = {"bad": "task"}
        mock_factory.return_value = mock_adapter

        config = _make_config(tmp_path, redis=True)
        SheetsAgent(config).run_once()

        mock_adapter.push.assert_called_once()
        report: dict[str, Any] = mock_adapter.push.call_args[0][1]
        assert report["status"] == "error"

    def test_no_archive_when_queue_sourced(
        self, tmp_path: Path
    ) -> None:
        """Queue-sourced tasks should not attempt file archival."""
        with patch(
            "infra.adapter_factory.get_queue_adapter"
        ) as mock_factory:
            mock_adapter = MagicMock()
            mock_adapter.pop.return_value = SAMPLE_TASK
            mock_factory.return_value = mock_adapter

            config = _make_config(tmp_path, redis=True)
            SheetsAgent(config).run_once()

            # No .done.json file should exist
            done_files = list(
                config.inbox_dir.glob("*.done.json")
            )
            assert len(done_files) == 0


# ---------------------------------------------------------------------------
# Config env var
# ---------------------------------------------------------------------------


class TestConfigRedisEnabled:
    """Verify REDIS_ENABLED env var parsing in config."""

    def test_env_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDIS_ENABLED", "true")
        cfg = SheetsAgentConfig.from_env()
        assert cfg.redis_enabled is True

    def test_env_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REDIS_ENABLED", raising=False)
        cfg = SheetsAgentConfig.from_env()
        assert cfg.redis_enabled is False
