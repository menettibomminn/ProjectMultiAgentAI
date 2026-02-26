"""Shared fixtures for metrics_agent tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from Agents.metrics_agent.config import MetricsAgentConfig

SAMPLE_TASK: dict[str, Any] = {
    "task_id": "metrics-001",
    "user_id": "system",
    "team_id": "platform-team",
    "metrics_request": {
        "operation": "collect_team_metrics",
        "target_team_id": "sheets-team",
        "period": "2026-02-23",
    },
    "metadata": {
        "source": "scheduler",
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
        / "platform-team" / "metrics-agent"
    )
    inbox.mkdir(parents=True)
    (tmp_path / "ops" / "audit" / "metrics-agent").mkdir(parents=True)
    (tmp_path / "locks").mkdir(parents=True)
    # Create a minimal HEALTH.md
    health = tmp_path / "HEALTH.md"
    health.write_text("# Metrics Agent — HEALTH\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def test_config(tmp_project: Path) -> MetricsAgentConfig:
    """Return a config pointing to the temporary project."""
    return MetricsAgentConfig(
        agent_id="metrics-test-01",
        team_id="platform-team",
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
        / "platform-team" / "metrics-agent"
    )
    path = inbox / "task.json"
    path.write_text(
        json.dumps(sample_task, indent=2), encoding="utf-8"
    )
    return path
