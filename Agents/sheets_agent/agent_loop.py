"""Agent loop — continuous polling loop for sheets_agent.

Reads tasks from the inbox queue, processes them via :class:`SheetsAgent`,
and pushes reports to the outbox.  Handles SIGINT/SIGTERM for graceful
shutdown and performs periodic health checks.
"""
from __future__ import annotations

import json
import logging
import signal
from typing import Any

from Agents.sheets_agent.config import SheetsAgentConfig
from Agents.sheets_agent.health_reporter import HealthReporter
from Agents.sheets_agent.sheets_agent import SheetsAgent

logger = logging.getLogger(__name__)


class AgentLoop:
    """Continuous polling loop for the sheets worker agent.

    Parameters
    ----------
    agent:
        A fully initialised :class:`SheetsAgent`.
    config:
        Agent configuration (provides polling intervals and thresholds).
    """

    def __init__(
        self,
        agent: SheetsAgent,
        config: SheetsAgentConfig,
    ) -> None:
        self._agent = agent
        self._config = config
        self._running = False
        self._cycles: int = 0
        self._health = HealthReporter(
            agent_id=config.agent_id,
            max_consecutive_errors=config.max_consecutive_errors,
        )
        self._queue_adapter: Any = None

    # -- Public API ----------------------------------------------------------

    def start(self) -> None:
        """Start the polling loop.  Blocks until :meth:`stop` is called."""
        self._running = True
        self._register_signals()

        from infra.adapter_factory import get_queue_adapter
        self._queue_adapter = get_queue_adapter()

        logger.info(
            "[LOOP] Starting agent loop (poll=%ds, health every %d cycles)",
            self._config.poll_interval_seconds,
            self._config.health_interval_cycles,
        )

        while self._running:
            self._poll_cycle()
            self._cycles += 1

            if self._cycles % self._config.health_interval_cycles == 0:
                self._health_tick()

            if not self._health.is_healthy():
                logger.error(
                    "[LOOP] Too many consecutive errors (%d) — shutting down",
                    self._config.max_consecutive_errors,
                )
                self._running = False

        logger.info("[LOOP] Loop stopped after %d cycles", self._cycles)

    def stop(self) -> None:
        """Request a graceful shutdown after the current cycle completes."""
        self._running = False

    # -- Internals -----------------------------------------------------------

    def _poll_cycle(self) -> bool:
        """Execute one poll-process cycle.  Returns ``True`` on task processed."""
        queue_name = f"inbox:{self._config.team_id}"

        task: dict[str, Any] | None = self._queue_adapter.pop(
            queue_name, timeout=self._config.poll_interval_seconds
        )
        if task is None:
            return False

        task_id = str(task.get("task_id", "unknown"))
        logger.info("[LOOP] Task %s received", task_id)

        try:
            success = self._agent.run_once_from_dict(task)
            if success:
                self._health.record_success(task_id)
            else:
                self._health.record_error(task_id, "run_once returned False")
            return success
        except Exception as exc:
            logger.error("[LOOP] Unhandled error processing %s: %s", task_id, exc)
            self._health.record_error(task_id, str(exc))
            return False

    def _health_tick(self) -> None:
        """Write a health report to the agent's health file."""
        health_data = self._health.report()
        logger.info(
            "[HEALTH] Status: %s | Processed: %d | Failed: %d",
            health_data["status"],
            health_data["tasks_processed"],
            health_data["tasks_failed"],
        )

        health_path = self._config.health_file
        try:
            entry = (
                f"\n### {health_data['last_health_check']} — Loop Health\n"
                f"\n"
                f"```json\n"
                f"{json.dumps(health_data, indent=2)}\n"
                f"```\n"
            )
            with open(health_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except OSError as exc:
            logger.warning("[HEALTH] Failed to write health report: %s", exc)

    def _register_signals(self) -> None:
        """Register SIGINT and SIGTERM handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Set the running flag to ``False`` on shutdown signal."""
        sig_name = signal.Signals(signum).name
        logger.info(
            "[LOOP] Shutdown signal received (%s), "
            "completing current task...",
            sig_name,
        )
        self._running = False
