"""Tests for the new resource-centric lock API in LockManager."""
from __future__ import annotations

import json
from pathlib import Path

from Controller.lock_manager import LockManager


class TestAcquireLock:
    """Test acquire_lock (resource-centric)."""

    def _make_mgr(self, tmp_path: Path, timeout: int = 120) -> LockManager:
        locks_dir = tmp_path / "locks"
        return LockManager(
            locks_dir=locks_dir,
            owner="ctrl-test",
            timeout_seconds=timeout,
        )

    def test_acquire_new_lock(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        assert mgr.acquire_lock("sheet-A", "agent-1") is True

    def test_acquire_creates_file(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        mgr.acquire_lock("sheet-A", "agent-1")
        lock_path = tmp_path / "locks" / "sheet-A.lock"
        assert lock_path.exists()
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["resource_id"] == "sheet-A"
        assert data["agent_id"] == "agent-1"
        assert data["status"] == "locked"

    def test_acquire_with_team(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        mgr.acquire_lock("sheet-A", "agent-1", team_id="sheets-team")
        lock_path = tmp_path / "locks" / "sheet-A.lock"
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["team_id"] == "sheets-team"

    def test_same_agent_can_reacquire(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        assert mgr.acquire_lock("r1", "agent-1") is True
        assert mgr.acquire_lock("r1", "agent-1") is True

    def test_different_agent_blocked(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        assert mgr.acquire_lock("r1", "agent-1") is True
        assert mgr.acquire_lock("r1", "agent-2") is False

    def test_stale_lock_overridden(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path, timeout=1)
        mgr.acquire_lock("r1", "agent-1")
        # Manually set timestamp to the past
        lock_path = tmp_path / "locks" / "r1.lock"
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        data["timestamp"] = "2020-01-01T00:00:00+00:00"
        lock_path.write_text(json.dumps(data), encoding="utf-8")

        assert mgr.acquire_lock("r1", "agent-2") is True

    def test_no_ctrl_prefix(self, tmp_path: Path) -> None:
        """Resource-centric locks should NOT have ctrl_ prefix."""
        mgr = self._make_mgr(tmp_path)
        mgr.acquire_lock("my-resource", "agent-1")
        assert (tmp_path / "locks" / "my-resource.lock").exists()
        assert not (tmp_path / "locks" / "ctrl_my-resource.lock").exists()


class TestReleaseLock:
    """Test release_lock."""

    def _make_mgr(self, tmp_path: Path) -> LockManager:
        return LockManager(
            locks_dir=tmp_path / "locks",
            owner="ctrl-test",
        )

    def test_release_acquired(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        mgr.acquire_lock("r1", "agent-1")
        assert mgr.release_lock("r1") is True
        assert not (tmp_path / "locks" / "r1.lock").exists()

    def test_release_nonexistent(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        assert mgr.release_lock("ghost") is False

    def test_release_allows_reacquire(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        mgr.acquire_lock("r1", "agent-1")
        mgr.release_lock("r1")
        assert mgr.acquire_lock("r1", "agent-2") is True


class TestCheckLock:
    """Test check_lock."""

    def _make_mgr(self, tmp_path: Path) -> LockManager:
        return LockManager(
            locks_dir=tmp_path / "locks",
            owner="ctrl-test",
        )

    def test_check_existing(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        mgr.acquire_lock("r1", "agent-1")
        data = mgr.check_lock("r1")
        assert data is not None
        assert data["agent_id"] == "agent-1"

    def test_check_nonexistent(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        assert mgr.check_lock("ghost") is None

    def test_check_after_release(self, tmp_path: Path) -> None:
        mgr = self._make_mgr(tmp_path)
        mgr.acquire_lock("r1", "agent-1")
        mgr.release_lock("r1")
        assert mgr.check_lock("r1") is None


class TestOldApiUnchanged:
    """Verify old acquire/release/is_held still works."""

    def test_old_api_still_works(self, tmp_path: Path) -> None:
        mgr = LockManager(
            locks_dir=tmp_path / "locks",
            owner="ctrl-test",
            timeout_seconds=120,
        )
        mgr.acquire("team-inbox", "task-001")
        assert mgr.is_held("team-inbox")
        mgr.release("team-inbox")
        assert not mgr.is_held("team-inbox")

    def test_old_and_new_independent(self, tmp_path: Path) -> None:
        """Old ctrl_ locks and new resource locks don't interfere."""
        mgr = LockManager(
            locks_dir=tmp_path / "locks",
            owner="ctrl-test",
        )
        mgr.acquire("resource-X", "task-001")
        mgr.acquire_lock("resource-X", "agent-1")

        # Old lock uses ctrl_ prefix, new doesn't
        assert (tmp_path / "locks" / "ctrl_resource-X.lock").exists()
        assert (tmp_path / "locks" / "resource-X.lock").exists()

        mgr.release("resource-X")
        assert not mgr.is_held("resource-X")
        # New lock still exists
        assert mgr.check_lock("resource-X") is not None
