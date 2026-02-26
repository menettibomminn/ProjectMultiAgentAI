"""Tests for lock_manager: FileLockBackend, RedisLockBackend, LockManager."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from Agents.sheets_agent.lock_manager import (
    FileLockBackend,
    LockBackend,
    LockError,
    LockManager,
    RedisLockBackend,
)


# ---------------------------------------------------------------
# FileLockBackend tests
# ---------------------------------------------------------------


class TestFileLockBackendAcquire:
    """Test file-based lock acquisition."""

    def test_acquire_new_lock(self, tmp_path: Path) -> None:
        backend = FileLockBackend(tmp_path / "locks")
        ok = backend.try_acquire("sheet-1", "agent-A", "task-1", timeout_seconds=60)
        assert ok is True

    def test_acquire_creates_lock_file(self, tmp_path: Path) -> None:
        locks_dir = tmp_path / "locks"
        backend = FileLockBackend(locks_dir)
        backend.try_acquire("sheet-1", "agent-A", "task-1", timeout_seconds=60)
        lock_files = list(locks_dir.glob("*.lock"))
        assert len(lock_files) == 1
        assert "sheet_sheet-1" in lock_files[0].name

    def test_acquire_writes_json_payload(self, tmp_path: Path) -> None:
        locks_dir = tmp_path / "locks"
        backend = FileLockBackend(locks_dir)
        backend.try_acquire("sheet-1", "agent-A", "task-1", timeout_seconds=60)
        lock_file = list(locks_dir.glob("*.lock"))[0]
        data = json.loads(lock_file.read_text(encoding="utf-8"))
        assert data["owner"] == "agent-A"
        assert data["task_id"] == "task-1"
        assert "ts" in data

    def test_cannot_acquire_held_lock(self, tmp_path: Path) -> None:
        backend = FileLockBackend(tmp_path / "locks")
        backend.try_acquire("sheet-1", "agent-A", "task-1", timeout_seconds=60)
        ok = backend.try_acquire("sheet-1", "agent-B", "task-2", timeout_seconds=60)
        assert ok is False

    def test_stale_lock_overridden(self, tmp_path: Path) -> None:
        locks_dir = tmp_path / "locks"
        locks_dir.mkdir(parents=True)
        backend = FileLockBackend(locks_dir)
        # Write a lock with old timestamp
        lock_path = locks_dir / "sheet_sheet-1.lock"
        old_ts = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
        lock_path.write_text(
            json.dumps({"owner": "agent-A", "task_id": "old", "ts": old_ts}),
            encoding="utf-8",
        )
        ok = backend.try_acquire("sheet-1", "agent-B", "task-2", timeout_seconds=120)
        assert ok is True
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["owner"] == "agent-B"

    def test_fresh_lock_not_overridden(self, tmp_path: Path) -> None:
        locks_dir = tmp_path / "locks"
        locks_dir.mkdir(parents=True)
        backend = FileLockBackend(locks_dir)
        # Write a recent lock
        lock_path = locks_dir / "sheet_sheet-1.lock"
        lock_path.write_text(
            json.dumps({
                "owner": "agent-A",
                "task_id": "active",
                "ts": datetime.now(timezone.utc).isoformat(),
            }),
            encoding="utf-8",
        )
        ok = backend.try_acquire("sheet-1", "agent-B", "task-2", timeout_seconds=120)
        assert ok is False


class TestFileLockBackendRelease:
    """Test file-based lock release."""

    def test_release_removes_lock_file(self, tmp_path: Path) -> None:
        locks_dir = tmp_path / "locks"
        backend = FileLockBackend(locks_dir)
        backend.try_acquire("sheet-1", "agent-A", "task-1", timeout_seconds=60)
        backend.release("sheet-1", "agent-A")
        lock_files = list(locks_dir.glob("*.lock"))
        assert len(lock_files) == 0

    def test_release_nonexistent_lock(self, tmp_path: Path) -> None:
        """Releasing a lock that doesn't exist should not raise."""
        backend = FileLockBackend(tmp_path / "locks")
        backend.release("sheet-1", "agent-A")  # should not raise


class TestFileLockBackendReadInfo:
    """Test lock info reading."""

    def test_read_info_returns_payload(self, tmp_path: Path) -> None:
        locks_dir = tmp_path / "locks"
        backend = FileLockBackend(locks_dir)
        backend.try_acquire("sheet-1", "agent-A", "task-1", timeout_seconds=60)
        info = backend.read_info("sheet-1")
        assert info is not None
        assert info["owner"] == "agent-A"
        assert info["task_id"] == "task-1"

    def test_read_info_no_lock(self, tmp_path: Path) -> None:
        backend = FileLockBackend(tmp_path / "locks")
        info = backend.read_info("sheet-1")
        assert info is None

    def test_read_info_corrupt_file(self, tmp_path: Path) -> None:
        locks_dir = tmp_path / "locks"
        locks_dir.mkdir(parents=True)
        lock_path = locks_dir / "sheet_sheet-1.lock"
        lock_path.write_text("NOT JSON", encoding="utf-8")
        backend = FileLockBackend(locks_dir)
        info = backend.read_info("sheet-1")
        assert info is None


