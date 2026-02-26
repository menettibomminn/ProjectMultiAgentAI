"""End-to-end test: feed a sample task, verify report.json and audit/ output."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from Agents.sheets_agent.config import SheetsAgentConfig
from Agents.sheets_agent.sheets_agent import SheetsAgent


class TestE2E:
    """Simulated end-to-end test with filesystem I/O."""

    def test_full_pipeline(
        self, tmp_project: Path, test_config: SheetsAgentConfig, sample_task: dict[str, Any]
    ) -> None:
        """Process a valid task and verify all outputs."""
        # Write task to inbox
        task_path = test_config.task_file
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(json.dumps(sample_task), encoding="utf-8")

        # Run agent
        agent = SheetsAgent(test_config)
        success = agent.run_once()

        assert success is True

        # Verify report.json exists
        report_path = test_config.report_file
        assert report_path.exists(), f"report.json not found at {report_path}"
        report = json.loads(report_path.read_text(encoding="utf-8"))

        assert report["agent_id"] == "test-agent"
        assert report["task_id"] == "test-task-001"
        assert report["status"] == "success"
        assert len(report["proposed_changes"]) == 1
        assert report["proposed_changes"][0]["op"] == "update"
        assert report["proposed_changes"][0]["new_values"] == [["Mario", "Rossi", "100"]]
        assert report["proposed_changes"][0]["old_values"] is None
        assert report["errors"] == []
        assert report["version"] == 1

        # Verify audit file exists
        audit_dir = test_config.audit_dir
        audit_files = list(audit_dir.glob("*.json"))
        assert len(audit_files) == 1, f"Expected 1 audit file, found {len(audit_files)}"
        audit = json.loads(audit_files[0].read_text(encoding="utf-8"))
        assert audit["task_id"] == "test-task-001"
        assert audit["agent_id"] == "test-agent"
        assert audit["report_checksum"] is not None
        assert audit["error"] is None

        # Verify task was archived
        assert not task_path.exists(), "task.json should be renamed to task.done.json"
        done_path = task_path.with_suffix(".done.json")
        assert done_path.exists()

        # Verify HEALTH.md was updated
        health_text = test_config.health_file.read_text(encoding="utf-8")
        assert "test-task-001" in health_text
        assert "healthy" in health_text

    def test_no_task_returns_false(
        self, tmp_project: Path, test_config: SheetsAgentConfig
    ) -> None:
        """When no task.json exists, run_once returns False."""
        agent = SheetsAgent(test_config)
        result = agent.run_once()
        assert result is False

    def test_invalid_task_produces_error_report(
        self, tmp_project: Path, test_config: SheetsAgentConfig
    ) -> None:
        """An invalid task produces an error report."""
        task_path = test_config.task_file
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text('{"task_id":"bad","invalid":true}', encoding="utf-8")

        agent = SheetsAgent(test_config)
        success = agent.run_once()

        assert success is False
        report_path = test_config.report_file
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["status"] == "error"
        assert len(report["errors"]) > 0

    def test_idempotency(
        self, tmp_project: Path, test_config: SheetsAgentConfig, sample_task: dict[str, Any]
    ) -> None:
        """Running twice with the same task should be idempotent."""
        task_path = test_config.task_file
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(json.dumps(sample_task), encoding="utf-8")

        agent = SheetsAgent(test_config)
        agent.run_once()

        # Write task again (simulating re-delivery)
        task_path.write_text(json.dumps(sample_task), encoding="utf-8")
        result = agent.run_once()
        # Second run should detect existing report and skip
        assert result is True
