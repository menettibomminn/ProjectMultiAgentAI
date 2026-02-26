"""Task lifecycle manager for the Controller.

Creates, tracks, and transitions tasks through a well-defined state machine.
All state is persisted to Controller/state/tasks.json via the state_store
module.

Task states:
    PENDING -> ASSIGNED -> RUNNING -> COMPLETED
                                   -> FAILED (-> retry -> PENDING)
                        -> WAITING_APPROVAL -> APPROVED -> RUNNING
                                            -> REJECTED -> FAILED
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Controller.logger import get_logger
from Controller.schema_validator import SchemaValidationError, validate_task
from Controller.state_store import load_json, save_json

# ---------------------------------------------------------------------------
# Valid states and transitions
# ---------------------------------------------------------------------------

VALID_STATUSES: frozenset[str] = frozenset({
    "PENDING",
    "ASSIGNED",
    "RUNNING",
    "WAITING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "FAILED",
    "COMPLETED",
})

_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"ASSIGNED", "RUNNING", "FAILED"}),
    "ASSIGNED": frozenset({"RUNNING", "FAILED"}),
    "RUNNING": frozenset({"COMPLETED", "FAILED", "WAITING_APPROVAL"}),
    "WAITING_APPROVAL": frozenset({"APPROVED", "REJECTED"}),
    "APPROVED": frozenset({"RUNNING", "COMPLETED"}),
    "REJECTED": frozenset({"FAILED", "PENDING"}),
    "FAILED": frozenset({"PENDING"}),
    "COMPLETED": frozenset(),
}

MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TaskManagerError(Exception):
    """Base error for task management operations."""


class TaskNotFoundError(TaskManagerError):
    """Raised when a task_id does not exist."""


class InvalidTransitionError(TaskManagerError):
    """Raised on an invalid state transition."""


class MaxRetriesExceededError(TaskManagerError):
    """Raised when retry limit is reached."""


# ---------------------------------------------------------------------------
# TaskManager
# ---------------------------------------------------------------------------


class TaskManager:
    """Deterministic task lifecycle manager with JSON persistence."""

    def __init__(self, tasks_file: Path) -> None:
        self._tasks_file = tasks_file
        self._log = get_logger("task_manager")
        self._tasks: dict[str, dict[str, Any]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_task(
        self,
        task_type: str,
        payload: dict[str, Any],
    ) -> str:
        """Create a new task and return its UUID.

        Args:
            task_type: Descriptive type (e.g. "process_inbox", "emit_directive").
            payload: Arbitrary data attached to the task.

        Returns:
            The newly generated task_id (UUID4 hex string).
        """
        now = datetime.now(timezone.utc).isoformat()
        task_id = uuid.uuid4().hex

        task: dict[str, Any] = {
            "task_id": task_id,
            "task_type": task_type,
            "status": "PENDING",
            "created_at": now,
            "updated_at": now,
            "payload": payload,
            "retries": 0,
        }

        validate_task(task)
        self._tasks[task_id] = task
        self._persist()
        self._log.info(
            "Task created: %s (type=%s)", task_id, task_type
        )
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Return the task dict for *task_id*, or None if not found."""
        return self._tasks.get(task_id)

    def update_task_status(self, task_id: str, status: str) -> None:
        """Transition *task_id* to *status*.

        Raises:
            TaskNotFoundError: If the task does not exist.
            InvalidTransitionError: If the transition is not allowed.
        """
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found")

        current = task["status"]
        if status not in VALID_STATUSES:
            raise InvalidTransitionError(
                f"Invalid status '{status}'. Valid: {sorted(VALID_STATUSES)}"
            )

        allowed = _VALID_TRANSITIONS.get(current, frozenset())
        if status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition {task_id} from {current} to {status}. "
                f"Allowed: {sorted(allowed)}"
            )

        task["status"] = status
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._persist()
        self._log.info(
            "Task %s: %s -> %s", task_id, current, status
        )

    def list_tasks(self) -> list[dict[str, Any]]:
        """Return all tasks sorted by creation time (newest first)."""
        return sorted(
            self._tasks.values(),
            key=lambda t: t["created_at"],
            reverse=True,
        )

    def retry_task(self, task_id: str) -> None:
        """Re-queue a FAILED task for retry.

        Increments the retry counter and transitions to PENDING.

        Raises:
            TaskNotFoundError: If the task does not exist.
            InvalidTransitionError: If the task is not in FAILED state.
            MaxRetriesExceededError: If retries >= MAX_RETRIES.
        """
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found")

        if task["status"] != "FAILED":
            raise InvalidTransitionError(
                f"Can only retry FAILED tasks, got {task['status']}"
            )

        if task["retries"] >= MAX_RETRIES:
            raise MaxRetriesExceededError(
                f"Task {task_id} has reached max retries ({MAX_RETRIES})"
            )

        task["retries"] += 1
        task["status"] = "PENDING"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._persist()
        self._log.info(
            "Task %s retried (attempt %d/%d)",
            task_id, task["retries"], MAX_RETRIES,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load tasks from disk."""
        raw = load_json(self._tasks_file, default={})
        if not isinstance(raw, dict):
            self._log.warning("Invalid tasks file format, starting fresh")
            self._tasks = {}
            return

        self._tasks = {}
        for task_id, task_data in raw.items():
            if not isinstance(task_data, dict):
                continue
            try:
                validate_task(task_data)
                self._tasks[task_id] = task_data
            except SchemaValidationError as exc:
                self._log.warning(
                    "Skipping invalid task %s: %s", task_id, exc
                )

    def _persist(self) -> None:
        """Atomically write all tasks to disk."""
        save_json(self._tasks_file, self._tasks)
