"""Pluggable lock manager for per-spreadsheet concurrency control.

Supports two storage backends:
- **FileLockBackend** (default) — portalocker-based advisory file locking.
- **RedisLockBackend** — Redis SET NX EX with Lua-script safe release.

Lock scope: one lock per spreadsheet_id.

Design decisions (see ARCHITECTURE.md):
- File backend path: locks/sheet_{spreadsheet_id}.lock
- Redis backend key: lock:sheet:{spreadsheet_id}
- Lock content is JSON: {owner, task_id, ts}
- Stale locks: file backend checks ts + timeout; Redis uses TTL auto-expiry.
- Exponential backoff on contention.
- Backend is selectable via config (``lock_backend = "file" | "redis"``).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import portalocker


class LockError(Exception):
    """Raised when a lock cannot be acquired."""


# ------------------------------------------------------------------
# Backend Protocol
# ------------------------------------------------------------------

@runtime_checkable
class LockBackend(Protocol):
    """Protocol for pluggable lock storage backends."""

    def try_acquire(
        self, key: str, owner: str, task_id: str, timeout_seconds: int,
    ) -> bool:
        """Attempt to acquire lock for *key*. Returns True on success."""
        ...

    def release(self, key: str, owner: str) -> None:
        """Release lock for *key* if held by *owner*."""
        ...

    def read_info(self, key: str) -> dict[str, Any] | None:
        """Read current lock holder info. Returns None if not held."""
        ...


# ------------------------------------------------------------------
# File Backend (default)
# ------------------------------------------------------------------

class FileLockBackend:
    """File-based lock backend using portalocker.

    Lock file path: ``{locks_dir}/sheet_{safe_key}.lock``
    Lock content: JSON ``{owner, task_id, ts}``.
    Stale locks (older than *timeout_seconds*) are overridden.
    """

    def __init__(self, locks_dir: Path, prefix: str = "sheet_") -> None:
        self._locks_dir = locks_dir
        self._prefix = prefix

    def try_acquire(
        self, key: str, owner: str, task_id: str, timeout_seconds: int,
    ) -> bool:
        self._locks_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._lock_path(key)
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "owner": owner,
            "task_id": task_id,
            "ts": now.isoformat(),
        }

        if not lock_path.exists():
            return self._write_lock(lock_path, payload)

        # Lock file exists — check if stale
        try:
            with portalocker.Lock(
                str(lock_path),
                mode="r",
                timeout=1,
                flags=portalocker.LOCK_SH | portalocker.LOCK_NB,
            ) as fh:
                existing = json.loads(fh.read())
        except (portalocker.LockException, json.JSONDecodeError, OSError):
            # Cannot read — treat as stale
            return self._write_lock(lock_path, payload)

        lock_ts = datetime.fromisoformat(
            existing.get("ts", "2000-01-01T00:00:00+00:00")
        )
        age = (now - lock_ts).total_seconds()
        if age > timeout_seconds:
            return self._write_lock(lock_path, payload)

        # Lock is fresh and held by someone else
        return False

    def release(self, key: str, owner: str) -> None:
        lock_path = self._lock_path(key)
        if lock_path.exists():
            lock_path.unlink(missing_ok=True)

    def read_info(self, key: str) -> dict[str, Any] | None:
        lock_path = self._lock_path(key)
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

    # -- internals --

    def _lock_path(self, key: str) -> Path:
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self._locks_dir / f"{self._prefix}{safe_key}.lock"

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


# ------------------------------------------------------------------
# Redis Backend (optional)
# ------------------------------------------------------------------

class RedisLockBackend:
    """Redis-based distributed lock backend.

    Uses ``SET key value NX EX`` for atomic lock acquisition with auto-expiry.
    Uses a Lua script for safe owner-checked release (Redlock single-instance).

    Redis key: ``{prefix}{safe_key}``
    Redis value: JSON ``{owner, task_id, ts}``

    Requires: ``pip install redis>=5.0``
    """

    # Lua: atomically release only if the stored owner matches.
    _RELEASE_LUA = """\
local val = redis.call('get', KEYS[1])
if val then
    local data = cjson.decode(val)
    if data.owner == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
