"""Tests for frontend_report_generator."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from Agents.frontend_agent.frontend_report_generator import (
    generate_error_report,
    generate_report,
    write_report,
)
from Agents.frontend_agent.tests.conftest import SAMPLE_TASK


class TestGenerateReport:
    """Verify report generation from valid tasks."""

    def test_render_dashboard_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="frontend-test")
        assert report["status"] == "success"
        assert report["task_id"] == "fe-001"
        assert len(report["proposed_changes"]) == 1
        change = report["proposed_changes"][0]
        assert change["component_type"] == "dashboard"
        assert change["estimated_risk"] == "low"
        assert change["confidence"] == 0.95
        assert change["approval_required"] is False

    def test_render_approval_form_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "render_approval_form"
        task["ui_request"].pop("sheets", None)
        task["ui_request"]["change"] = {
            "change_id": "chg-001",
            "sheet_id": "sheet_abc",
            "changes": [
                {"cell": "B2", "old_value": "100", "new_value": "200"}
            ],
        }
        report = generate_report(task, agent_id="frontend-test")
        change = report["proposed_changes"][0]
        assert change["component_type"] == "approval_form"
        assert change["approval_required"] is True
        assert change["confidence"] == 0.95

    def test_render_audit_log_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "render_audit_log"
        task["ui_request"].pop("sheets", None)
        report = generate_report(task, agent_id="frontend-test")
        change = report["proposed_changes"][0]
        assert change["component_type"] == "audit_table"
        assert change["approval_required"] is False

    def test_validate_input_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "validate_input"
        task["ui_request"].pop("sheets", None)
        task["ui_request"]["form_data"] = {"name": "Test"}
        task["ui_request"]["schema_name"] = "user_profile"
        report = generate_report(task, agent_id="frontend-test")
        change = report["proposed_changes"][0]
        assert change["component_type"] == "validation_result"
        assert change["confidence"] == 0.99
        assert change["approval_required"] is False

    def test_format_error_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "format_error"
        task["ui_request"].pop("sheets", None)
        task["ui_request"]["error"] = {
            "code": "ERR_TIMEOUT",
            "message": "Request timed out",
        }
        report = generate_report(task, agent_id="frontend-test")
        change = report["proposed_changes"][0]
        assert change["component_type"] == "error_display"
        assert change["confidence"] == 0.90
        assert change["approval_required"] is False

    def test_no_sheets_access_risk_note(self) -> None:
        """All reports must include the no-sheets-access risk note."""
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="frontend-test")
        assert any(
            "does not access Google Sheets directly" in r
            for r in report["risks"]
        )

    def test_validation_entries(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="frontend-test")
        assert len(report["validation"]) >= 3
        assert all(v["ok"] for v in report["validation"])

    def test_timestamps_present(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="frontend-test")
        assert "timestamp_utc" in report
        assert "timestamp_local" in report


class TestErrorReport:
    """Verify error report generation."""

    def test_error_report_format(self) -> None:
        report = generate_error_report(
            task_id="fe-err-01",
            agent_id="frontend-test",
            errors=["Render failed"],
        )
        assert report["status"] == "error"
        assert report["proposed_changes"] == []
        assert "Render failed" in report["errors"]

    def test_error_report_timestamps(self) -> None:
        report = generate_error_report(
            task_id="fe-err-02",
            agent_id="frontend-test",
            errors=["Template missing"],
        )
        assert "timestamp_utc" in report
        assert "timestamp_local" in report


class TestWriteReport:
    """Verify atomic file writing."""

    def test_atomic_write(self, tmp_path: Path) -> None:
        report = {"task_id": "test", "status": "success"}
        path = tmp_path / "inbox" / "report.json"
        write_report(report, path)
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["task_id"] == "test"
        # Verify .tmp file was cleaned up
        assert not path.with_suffix(".tmp").exists()

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "report.json"
        write_report({"ok": True}, path)
        assert path.exists()
