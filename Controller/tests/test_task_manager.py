"""Tests for Controller.task_manager."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from Controller.task_manager import (
    InvalidTransitionError,
    MaxRetriesExceededError,
    TaskManager,
    TaskNotFoundError,
)


@pytest.fixture
def tasks_file(tmp_path: Path) -> Path:
    return tmp_path / "state" / "tasks.json"


@pytest.fixture
def mgr(tasks_file: Path) -> TaskManager:
    return TaskManager(tasks_file)


class TestCreateTask:
    def test_returns_uuid(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {"key": "value"})
        assert len(tid) == 32  # UUID hex
        assert tid.isalnum()

    def test_task_is_pending(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        task = mgr.get_task(tid)
        assert task is not None
        assert task["status"] == "PENDING"

    def test_task_has_timestamps(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        task = mgr.get_task(tid)
        assert task is not None
        assert task["created_at"]
        assert task["updated_at"]

    def test_task_has_zero_retries(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        task = mgr.get_task(tid)
        assert task is not None
        assert task["retries"] == 0

    def test_payload_persisted(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {"x": 42})
        task = mgr.get_task(tid)
        assert task is not None
        assert task["payload"] == {"x": 42}

    def test_persists_to_disk(self, tasks_file: Path) -> None:
        mgr = TaskManager(tasks_file)
        tid = mgr.create_task("test", {})
        data = json.loads(tasks_file.read_text(encoding="utf-8"))
        assert tid in data


class TestGetTask:
    def test_existing_task(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        assert mgr.get_task(tid) is not None

    def test_missing_task(self, mgr: TaskManager) -> None:
        assert mgr.get_task("nonexistent") is None


class TestUpdateTaskStatus:
    def test_pending_to_assigned(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        mgr.update_task_status(tid, "ASSIGNED")
        task = mgr.get_task(tid)
        assert task is not None
        assert task["status"] == "ASSIGNED"

    def test_pending_to_running(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        mgr.update_task_status(tid, "RUNNING")
        task = mgr.get_task(tid)
        assert task is not None
        assert task["status"] == "RUNNING"

    def test_running_to_completed(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        mgr.update_task_status(tid, "RUNNING")
        mgr.update_task_status(tid, "COMPLETED")
        task = mgr.get_task(tid)
        assert task is not None
        assert task["status"] == "COMPLETED"

    def test_running_to_waiting_approval(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        mgr.update_task_status(tid, "RUNNING")
        mgr.update_task_status(tid, "WAITING_APPROVAL")
        task = mgr.get_task(tid)
        assert task is not None
        assert task["status"] == "WAITING_APPROVAL"

    def test_waiting_to_approved(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        mgr.update_task_status(tid, "RUNNING")
        mgr.update_task_status(tid, "WAITING_APPROVAL")
        mgr.update_task_status(tid, "APPROVED")
        task = mgr.get_task(tid)
        assert task is not None
        assert task["status"] == "APPROVED"

    def test_waiting_to_rejected(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        mgr.update_task_status(tid, "RUNNING")
        mgr.update_task_status(tid, "WAITING_APPROVAL")
        mgr.update_task_status(tid, "REJECTED")
        task = mgr.get_task(tid)
        assert task is not None
        assert task["status"] == "REJECTED"

    def test_invalid_transition_raises(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        with pytest.raises(InvalidTransitionError):
            mgr.update_task_status(tid, "COMPLETED")  # PENDING -> COMPLETED not allowed

    def test_completed_is_terminal(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        mgr.update_task_status(tid, "RUNNING")
        mgr.update_task_status(tid, "COMPLETED")
        with pytest.raises(InvalidTransitionError):
            mgr.update_task_status(tid, "PENDING")

    def test_invalid_status_value(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        with pytest.raises(InvalidTransitionError):
            mgr.update_task_status(tid, "NONEXISTENT")

    def test_not_found_raises(self, mgr: TaskManager) -> None:
        with pytest.raises(TaskNotFoundError):
            mgr.update_task_status("ghost", "RUNNING")

    def test_updates_timestamp(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        task = mgr.get_task(tid)
        assert task is not None
        old_ts = task["updated_at"]
        mgr.update_task_status(tid, "RUNNING")
        task = mgr.get_task(tid)
        assert task is not None
        assert task["updated_at"] >= old_ts


class TestListTasks:
    def test_empty(self, mgr: TaskManager) -> None:
        assert mgr.list_tasks() == []

    def test_multiple_tasks(self, mgr: TaskManager) -> None:
        mgr.create_task("a", {})
        mgr.create_task("b", {})
        mgr.create_task("c", {})
        assert len(mgr.list_tasks()) == 3

    def test_sorted_newest_first(self, mgr: TaskManager) -> None:
        t1 = mgr.create_task("first", {})
        t2 = mgr.create_task("second", {})
        tasks = mgr.list_tasks()
        assert tasks[0]["task_id"] == t2
        assert tasks[1]["task_id"] == t1


class TestRetryTask:
    def test_retry_failed_task(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        mgr.update_task_status(tid, "RUNNING")
        mgr.update_task_status(tid, "FAILED")
        mgr.retry_task(tid)
        task = mgr.get_task(tid)
        assert task is not None
        assert task["status"] == "PENDING"
        assert task["retries"] == 1

    def test_retry_increments_counter(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        for _ in range(3):
            mgr.update_task_status(tid, "RUNNING")
            mgr.update_task_status(tid, "FAILED")
            mgr.retry_task(tid)
        task = mgr.get_task(tid)
        assert task is not None
        assert task["retries"] == 3

    def test_max_retries_exceeded(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        for _ in range(3):
            mgr.update_task_status(tid, "RUNNING")
            mgr.update_task_status(tid, "FAILED")
            mgr.retry_task(tid)
        mgr.update_task_status(tid, "RUNNING")
        mgr.update_task_status(tid, "FAILED")
        with pytest.raises(MaxRetriesExceededError):
            mgr.retry_task(tid)

    def test_retry_non_failed_raises(self, mgr: TaskManager) -> None:
        tid = mgr.create_task("test", {})
        with pytest.raises(InvalidTransitionError):
            mgr.retry_task(tid)

    def test_retry_not_found(self, mgr: TaskManager) -> None:
        with pytest.raises(TaskNotFoundError):
            mgr.retry_task("ghost")


class TestPersistence:
    def test_round_trip(self, tasks_file: Path) -> None:
        mgr1 = TaskManager(tasks_file)
        tid = mgr1.create_task("persist", {"data": True})
        mgr1.update_task_status(tid, "RUNNING")

        mgr2 = TaskManager(tasks_file)
        task = mgr2.get_task(tid)
        assert task is not None
        assert task["status"] == "RUNNING"
        assert task["payload"] == {"data": True}

    def test_corrupt_file_starts_fresh(self, tasks_file: Path) -> None:
        tasks_file.parent.mkdir(parents=True, exist_ok=True)
        tasks_file.write_text("not json", encoding="utf-8")
        mgr = TaskManager(tasks_file)
        assert mgr.list_tasks() == []
