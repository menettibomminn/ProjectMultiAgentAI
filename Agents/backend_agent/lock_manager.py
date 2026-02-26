"""File-based lock manager for per-resource concurrency control.

Uses portalocker for cross-platform advisory file locking.
Lock scope: one lock file per resource under locks/.
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
    """Manage per-resource file locks."""

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
        self._held: dict[str, Path] = {}

    def acquire(self, resource_id: str, task_id: str) -> None:
        """Acquire a lock for *resource_id*. Raises LockError after retries."""
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
            f"Cannot acquire lock for resource {resource_id} "
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

    def _lock_path(self, resource_id: str) -> Path:
        safe_id = resource_id.replace("/", "_").replace("\\", "_")
        return self._locks_dir / f"backend_{safe_id}.lock"

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
