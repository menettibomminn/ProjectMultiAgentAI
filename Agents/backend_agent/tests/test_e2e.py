"""End-to-end integration tests for the backend agent pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from Agents.backend_agent.backend_agent import BackendAgent
from Agents.backend_agent.config import BackendAgentConfig


class TestFullPipeline:
    """Verify the complete 10-step pipeline."""

    def test_full_pipeline(
        self, test_config: BackendAgentConfig, task_file: Path
    ) -> None:
        agent = BackendAgent(test_config)
        result = agent.run_once()
        assert result is True

        # Report written
        report_path = test_config.report_file
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["status"] == "success"
        assert report["task_id"] == "backend-042"
        assert len(report["proposed_changes"]) == 1

        # Task archived
        done_path = task_file.with_suffix(".done.json")
        assert done_path.exists()
        assert not task_file.exists()

        # Audit written
        audit_dir = test_config.audit_dir
        assert audit_dir.exists()
        audit_files = list(audit_dir.glob("*.json"))
        assert len(audit_files) == 1

        # HEALTH.md updated
        health_text = test_config.health_file.read_text(encoding="utf-8")
        assert "backend-042" in health_text
        assert "healthy" in health_text

    def test_no_task_returns_false(
        self, test_config: BackendAgentConfig
    ) -> None:
        agent = BackendAgent(test_config)
        result = agent.run_once()
        assert result is False

    def test_invalid_task_produces_error_report(
        self, test_config: BackendAgentConfig
    ) -> None:
        # Write an invalid task
        inbox = test_config.inbox_dir
        inbox.mkdir(parents=True, exist_ok=True)
        task_path = inbox / "task.json"
        task_path.write_text(
            json.dumps({"task_id": "bad-task", "invalid": True}),
            encoding="utf-8",
        )

        agent = BackendAgent(test_config)
        result = agent.run_once()
        assert result is False

        report = json.loads(
            test_config.report_file.read_text(encoding="utf-8")
        )
        assert report["status"] == "error"
        assert len(report["errors"]) > 0

    def test_idempotency(
        self, test_config: BackendAgentConfig, task_file: Path
    ) -> None:
        agent = BackendAgent(test_config)

        # First run — processes task
        result1 = agent.run_once()
        assert result1 is True

        # Write task again with same task_id
        inbox = test_config.inbox_dir
        task_path = inbox / "task.json"
        task_data = {
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
        task_path.write_text(
            json.dumps(task_data, indent=2), encoding="utf-8"
        )

        # Second run — should skip (idempotent)
        result2 = agent.run_once()
        assert result2 is True
