"""Retry and escalation management for failed tasks.

When an agent report has status "error" or "failure", the RetryManager
decides whether to re-emit the task (retry) or escalate to an operator.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Controller.config import ControllerConfig
from Controller.controller_report_generator import generate_directive, write_directive
from Controller.logger import get_logger


@dataclass
class TaskRetryEntry:
    """Tracks retry state for a single failed task."""

    task_id: str
    agent: str
    team: str
    retry_count: int = 0
    max_retries: int = 3
    last_retry_ts: str = ""
    status: str = "pending"  # pending | retrying | exhausted


class RetryManager:
    """Manage retry logic and escalation for failed agent tasks."""

    def __init__(self, config: ControllerConfig) -> None:
        self.config = config
        self.log = get_logger(f"{config.controller_id}.retry")
        self._state: dict[str, TaskRetryEntry] = {}
        self.load_state()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def load_state(self) -> None:
        """Load retry state from disk."""
        state_file = self.config.retry_state_file
        if not state_file.exists():
            self._state = {}
            return

        try:
            raw = json.loads(state_file.read_text(encoding="utf-8"))
            self._state = {}
            for task_id, entry_data in raw.items():
                self._state[task_id] = TaskRetryEntry(**entry_data)
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            self.log.error("Failed to load retry state: %s", exc)
            self._state = {}

    def save_state(self) -> None:
        """Atomically write retry state to disk."""
        state_file = self.config.retry_state_file
        state_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            task_id: asdict(entry) for task_id, entry in self._state.items()
        }

        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(state_file)

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    def should_retry(self, task_id: str, agent: str) -> bool:
        """Check if a task should be retried.

        Returns True if retry_count < max_retries and the exponential
        backoff period has elapsed.
        """
        entry = self._state.get(task_id)
        if entry is None:
            return True  # First failure — can retry

        if entry.retry_count >= entry.max_retries:
            return False

        # Check exponential backoff
        if entry.last_retry_ts:
            try:
                last_ts = datetime.fromisoformat(entry.last_retry_ts)
                elapsed = (
                    datetime.now(timezone.utc) - last_ts
                ).total_seconds()
                backoff = self.config.retry_backoff_base ** entry.retry_count
                if elapsed < backoff:
                    return False
            except ValueError:
                pass  # Invalid timestamp — allow retry

        return True

    def record_failure(
        self, task_id: str, agent: str, team: str
    ) -> TaskRetryEntry:
        """Record a task failure, incrementing the retry counter."""
        now = datetime.now(timezone.utc).isoformat()

        if task_id in self._state:
            entry = self._state[task_id]
            entry.retry_count += 1
            entry.last_retry_ts = now
            if entry.retry_count >= entry.max_retries:
                entry.status = "exhausted"
            else:
                entry.status = "retrying"
        else:
            entry = TaskRetryEntry(
                task_id=task_id,
                agent=agent,
                team=team,
                retry_count=1,
                max_retries=self.config.retry_max_per_task,
                last_retry_ts=now,
                status="retrying",
            )
            self._state[task_id] = entry

        self.save_state()
        return entry

    def record_success(self, task_id: str) -> None:
        """Remove retry tracking for a successfully completed task."""
        if task_id in self._state:
            del self._state[task_id]
            self.save_state()

    def get_entry(self, task_id: str) -> TaskRetryEntry | None:
        """Get the retry entry for a task, if any."""
        return self._state.get(task_id)

    # ------------------------------------------------------------------
    # Directive generation
    # ------------------------------------------------------------------

    def generate_retry_directive(
        self, entry: TaskRetryEntry
    ) -> dict[str, Any]:
        """Generate a retry_task directive for the given entry."""
        return generate_directive(
            directive_id=f"retry-{entry.task_id}-{entry.retry_count}",
            target_agent=entry.agent,
            command="retry_task",
            parameters={
                "original_task_id": entry.task_id,
                "retry_count": entry.retry_count,
                "max_retries": entry.max_retries,
            },
            controller_id=self.config.controller_id,
        )

    def generate_escalation_directive(
        self, entry: TaskRetryEntry, reason: str
    ) -> dict[str, Any]:
        """Generate an escalation directive for an exhausted task."""
        return generate_directive(
            directive_id=f"escalate-{entry.task_id}",
            target_agent="operator",
            command="escalate",
            parameters={
                "original_task_id": entry.task_id,
                "failed_agent": entry.agent,
                "team": entry.team,
                "retry_count": entry.retry_count,
                "reason": reason,
            },
            controller_id=self.config.controller_id,
        )

    def write_retry_directive(
        self, directive: dict[str, Any], entry: TaskRetryEntry
    ) -> Path:
        """Write a retry directive to the agent's outbox."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = (
            self.config.outbox_dir
            / entry.team
            / entry.agent
            / f"{ts}_retry_directive.json"
        )
        write_directive(directive, path)
        return path

    def write_escalation_directive(
        self, directive: dict[str, Any], entry: TaskRetryEntry
    ) -> Path:
        """Write an escalation directive to the escalation outbox."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = (
            self.config.outbox_dir
            / "escalation"
            / f"{ts}_escalation.json"
        )
        write_directive(directive, path)
        return path

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def cleanup_stale_entries(self, max_age_hours: int = 72) -> int:
        """Remove retry entries older than max_age_hours. Returns count removed."""
        now = datetime.now(timezone.utc)
        stale: list[str] = []

        for task_id, entry in self._state.items():
            if entry.last_retry_ts:
                try:
                    ts = datetime.fromisoformat(entry.last_retry_ts)
                    age_hours = (now - ts).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        stale.append(task_id)
                except ValueError:
                    stale.append(task_id)
            else:
                stale.append(task_id)

        for task_id in stale:
            del self._state[task_id]

        if stale:
            self.save_state()
            self.log.info("Cleaned up %d stale retry entries", len(stale))

        return len(stale)
