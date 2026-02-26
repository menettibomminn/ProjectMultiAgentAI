"""Tests for Controller.retry_manager."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pytest

from Controller.config import ControllerConfig
from Controller.retry_manager import RetryManager, TaskRetryEntry


@pytest.fixture
def retry_config(tmp_path: Path) -> ControllerConfig:
    """Config with state dir in tmp_path."""
    (tmp_path / "Controller" / "inbox").mkdir(parents=True)
    (tmp_path / "Controller" / "outbox").mkdir(parents=True)
    (tmp_path / "audit" / "controller" / "test-ctrl").mkdir(parents=True)
    (tmp_path / "locks").mkdir(parents=True)
    (tmp_path / "Orchestrator").mkdir(parents=True)
    state_dir = tmp_path / "Controller" / "state"
    state_dir.mkdir(parents=True)
    return ControllerConfig(
        controller_id="test-ctrl",
        project_root=tmp_path,
        retry_max_per_task=3,
        retry_backoff_base=2.0,
        agent_health_paths={},
    )


class TestLoadSaveState:
    """Test load/save round-trip for retry state."""

    def test_save_and_load_round_trip(self, retry_config: ControllerConfig) -> None:
        mgr = RetryManager(retry_config)
        mgr.record_failure("task-1", "sheets-agent", "sheets-team")
        mgr.record_failure("task-2", "auth-agent", "auth-team")

        # Create a new manager to test loading from disk
        mgr2 = RetryManager(retry_config)
        assert "task-1" in mgr2._state
        assert "task-2" in mgr2._state
        assert mgr2._state["task-1"].retry_count == 1
        assert mgr2._state["task-2"].agent == "auth-agent"

    def test_load_empty_state(self, tmp_path: Path) -> None:
        """Fresh state dir with no retry_state.json loads empty."""
        (tmp_path / "Controller" / "inbox").mkdir(parents=True)
        (tmp_path / "Controller" / "outbox").mkdir(parents=True)
        (tmp_path / "Controller" / "state").mkdir(parents=True)
        (tmp_path / "audit" / "controller" / "test-ctrl").mkdir(parents=True)
        (tmp_path / "locks").mkdir(parents=True)
        (tmp_path / "Orchestrator").mkdir(parents=True)
        config = ControllerConfig(
            controller_id="test-ctrl",
            project_root=tmp_path,
            agent_health_paths={},
        )
        mgr = RetryManager(config)
        assert len(mgr._state) == 0

    def test_load_corrupted_state(self, retry_config: ControllerConfig) -> None:
        """Corrupted state file is handled gracefully."""
        retry_config.retry_state_file.parent.mkdir(parents=True, exist_ok=True)
        retry_config.retry_state_file.write_text(
            "not valid json!!!", encoding="utf-8"
        )
        mgr = RetryManager(retry_config)
        assert len(mgr._state) == 0


class TestShouldRetry:
    """Test should_retry logic with backoff."""

    def test_first_failure_allows_retry(self, retry_config: ControllerConfig) -> None:
        mgr = RetryManager(retry_config)
        assert mgr.should_retry("new-task", "agent") is True

    def test_exhausted_retries_blocks(self, retry_config: ControllerConfig) -> None:
        mgr = RetryManager(retry_config)
        for _ in range(3):
            mgr.record_failure("task-x", "agent", "team")
        assert mgr.should_retry("task-x", "agent") is False

    def test_backoff_blocks_immediate_retry(
        self, retry_config: ControllerConfig
    ) -> None:
        mgr = RetryManager(retry_config)
        mgr.record_failure("task-y", "agent", "team")
        # Immediately after failure, backoff should block (2^1 = 2 seconds)
        assert mgr.should_retry("task-y", "agent") is False

    def test_backoff_allows_after_wait(
        self, retry_config: ControllerConfig
    ) -> None:
        """After sufficient time, retry is allowed."""
        mgr = RetryManager(retry_config)
        # Manually create an entry with an old timestamp
        past = datetime.now(timezone.utc) - timedelta(seconds=100)
        entry = TaskRetryEntry(
            task_id="task-z",
            agent="agent",
            team="team",
            retry_count=1,
            max_retries=3,
            last_retry_ts=past.isoformat(),
            status="retrying",
        )
        mgr._state["task-z"] = entry
        assert mgr.should_retry("task-z", "agent") is True


class TestRecordFailureSuccess:
    """Test record_failure and record_success."""

    def test_record_failure_increments(self, retry_config: ControllerConfig) -> None:
        mgr = RetryManager(retry_config)
        e1 = mgr.record_failure("t1", "a1", "team1")
        assert e1.retry_count == 1
        assert e1.status == "retrying"

        e2 = mgr.record_failure("t1", "a1", "team1")
        assert e2.retry_count == 2
        assert e2.status == "retrying"

        e3 = mgr.record_failure("t1", "a1", "team1")
        assert e3.retry_count == 3
        assert e3.status == "exhausted"

    def test_record_success_clears(self, retry_config: ControllerConfig) -> None:
        mgr = RetryManager(retry_config)
        mgr.record_failure("t1", "a1", "team1")
        assert "t1" in mgr._state
        mgr.record_success("t1")
        assert "t1" not in mgr._state

    def test_record_success_noop_if_missing(
        self, retry_config: ControllerConfig
    ) -> None:
        mgr = RetryManager(retry_config)
        mgr.record_success("nonexistent")  # Should not raise


class TestDirectiveGeneration:
    """Test retry and escalation directive generation."""

    def test_generate_retry_directive(self, retry_config: ControllerConfig) -> None:
        mgr = RetryManager(retry_config)
        entry = TaskRetryEntry(
            task_id="t-001",
            agent="sheets-agent",
            team="sheets-team",
            retry_count=1,
            max_retries=3,
        )
        d = mgr.generate_retry_directive(entry)
        assert d["command"] == "retry_task"
        assert d["target_agent"] == "sheets-agent"
        assert d["parameters"]["original_task_id"] == "t-001"
        assert "signature" in d

    def test_generate_escalation_directive(
        self, retry_config: ControllerConfig
    ) -> None:
        mgr = RetryManager(retry_config)
        entry = TaskRetryEntry(
            task_id="t-002",
            agent="backend-agent",
            team="backend-team",
            retry_count=3,
            max_retries=3,
            status="exhausted",
        )
        d = mgr.generate_escalation_directive(entry, "Max retries exhausted")
        assert d["command"] == "escalate"
        assert d["target_agent"] == "operator"
        assert d["parameters"]["reason"] == "Max retries exhausted"

    def test_write_retry_directive(self, retry_config: ControllerConfig) -> None:
        mgr = RetryManager(retry_config)
        entry = TaskRetryEntry(
            task_id="t-003",
            agent="agent-x",
            team="team-y",
            retry_count=1,
        )
        d = mgr.generate_retry_directive(entry)
        path = mgr.write_retry_directive(d, entry)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["command"] == "retry_task"

    def test_write_escalation_directive(
        self, retry_config: ControllerConfig
    ) -> None:
        mgr = RetryManager(retry_config)
        entry = TaskRetryEntry(
            task_id="t-004",
            agent="agent-z",
            team="system",
        )
        d = mgr.generate_escalation_directive(entry, "Agent DOWN")
        path = mgr.write_escalation_directive(d, entry)
        assert path.exists()
        assert "escalation" in str(path)


class TestCleanupStaleEntries:
    """Test cleanup_stale_entries."""

    def test_cleanup_removes_old(self, retry_config: ControllerConfig) -> None:
        mgr = RetryManager(retry_config)
        old_ts = (
            datetime.now(timezone.utc) - timedelta(hours=100)
        ).isoformat()
        mgr._state["old-task"] = TaskRetryEntry(
            task_id="old-task",
            agent="a",
            team="t",
            retry_count=2,
            last_retry_ts=old_ts,
        )
        mgr._state["new-task"] = TaskRetryEntry(
            task_id="new-task",
            agent="b",
            team="t",
            retry_count=1,
            last_retry_ts=datetime.now(timezone.utc).isoformat(),
        )
        removed = mgr.cleanup_stale_entries(max_age_hours=72)
        assert removed == 1
        assert "old-task" not in mgr._state
        assert "new-task" in mgr._state

    def test_cleanup_noop_when_fresh(self, retry_config: ControllerConfig) -> None:
        mgr = RetryManager(retry_config)
        mgr.record_failure("fresh", "a", "t")
        removed = mgr.cleanup_stale_entries(max_age_hours=72)
        assert removed == 0