end
return 0
"""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        prefix: str = "lock:sheet:",
    ) -> None:
        try:
            import redis as redis_lib
        except ImportError as exc:
            raise ImportError(
                "RedisLockBackend requires the 'redis' package. "
                "Install with: pip install 'redis>=5.0'"
            ) from exc
        self._client: Any = redis_lib.Redis.from_url(
            redis_url, decode_responses=True,
        )
        self._prefix = prefix
        self._release_sha: str | None = None

    def try_acquire(
        self, key: str, owner: str, task_id: str, timeout_seconds: int,
    ) -> bool:
        redis_key = self._redis_key(key)
        now = datetime.now(timezone.utc)
        payload = json.dumps(
            {"owner": owner, "task_id": task_id, "ts": now.isoformat()},
            sort_keys=True,
        )
        try:
            result = self._client.set(
                redis_key, payload, nx=True, ex=max(timeout_seconds, 1),
            )
            return bool(result)
        except Exception:
            # Connection error, timeout, etc. — treat as acquisition failure
            # so LockManager retries with backoff instead of crashing.
            return False

    def release(self, key: str, owner: str) -> None:
        redis_key = self._redis_key(key)
        try:
            if self._release_sha is None:
                self._release_sha = self._client.script_load(
                    self._RELEASE_LUA,
                )
            self._client.evalsha(self._release_sha, 1, redis_key, owner)
        except Exception:
            # Fallback: script cache may be flushed, or connection lost.
            # Re-load script and retry once; silently ignore if still failing
            # (lock will auto-expire via TTL).
            try:
                self._release_sha = self._client.script_load(
                    self._RELEASE_LUA,
                )
                self._client.evalsha(
                    self._release_sha, 1, redis_key, owner,
                )
            except Exception:
                pass  # TTL will expire the lock

    def read_info(self, key: str) -> dict[str, Any] | None:
        redis_key = self._redis_key(key)
        try:
            value = self._client.get(redis_key)
        except Exception:
            return None
        if value is None:
            return None
        try:
            return json.loads(value)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return None

    # -- internals --

    def _redis_key(self, key: str) -> str:
        safe_key = key.replace("/", "_").replace("\\", "_")
        return f"{self._prefix}{safe_key}"


# ------------------------------------------------------------------
# Lock Manager (backend-agnostic)
# ------------------------------------------------------------------

class LockManager:
    """Manage per-spreadsheet locks with pluggable storage backend.

    Default backend: :class:`FileLockBackend` (portalocker).
    Optional: :class:`RedisLockBackend` for distributed locking.
    """

    def __init__(
        self,
        locks_dir: Path,
        owner: str,
        timeout_seconds: int = 120,
        max_retries: int = 5,
        backoff_base: float = 2.0,
        backend: LockBackend | None = None,
    ) -> None:
        self._owner = owner
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backend: LockBackend = backend or FileLockBackend(locks_dir)
        self._held: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(self, spreadsheet_id: str, task_id: str) -> None:
        """Acquire a lock for *spreadsheet_id*.

        Raises LockError after exhausting retries.
        """
        for attempt in range(self._max_retries + 1):
            if self._backend.try_acquire(
                spreadsheet_id, self._owner, task_id, self._timeout,
            ):
                self._held.add(spreadsheet_id)
                return
            if attempt < self._max_retries:
                delay = self._backoff_base * (2 ** attempt)
                time.sleep(delay)

        raise LockError(
            f"Cannot acquire lock for spreadsheet {spreadsheet_id} "
            f"after {self._max_retries} retries"
        )

    def release(self, spreadsheet_id: str) -> None:
        """Release a previously acquired lock."""
        if spreadsheet_id in self._held:
            self._backend.release(spreadsheet_id, self._owner)
            self._held.discard(spreadsheet_id)

    def release_all(self) -> None:
        """Release all locks held by this manager."""
        for sid in list(self._held):
            self.release(sid)

    def is_held(self, spreadsheet_id: str) -> bool:
        """Check if we currently hold a lock for *spreadsheet_id*."""
        return spreadsheet_id in self._held