class TestFileLockBackendPrefix:
    """Test custom prefix."""

    def test_custom_prefix(self, tmp_path: Path) -> None:
        locks_dir = tmp_path / "locks"
        backend = FileLockBackend(locks_dir, prefix="ctrl_")
        backend.try_acquire("team-1", "controller", "task-1", timeout_seconds=60)
        lock_files = list(locks_dir.glob("*.lock"))
        assert "ctrl_team-1" in lock_files[0].name


# ---------------------------------------------------------------
# RedisLockBackend tests (mocked Redis client)
# ---------------------------------------------------------------


def _make_mock_redis() -> MagicMock:
    """Create a mock Redis client."""
    client = MagicMock()
    client.set.return_value = True
    client.get.return_value = None
    client.script_load.return_value = "fake-sha"
    client.evalsha.return_value = 1
    return client


class TestRedisLockBackendAcquire:
    """Test Redis lock acquisition."""

    def test_acquire_calls_set_nx_ex(self, tmp_path: Path) -> None:
        mock_client = _make_mock_redis()
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = None

        ok = backend.try_acquire("sheet-1", "agent-A", "task-1", timeout_seconds=120)
        assert ok is True
        mock_client.set.assert_called_once()
        call_kwargs = mock_client.set.call_args
        # Verify nx=True, ex=120
        assert call_kwargs.kwargs.get("nx") is True or call_kwargs[1].get("nx") is True
        assert call_kwargs.kwargs.get("ex") == 120 or call_kwargs[1].get("ex") == 120

    def test_acquire_fails_when_key_exists(self) -> None:
        mock_client = _make_mock_redis()
        mock_client.set.return_value = None  # SET NX returns None when key exists
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = None

        ok = backend.try_acquire("sheet-1", "agent-B", "task-2", timeout_seconds=120)
        assert ok is False

    def test_acquire_stores_json_payload(self) -> None:
        mock_client = _make_mock_redis()
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = None

        backend.try_acquire("sheet-1", "agent-A", "task-1", timeout_seconds=60)
        call_args = mock_client.set.call_args
        stored_value = call_args[0][1]
        data = json.loads(stored_value)
        assert data["owner"] == "agent-A"
        assert data["task_id"] == "task-1"
        assert "ts" in data


class TestRedisLockBackendRelease:
    """Test Redis lock release."""

    def test_release_uses_lua_script(self) -> None:
        mock_client = _make_mock_redis()
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = "cached-sha"

        backend.release("sheet-1", "agent-A")
        mock_client.evalsha.assert_called_once_with(
            "cached-sha", 1, "lock:sheet:sheet-1", "agent-A"
        )

    def test_release_loads_script_on_first_call(self) -> None:
        mock_client = _make_mock_redis()
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = None

        backend.release("sheet-1", "agent-A")
        mock_client.script_load.assert_called_once()
        mock_client.evalsha.assert_called_once()


class TestRedisLockBackendReadInfo:
    """Test Redis lock info reading."""

    def test_read_info_returns_payload(self) -> None:
        mock_client = _make_mock_redis()
        mock_client.get.return_value = json.dumps(
            {"owner": "agent-A", "task_id": "task-1", "ts": "2026-01-01T00:00:00+00:00"}
        )
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = None

        info = backend.read_info("sheet-1")
        assert info is not None
        assert info["owner"] == "agent-A"

    def test_read_info_no_key(self) -> None:
        mock_client = _make_mock_redis()
        mock_client.get.return_value = None
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = None

        info = backend.read_info("sheet-1")
        assert info is None


class TestRedisLockBackendConnectionFailure:
    """Test Redis backend behavior when Redis is unreachable."""

    def test_acquire_returns_false_on_connection_error(self) -> None:
        mock_client = _make_mock_redis()
        mock_client.set.side_effect = ConnectionError("Redis unreachable")
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = None

        ok = backend.try_acquire("sheet-1", "agent-A", "task-1", timeout_seconds=60)
        assert ok is False

    def test_release_silently_fails_on_connection_error(self) -> None:
        mock_client = _make_mock_redis()
        mock_client.script_load.side_effect = ConnectionError("Redis unreachable")
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = None

        # Should not raise — TTL will expire the lock
        backend.release("sheet-1", "agent-A")

    def test_read_info_returns_none_on_connection_error(self) -> None:
        mock_client = _make_mock_redis()
        mock_client.get.side_effect = ConnectionError("Redis unreachable")
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = None

        info = backend.read_info("sheet-1")
        assert info is None

    def test_acquire_failure_triggers_lock_error_after_retries(
        self, tmp_path: Path,
    ) -> None:
        """When Redis is down, LockManager retries then raises LockError."""
        mock_client = _make_mock_redis()
        mock_client.set.side_effect = ConnectionError("Redis unreachable")
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = None

        mgr = LockManager(
            locks_dir=tmp_path, owner="agent-A",
            max_retries=1, backoff_base=0.001, backend=backend,
        )
        with pytest.raises(LockError, match="Cannot acquire lock"):
            mgr.acquire("sheet-1", "task-1")


