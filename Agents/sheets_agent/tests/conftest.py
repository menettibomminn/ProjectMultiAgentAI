"""Shared fixtures for sheets agent tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from Agents.sheets_agent.config import SheetsAgentConfig


# ---------------------------------------------------------------------------
# Sample task data
# ---------------------------------------------------------------------------

SAMPLE_TASK: dict[str, Any] = {
    "task_id": "test-task-001",
    "user_id": "user@example.com",
    "team_id": "sales",
    "sheet": {
        "spreadsheet_id": "abc123-spreadsheet",
        "sheet_name": "Foglio1",
    },
    "requested_changes": [
        {
            "op": "update",
            "range": "A2:C2",
            "values": [["Mario", "Rossi", "100"]],
        }
    ],
    "metadata": {
        "source": "web-ui",
        "priority": "normal",
        "timestamp": "2026-02-23T15:00:00+01:00",
    },
}


@pytest.fixture
def sample_task() -> dict[str, Any]:
    """Return a valid sample task dict."""
    return json.loads(json.dumps(SAMPLE_TASK))  # deep copy


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with inbox/audit/locks structure."""
    agent_id = "test-agent"
    inbox = tmp_path / "inbox" / "sheets" / agent_id
    inbox.mkdir(parents=True)
    (tmp_path / "audit" / "sheets" / agent_id).mkdir(parents=True)
    (tmp_path / "locks").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def test_config(tmp_project: Path) -> SheetsAgentConfig:
    """Return a config pointing at tmp_project with isolated HEALTH.md."""
    health = tmp_project / "HEALTH.md"
    health.write_text("# HEALTH\n\n<!-- Append new entries below this line -->\n", encoding="utf-8")
    return SheetsAgentConfig(
        agent_id="test-agent",
        team_id="test-team",
        project_root=tmp_project,
        health_file_override=health,
    )


@pytest.fixture
def task_file(tmp_project: Path, sample_task: dict[str, Any]) -> Path:
    """Write sample_task to the inbox and return its path."""
    agent_id = "test-agent"
    inbox = tmp_project / "inbox" / "sheets" / agent_id
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / "task.json"
    path.write_text(json.dumps(sample_task), encoding="utf-8")
    return path
