"""Shared fixtures for backend_agent tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from Agents.backend_agent.config import BackendAgentConfig

SAMPLE_TASK: dict[str, Any] = {
    "task_id": "backend-042",
    "user_id": "emp_042",
    "team_id": "backend-team",
    "request": {
        "operation": "process_sheet_request",
        "sheet_id": "sheet_abc123",
        "changes": [
            {"cell": "B5", "old_value": "100", "new_value": "150"},
        ],
    },
    "metadata": {
        "source": "web-ui",
        "priority": "normal",
        "timestamp": "2026-02-23T10:00:00Z",
    },
}


@pytest.fixture()
def sample_task() -> dict[str, Any]:
    """Return a deep copy of the sample task."""
    return copy.deepcopy(SAMPLE_TASK)


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project structure with inbox/audit/locks dirs."""
    inbox = (
        tmp_path / "Controller" / "inbox"
        / "backend-team" / "backend-agent"
    )
    inbox.mkdir(parents=True)
    (tmp_path / "ops" / "audit" / "backend-agent").mkdir(parents=True)
    (tmp_path / "locks").mkdir(parents=True)
    # Create a minimal HEALTH.md
    health = tmp_path / "HEALTH.md"
    health.write_text("# Backend Agent — HEALTH\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def test_config(tmp_project: Path) -> BackendAgentConfig:
    """Return a config pointing to the temporary project."""
    return BackendAgentConfig(
        agent_id="backend-test-01",
        team_id="backend-team",
        project_root=tmp_project,
        lock_timeout_seconds=5,
        lock_max_retries=1,
        lock_backoff_base=0.01,
        task_timeout_seconds=10,
        health_file_override=tmp_project / "HEALTH.md",
    )


@pytest.fixture()
def task_file(
    tmp_project: Path, sample_task: dict[str, Any]
) -> Path:
    """Write a sample task to the inbox and return its path."""
    inbox = (
        tmp_project / "Controller" / "inbox"
        / "backend-team" / "backend-agent"
    )
    path = inbox / "task.json"
    path.write_text(
        json.dumps(sample_task, indent=2), encoding="utf-8"
    )
    return path
