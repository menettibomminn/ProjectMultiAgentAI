"""Shared fixtures for Controller tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from Controller.config import ControllerConfig


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_REPORT: dict[str, Any] = {
    "agent": "sheets-agent",
    "timestamp": "2026-02-24T10:33:00Z",
    "task_id": "sh-042",
    "status": "success",
    "summary": "Cell B5 updated from 100 to 150 on Sheet1",
    "metrics": {
        "duration_ms": 820,
        "tokens_in": 150,
        "tokens_out": 200,
        "cost_eur": 0.0005,
    },
    "artifacts": ["diff_B5_100_to_150.json"],
    "next_actions": [],
}

SAMPLE_CONTROLLER_TASK: dict[str, Any] = {
    "task_id": "ctrl-test-001",
    "skill": "process_inbox",
    "input": {"team": "sheets-team"},
    "metadata": {
        "source": "api",
        "priority": "normal",
        "timestamp": "2026-02-24T10:00:00Z",
    },
}


@pytest.fixture
def sample_report() -> dict[str, Any]:
    """Return a valid sample report dict."""
    return json.loads(json.dumps(SAMPLE_REPORT))


@pytest.fixture
def sample_task() -> dict[str, Any]:
    """Return a valid sample controller task dict."""
    return json.loads(json.dumps(SAMPLE_CONTROLLER_TASK))


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with Controller inbox/outbox structure."""
    controller_id = "test-controller"
    inbox = tmp_path / "Controller" / "inbox"
    inbox.mkdir(parents=True)
    outbox = tmp_path / "Controller" / "outbox"
    outbox.mkdir(parents=True)
    (tmp_path / "audit" / "controller" / controller_id).mkdir(parents=True)
    (tmp_path / "locks").mkdir(parents=True)
    (tmp_path / "Orchestrator").mkdir(parents=True)
    (tmp_path / "Orchestrator" / "STATE.md").write_text(
        "# STATE\n\n<!-- Managed by Controller -->\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def test_config(tmp_project: Path) -> ControllerConfig:
    """Return a config pointing at tmp_project with isolated HEALTH.md."""
    health = tmp_project / "HEALTH.md"
    health.write_text(
        "# HEALTH\n\n<!-- Append new entries below this line -->\n",
        encoding="utf-8",
    )
    return ControllerConfig(
        controller_id="test-controller",
        project_root=tmp_project,
        health_file_override=health,
        agent_health_paths={},
    )


@pytest.fixture
def inbox_report(tmp_project: Path, sample_report: dict[str, Any]) -> Path:
    """Write a sample report into the Controller inbox and return its path."""
    team_dir = tmp_project / "Controller" / "inbox" / "sheets-team" / "sheets-agent"
    team_dir.mkdir(parents=True, exist_ok=True)
    path = team_dir / "20260224T103300Z_report.json"
    path.write_text(json.dumps(sample_report), encoding="utf-8")
    return path


@pytest.fixture
def agent_health_dir(tmp_project: Path) -> Path:
    """Create fake HEALTH.md files for agents and return the agents root dir."""
    from datetime import datetime, timezone
    agents_dir = tmp_project / "Agents"
    now = datetime.now(timezone.utc).isoformat()

    agent_configs = {
        "sheets/HEALTH.md": {"status": "healthy", "failures": 0, "ts": now},
        "auth-agent/HEALTH.md": {"status": "healthy", "failures": 0, "ts": now},
        "backend-agent/HEALTH.md": {"status": "degraded", "failures": 4, "ts": now},
    }

    for rel_path, cfg in agent_configs.items():
        health_path = agents_dir / rel_path
        health_path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"# Agent HEALTH\n\n"
            f"### {cfg['ts']} — Task test-001\n\n"
            f"| Field | Value |\n"
            f"|---|---|\n"
            f"| last_run_timestamp | {cfg['ts']} |\n"
            f"| last_task_id | test-001 |\n"
            f"| last_status | {cfg['status']} |\n"
            f"| consecutive_failures | {cfg['failures']} |\n"
            f"| version | 1 |\n"
            f"| queue_length_estimate | 0 |\n"
            f"| notes | test fixture |\n"
        )
        health_path.write_text(content, encoding="utf-8")

    return agents_dir


@pytest.fixture
def test_config_with_health(
    tmp_project: Path, agent_health_dir: Path
) -> ControllerConfig:
    """Config with agent_health_paths pointing at the test fixture HEALTH.md files."""
    health = tmp_project / "HEALTH.md"
    health.write_text(
        "# HEALTH\n\n<!-- Append new entries below this line -->\n",
        encoding="utf-8",
    )
    return ControllerConfig(
        controller_id="test-controller",
        project_root=tmp_project,
        health_file_override=health,
        agent_health_paths={
            "sheets-agent": "Agents/sheets/HEALTH.md",
            "auth-agent": "Agents/auth-agent/HEALTH.md",
            "backend-agent": "Agents/backend-agent/HEALTH.md",
        },
    )
