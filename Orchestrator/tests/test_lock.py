"""Tests for StateLock."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from Orchestrator.exceptions import StateLockError
from Orchestrator.state_lock import StateLock


class TestStateLockBasic:
    def test_acquire_and_release(self, tmp_path: Path) -> None:
        lock = StateLock(tmp_path / ".state.lock", timeout=5.0)
        lock.acquire_lock()
        assert lock.is_acquired
        lock.release_lock()
        assert not lock.is_acquired

    def test_context_manager(self, tmp_path: Path) -> None:
        lock_path = tmp_path / ".state.lock"
        with StateLock(lock_path, timeout=5.0) as lock:
            assert lock.is_acquired
        assert not lock.is_acquired

    def test_double_acquire_idempotent(self, tmp_path: Path) -> None:
        lock = StateLock(tmp_path / ".state.lock", timeout=5.0)
        lock.acquire_lock()
        lock.acquire_lock()  # Should not raise.
        assert lock.is_acquired
        lock.release_lock()
        assert not lock.is_acquired

    def test_release_when_not_held(self, tmp_path: Path) -> None:
        lock = StateLock(tmp_path / ".state.lock", timeout=5.0)
        lock.release_lock()  # Should not raise.
        assert not lock.is_acquired

    def test_lock_creates_parent_dirs(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "deep" / "nested" / ".state.lock"
        lock = StateLock(lock_path, timeout=5.0)
        lock.acquire_lock()
        assert lock.is_acquired
        lock.release_lock()

    def test_lock_cleans_up_file(self, tmp_path: Path) -> None:
        lock_path = tmp_path / ".state.lock"
        lock = StateLock(lock_path, timeout=5.0)
        lock.acquire_lock()
        lock.release_lock()
        # Lock file should be deleted after release.
        assert not lock_path.exists()


class TestStateLockConcurrency:
    def test_threads_serialize(self, tmp_path: Path) -> None:
        """Multiple threads contending for the same lock are serialized."""
        lock_path = tmp_path / ".state.lock"
        counter = [0]

        def worker() -> None:
            lock = StateLock(lock_path, timeout=15.0)
            lock.acquire_lock()
            try:
                val = counter[0]
                time.sleep(0.01)
                counter[0] = val + 1
            finally:
                lock.release_lock()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # Without lock serialization, counter would be < 5.
        assert counter[0] == 5

    def test_context_manager_releases_on_exception(
        self, tmp_path: Path
    ) -> None:
        lock_path = tmp_path / ".state.lock"
        with pytest.raises(RuntimeError, match="boom"):
            with StateLock(lock_path, timeout=5.0) as lock:
                assert lock.is_acquired
                raise RuntimeError("boom")

        # Lock must be released even after exception.
        lock2 = StateLock(lock_path, timeout=2.0)
        lock2.acquire_lock()
        assert lock2.is_acquired
        lock2.release_lock()
