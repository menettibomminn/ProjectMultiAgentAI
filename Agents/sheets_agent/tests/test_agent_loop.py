"""Tests for AgentLoop."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from Agents.sheets_agent.agent_loop import AgentLoop
from Agents.sheets_agent.config import SheetsAgentConfig
from Agents.sheets_agent.sheets_agent import SheetsAgent


SAMPLE_TASK: dict[str, Any] = {
    "task_id": "loop-test-001",
    "user_id": "user@example.com",
    "team_id": "sheets-team",
    "sheet": {
        "spreadsheet_id": "sp-loop",
        "sheet_name": "Sheet1",
    },
    "requested_changes": [
        {
            "op": "update",
            "range": "A1:B1",
            "values": [["a", "b"]],
        },
    ],
    "metadata": {
        "source": "api",
        "priority": "normal",
        "timestamp": "2026-02-28T10:00:00Z",
    },
}


def _make_config(tmp_path: Path) -> SheetsAgentConfig:
    agent_id = "loop-agent"
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
        poll_interval_seconds=1,
        health_interval_cycles=2,
        max_consecutive_errors=3,
    )


class TestAgentLoopCreation:
    def test_creation(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        agent = SheetsAgent(config)
        loop = AgentLoop(agent=agent, config=config)
        assert loop._running is False
        assert loop._cycles == 0


class TestPollCycle:
    @patch("infra.adapter_factory.get_queue_adapter")
    def test_task_available_processed(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """When a task is in the queue, it is processed."""
        config = _make_config(tmp_path)
        agent = SheetsAgent(config)
        loop = AgentLoop(agent=agent, config=config)

        mock_adapter = MagicMock()
        mock_adapter.pop.return_value = SAMPLE_TASK
        loop._queue_adapter = mock_adapter

        # Mock run_once_from_dict to avoid real processing
        agent.run_once_from_dict = MagicMock(return_value=True)  # type: ignore[assignment]

        result = loop._poll_cycle()
        assert result is True
        agent.run_once_from_dict.assert_called_once_with(SAMPLE_TASK)

    @patch("infra.adapter_factory.get_queue_adapter")
    def test_no_task_noop(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """When the queue is empty, poll returns False."""
        config = _make_config(tmp_path)
        agent = SheetsAgent(config)
        loop = AgentLoop(agent=agent, config=config)

        mock_adapter = MagicMock()
        mock_adapter.pop.return_value = None
        loop._queue_adapter = mock_adapter

        result = loop._poll_cycle()
        assert result is False

    @patch("infra.adapter_factory.get_queue_adapter")
    def test_error_increments_count(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """When processing fails, health error count increments."""
        config = _make_config(tmp_path)
        agent = SheetsAgent(config)
        loop = AgentLoop(agent=agent, config=config)

        mock_adapter = MagicMock()
        mock_adapter.pop.return_value = SAMPLE_TASK
        loop._queue_adapter = mock_adapter

        agent.run_once_from_dict = MagicMock(  # type: ignore[assignment]
            side_effect=RuntimeError("boom"),
        )

        result = loop._poll_cycle()
        assert result is False
        assert loop._health._consecutive_errors == 1


class TestStopAndHealth:
    def test_stop_sets_running_false(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        agent = SheetsAgent(config)
        loop = AgentLoop(agent=agent, config=config)
        loop._running = True
        loop.stop()
        assert loop._running is False

    @patch("infra.adapter_factory.get_queue_adapter")
    def test_max_errors_stops_loop(
        self, mock_factory: MagicMock, tmp_path: Path
    ) -> None:
        """Loop stops after max_consecutive_errors."""
        config = _make_config(tmp_path)
        agent = SheetsAgent(config)
        loop = AgentLoop(agent=agent, config=config)

        mock_adapter = MagicMock()
        mock_adapter.pop.return_value = SAMPLE_TASK
        mock_factory.return_value = mock_adapter

        agent.run_once_from_dict = MagicMock(  # type: ignore[assignment]
            side_effect=RuntimeError("boom"),
        )

        # Monkey-patch _register_signals to avoid signal handler issues
        loop._register_signals = MagicMock()  # type: ignore[assignment]
        loop.start()

        # Should have stopped after max_consecutive_errors (3)
        assert loop._running is False
        assert loop._health._consecutive_errors >= 3

    def test_health_tick_writes(self, tmp_path: Path) -> None:
        """_health_tick appends to HEALTH.md."""
        config = _make_config(tmp_path)
        agent = SheetsAgent(config)
        loop = AgentLoop(agent=agent, config=config)
        loop._health.record_success("t1")

        loop._health_tick()

        text = config.health_file.read_text(encoding="utf-8")
        assert "Loop Health" in text
        assert "t1" in text
