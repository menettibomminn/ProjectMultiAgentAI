"""Health reporter — periodic health status for the agent loop."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any


class HealthReporter:
    """Track and report agent health during continuous-loop execution.

    Parameters
    ----------
    agent_id:
        Agent identifier included in every report.
    max_consecutive_errors:
        Threshold after which :meth:`is_healthy` returns ``False``.
    """

    def __init__(
        self,
        agent_id: str,
        max_consecutive_errors: int = 5,
    ) -> None:
        self._agent_id = agent_id
        self._max_errors = max_consecutive_errors
        self._start_time = time.monotonic()
        self._tasks_processed: int = 0
        self._tasks_failed: int = 0
        self._consecutive_errors: int = 0
        self._last_task_id: str = ""
        self._last_task_status: str = ""
        self._queue_length: int = 0

    # -- Public API ----------------------------------------------------------

    def record_success(self, task_id: str) -> None:
        """Register a successfully processed task."""
        self._tasks_processed += 1
        self._consecutive_errors = 0
        self._last_task_id = task_id
        self._last_task_status = "success"

    def record_error(self, task_id: str, err: str) -> None:
        """Register a task failure."""
        self._tasks_processed += 1
        self._tasks_failed += 1
        self._consecutive_errors += 1
        self._last_task_id = task_id
        self._last_task_status = f"error: {err}"

    def set_queue_length(self, length: int) -> None:
        """Update the estimated inbox queue length."""
        self._queue_length = length

    def is_healthy(self) -> bool:
        """Return ``False`` when consecutive errors exceed the threshold."""
        return self._consecutive_errors < self._max_errors

    def report(self) -> dict[str, Any]:
        """Return a snapshot of the current health state."""
        uptime = time.monotonic() - self._start_time
        status = "healthy" if self.is_healthy() else "degraded"
        return {
            "agent_id": self._agent_id,
            "status": status,
            "uptime_seconds": round(uptime, 1),
            "tasks_processed": self._tasks_processed,
            "tasks_failed": self._tasks_failed,
            "consecutive_errors": self._consecutive_errors,
            "last_task_id": self._last_task_id,
            "last_task_status": self._last_task_status,
            "last_health_check": datetime.now(timezone.utc).isoformat(),
            "queue_length_estimate": self._queue_length,
        }