class TestRedisLockBackendKeyFormat:
    """Test Redis key format."""

    def test_key_prefix(self) -> None:
        mock_client = _make_mock_redis()
        with patch("Agents.sheets_agent.lock_manager.RedisLockBackend.__init__", return_value=None):
            backend = RedisLockBackend.__new__(RedisLockBackend)
            backend._client = mock_client
            backend._prefix = "lock:sheet:"
            backend._release_sha = None

        backend.try_acquire("abc/123", "agent-A", "task-1", timeout_seconds=60)
        call_args = mock_client.set.call_args
        redis_key = call_args[0][0]
        assert redis_key == "lock:sheet:abc_123"


# ---------------------------------------------------------------
# LockManager tests (backend-agnostic)
# ---------------------------------------------------------------


class _FakeBackend:
    """Minimal fake backend for testing LockManager logic."""

    def __init__(self) -> None:
        self.locks: dict[str, dict[str, Any]] = {}
        self.acquire_calls: list[tuple[str, str, str, int]] = []
        self.release_calls: list[tuple[str, str]] = []

    def try_acquire(
        self, key: str, owner: str, task_id: str, timeout_seconds: int,
    ) -> bool:
        self.acquire_calls.append((key, owner, task_id, timeout_seconds))
        if key in self.locks:
            return False
        self.locks[key] = {"owner": owner, "task_id": task_id}
        return True

    def release(self, key: str, owner: str) -> None:
        self.release_calls.append((key, owner))
        self.locks.pop(key, None)

    def read_info(self, key: str) -> dict[str, Any] | None:
        return self.locks.get(key)


class TestLockManager:
    """Test LockManager with a fake backend."""

    def test_acquire_and_release(self, tmp_path: Path) -> None:
        fake = _FakeBackend()
        mgr = LockManager(
            locks_dir=tmp_path, owner="agent-A",
            max_retries=0, backend=fake,
        )
        mgr.acquire("sheet-1", "task-1")
        assert mgr.is_held("sheet-1")
        mgr.release("sheet-1")
        assert not mgr.is_held("sheet-1")

    def test_acquire_raises_after_retries(self, tmp_path: Path) -> None:
        fake = _FakeBackend()
        fake.locks["sheet-1"] = {"owner": "agent-X"}  # pre-held
        mgr = LockManager(
            locks_dir=tmp_path, owner="agent-A",
            max_retries=2, backoff_base=0.001, backend=fake,
        )
        with pytest.raises(LockError, match="Cannot acquire lock"):
            mgr.acquire("sheet-1", "task-1")
        # Should have tried 3 times (initial + 2 retries)
        assert len(fake.acquire_calls) == 3

    def test_release_all(self, tmp_path: Path) -> None:
        fake = _FakeBackend()
        mgr = LockManager(
            locks_dir=tmp_path, owner="agent-A",
            max_retries=0, backend=fake,
        )
        mgr.acquire("sheet-1", "task-1")
        mgr.acquire("sheet-2", "task-2")
        assert mgr.is_held("sheet-1")
        assert mgr.is_held("sheet-2")
        mgr.release_all()
        assert not mgr.is_held("sheet-1")
        assert not mgr.is_held("sheet-2")

    def test_release_not_held(self, tmp_path: Path) -> None:
        """Releasing a lock we don't hold should be a no-op."""
        fake = _FakeBackend()
        mgr = LockManager(
            locks_dir=tmp_path, owner="agent-A",
            max_retries=0, backend=fake,
        )
        mgr.release("sheet-1")  # should not raise
        assert len(fake.release_calls) == 0

    def test_default_backend_is_file(self, tmp_path: Path) -> None:
        """Without explicit backend, LockManager creates FileLockBackend."""
        mgr = LockManager(locks_dir=tmp_path / "locks", owner="agent-A")
        assert isinstance(mgr._backend, FileLockBackend)

    def test_passes_owner_to_backend(self, tmp_path: Path) -> None:
        fake = _FakeBackend()
        mgr = LockManager(
            locks_dir=tmp_path, owner="agent-A",
            max_retries=0, backend=fake,
        )
        mgr.acquire("sheet-1", "task-1")
        assert fake.acquire_calls[0][1] == "agent-A"
        mgr.release("sheet-1")
        assert fake.release_calls[0][1] == "agent-A"


class TestLockBackendProtocol:
    """Verify protocol compliance."""

    def test_file_backend_is_lock_backend(self, tmp_path: Path) -> None:
        backend = FileLockBackend(tmp_path)
        assert isinstance(backend, LockBackend)

    def test_fake_backend_is_lock_backend(self) -> None:
        fake = _FakeBackend()
        assert isinstance(fake, LockBackend)
