"""File-based lock manager for Controller inbox processing.

Uses portalocker for cross-platform advisory file locking.
Lock scope: one lock file per team inbox under locks/.

Design decisions (see ARCHITECTURE.md):
- Lock file path: locks/ctrl_{team_id}.lock
- Lock content is JSON: {owner, task_id, ts}
- Stale locks (older than lock_timeout) are overridden.
- Exponential backoff on contention.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import portalocker


class LockError(Exception):
    """Raised when a lock cannot be acquired."""


class LockManager:
    """Manage per-team inbox processing locks."""

    def __init__(
        self,
        locks_dir: Path,
        owner: str,
        timeout_seconds: int = 120,
        max_retries: int = 5,
        backoff_base: float = 2.0,
    ) -> None:
        self._locks_dir = locks_dir
        self._owner = owner
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._held: dict[str, Path] = {}  # resource_id -> lock file path
        self._new_held: dict[str, Path] = {}  # resource-centric locks

    def acquire(self, resource_id: str, task_id: str) -> None:
        """Acquire a lock for *resource_id*.

        Raises LockError after exhausting retries.
        """
        self._locks_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._lock_path(resource_id)

        for attempt in range(self._max_retries + 1):
            if self._try_acquire(lock_path, task_id):
                self._held[resource_id] = lock_path
                return
            if attempt < self._max_retries:
                delay = self._backoff_base * (2 ** attempt)
                time.sleep(delay)

        raise LockError(
            f"Cannot acquire lock for {resource_id} "
            f"after {self._max_retries} retries"
        )

    def release(self, resource_id: str) -> None:
        """Release a previously acquired lock."""
        lock_path = self._held.pop(resource_id, None)
        if lock_path and lock_path.exists():
            lock_path.unlink(missing_ok=True)

    def release_all(self) -> None:
        """Release all locks held by this manager."""
        for rid in list(self._held):
            self.release(rid)

    def is_held(self, resource_id: str) -> bool:
        """Check if we currently hold a lock for *resource_id*."""
        return resource_id in self._held

    # ------------------------------------------------------------------
    # Resource-centric lock API (new)
    # ------------------------------------------------------------------

    def acquire_lock(
        self,
        resource_id: str,
        agent_id: str,
        team_id: str = "",
    ) -> bool:
        """Acquire a resource-centric lock.

        File: locks/{resource_id}.lock (no ctrl_ prefix).
        Returns True if the lock was acquired, False if held by another agent.
        Stale locks (older than timeout_seconds) are overridden.
        """
        self._locks_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._new_lock_path(resource_id)
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "resource_id": resource_id,
            "agent_id": agent_id,
            "team_id": team_id,
            "timestamp": now.isoformat(),
            "status": "locked",
        }

        if not lock_path.exists():
            if self._write_lock(lock_path, payload):
                self._new_held[resource_id] = lock_path
                return True
            return False

        # Read existing lock
        try:
            with portalocker.Lock(
                str(lock_path),
                mode="r",
                timeout=1,
                flags=portalocker.LOCK_SH | portalocker.LOCK_NB,
            ) as fh:
                existing = json.loads(fh.read())
        except (portalocker.LockException, json.JSONDecodeError, OSError):
            if self._write_lock(lock_path, payload):
                self._new_held[resource_id] = lock_path
                return True
            return False

        # Same agent can re-acquire
        if existing.get("agent_id") == agent_id:
            if self._write_lock(lock_path, payload):
                self._new_held[resource_id] = lock_path
                return True
            return False

        # Check staleness
        lock_ts = datetime.fromisoformat(
            existing.get("timestamp", "2000-01-01T00:00:00+00:00")
        )
        age = (now - lock_ts).total_seconds()
        if age > self._timeout:
            if self._write_lock(lock_path, payload):
                self._new_held[resource_id] = lock_path
                return True
            return False

        return False

    def release_lock(self, resource_id: str) -> bool:
        """Release a resource-centric lock. Returns True if released."""
        lock_path = self._new_held.pop(resource_id, None)
        if lock_path is None:
            lock_path = self._new_lock_path(resource_id)
        if lock_path.exists():
            lock_path.unlink(missing_ok=True)
            return True
        return False

    def is_locked(self, resource_id: str) -> bool:
        """Check if a resource-centric lock is currently active.

        Returns True if the lock file exists and is not stale.
        """
        data = self.check_lock(resource_id)
        if data is None:
            return False
        ts_str = data.get("timestamp", "")
        if not ts_str:
            return True
        try:
            lock_ts = datetime.fromisoformat(ts_str)
            age = (datetime.now(timezone.utc) - lock_ts).total_seconds()
            return age <= self._timeout
        except ValueError:
            return True

    def check_lock(self, resource_id: str) -> dict[str, Any] | None:
        """Check the state of a resource-centric lock. Returns lock data or None."""
        lock_path = self._new_lock_path(resource_id)
        if not lock_path.exists():
            return None
        try:
            with portalocker.Lock(
                str(lock_path),
                mode="r",
                timeout=1,
                flags=portalocker.LOCK_SH | portalocker.LOCK_NB,
            ) as fh:
                return json.loads(fh.read())  # type: ignore[no-any-return]
        except (portalocker.LockException, json.JSONDecodeError, OSError):
            return None

    def _new_lock_path(self, resource_id: str) -> Path:
        """Lock file path for resource-centric locks (no ctrl_ prefix)."""
        safe_id = resource_id.replace("/", "_").replace("\\", "_")
        return self._locks_dir / f"{safe_id}.lock"

    def _lock_path(self, resource_id: str) -> Path:
        safe_id = resource_id.replace("/", "_").replace("\\", "_")
        return self._locks_dir / f"ctrl_{safe_id}.lock"

    def _try_acquire(self, lock_path: Path, task_id: str) -> bool:
        """Try once to create or override the lock file."""
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "owner": self._owner,
            "task_id": task_id,
            "ts": now.isoformat(),
        }

        if not lock_path.exists():
            return self._write_lock(lock_path, payload)

        try:
            with portalocker.Lock(
                str(lock_path),
                mode="r",
                timeout=1,
                flags=portalocker.LOCK_SH | portalocker.LOCK_NB,
            ) as fh:
                existing = json.loads(fh.read())
        except (portalocker.LockException, json.JSONDecodeError, OSError):
            return self._write_lock(lock_path, payload)

        lock_ts = datetime.fromisoformat(
            existing.get("ts", "2000-01-01T00:00:00+00:00")
        )
        age = (now - lock_ts).total_seconds()
        if age > self._timeout:
            return self._write_lock(lock_path, payload)

        return False

    @staticmethod
    def _write_lock(lock_path: Path, payload: dict[str, Any]) -> bool:
        """Write the lock file atomically with an exclusive lock."""
        try:
            with portalocker.Lock(
                str(lock_path),
                mode="w",
                timeout=2,
                flags=portalocker.LOCK_EX,
            ) as fh:
                fh.write(json.dumps(payload))
            return True
        except portalocker.LockException:
            return False
