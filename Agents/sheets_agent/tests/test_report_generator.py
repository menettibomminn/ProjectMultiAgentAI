"""Tests for sheets_report_generator — task to proposed_changes mapping."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from Agents.sheets_agent.sheets_report_generator import (
    generate_error_report,
    generate_report,
    write_report,
)


class TestGenerateReport:
    """Test the report generation from a valid task."""

    def test_basic_update(self, sample_task: dict[str, Any]) -> None:
        report = generate_report(sample_task, agent_id="test-agent")

        assert report["agent_id"] == "test-agent"
        assert report["task_id"] == "test-task-001"
        assert report["status"] == "success"
        assert report["errors"] == []
        assert report["version"] == 1
        assert "timestamp_utc" in report
        assert "timestamp_local" in report

    def test_proposed_changes_match_requested(self, sample_task: dict[str, Any]) -> None:
        report = generate_report(sample_task, agent_id="test-agent")

        assert len(report["proposed_changes"]) == 1
        pc = report["proposed_changes"][0]
        assert pc["op"] == "update"
        assert pc["range"] == "A2:C2"
        assert pc["new_values"] == [["Mario", "Rossi", "100"]]
        assert pc["old_values"] is None  # agent does not read from Sheets
        assert pc["sheet"]["spreadsheet_id"] == "abc123-spreadsheet"
        assert pc["sheet"]["sheet_name"] == "Foglio1"

    def test_confidence_and_risk_update(self, sample_task: dict[str, Any]) -> None:
        report = generate_report(sample_task, agent_id="test-agent")
        pc = report["proposed_changes"][0]
        assert pc["confidence"] == 0.95
        assert pc["estimated_risk"] == "low"

    def test_delete_row_risk(self, sample_task: dict[str, Any]) -> None:
        sample_task["requested_changes"] = [
            {"op": "delete_row", "range": "A5:A5"}
        ]
        report = generate_report(sample_task, agent_id="test-agent")
        pc = report["proposed_changes"][0]
        assert pc["estimated_risk"] == "medium"
        assert pc["confidence"] == 0.85
        assert len(report["risks"]) >= 1

    def test_clear_range_risk(self, sample_task: dict[str, Any]) -> None:
        sample_task["requested_changes"] = [
            {"op": "clear_range", "range": "A1:Z100"}
        ]
        report = generate_report(sample_task, agent_id="test-agent")
        pc = report["proposed_changes"][0]
        assert pc["estimated_risk"] == "high"
        assert pc["confidence"] == 0.80
        assert len(report["risks"]) >= 1

    def test_multiple_changes(self, sample_task: dict[str, Any]) -> None:
        sample_task["requested_changes"] = [
            {"op": "update", "range": "A1:A1", "values": [["1"]]},
            {"op": "delete_row", "range": "B2:B2"},
            {"op": "append_row", "range": "C3:D3", "values": [["x", "y"]]},
        ]
        report = generate_report(sample_task, agent_id="test-agent")
        assert len(report["proposed_changes"]) == 3
        assert len(report["validation"]) == 6  # 2 entries per change

    def test_validation_entries(self, sample_task: dict[str, Any]) -> None:
        report = generate_report(sample_task, agent_id="test-agent")
        assert len(report["validation"]) == 2  # range + op for 1 change
        for v in report["validation"]:
            assert v["ok"] is True
            assert "field" in v


class TestGenerateErrorReport:
    """Test error report generation."""

    def test_error_report_structure(self) -> None:
        report = generate_error_report(
            task_id="err-001",
            agent_id="test-agent",
            errors=["Schema validation failed: missing field"],
        )
        assert report["status"] == "error"
        assert report["task_id"] == "err-001"
        assert report["proposed_changes"] == []
        assert len(report["errors"]) == 1


class TestWriteReport:
    """Test atomic report writing."""

    def test_write_creates_file(self, tmp_path: Path) -> None:
        report = {"test": True}
        path = tmp_path / "sub" / "report.json"
        write_report(report, path)

        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["test"] is True

    def test_write_overwrites(self, tmp_path: Path) -> None:
        path = tmp_path / "report.json"
        write_report({"v": 1}, path)
        write_report({"v": 2}, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["v"] == 2
