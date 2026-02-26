"""Tests for backend_report_generator."""
from __future__ import annotations

import copy
import json
from pathlib import Path


from Agents.backend_agent.backend_report_generator import (
    generate_error_report,
    generate_report,
    write_report,
)
from Agents.backend_agent.tests.conftest import SAMPLE_TASK


class TestGenerateReport:
    """Verify report generation from valid tasks."""

    def test_process_sheet_request_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="backend-test")
        assert report["status"] == "success"
        assert report["task_id"] == "backend-042"
        assert len(report["proposed_changes"]) == 1
        change = report["proposed_changes"][0]
        assert change["operation"] == "process_sheet_request"
        assert change["risk"] == "low"
        assert change["confidence"] == 0.90

    def test_validate_payload_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"] = {
            "operation": "validate_payload",
            "payload": {"key": "value"},
            "schema_name": "user_schema_v1",
        }
        report = generate_report(task, agent_id="backend-test")
        change = report["proposed_changes"][0]
        assert change["confidence"] == 0.99
        assert change["risk"] == "low"
        assert change["details"]["validated_payload"] is True

    def test_route_directive_risk(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"] = {
            "operation": "route_directive",
            "directive": "sync_all",
        }
        report = generate_report(task, agent_id="backend-test")
        change = report["proposed_changes"][0]
        assert change["risk"] == "medium"
        assert change["confidence"] == 0.90
        assert any("handler" in r for r in report["risks"])

    def test_compute_diff_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"] = {
            "operation": "compute_diff",
            "sheet_id": "sheet_xyz",
        }
        report = generate_report(task, agent_id="backend-test")
        change = report["proposed_changes"][0]
        assert change["risk"] == "low"
        assert change["confidence"] == 0.95
        assert change["details"]["computed_diff"] is True

    def test_bulk_write_high_risk(self) -> None:
        """process_sheet_request with > 100 changes should be high risk."""
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"]["changes"] = [
            {"cell": f"A{i}", "old_value": "0", "new_value": str(i)}
            for i in range(101)
        ]
        report = generate_report(task, agent_id="backend-test")
        change = report["proposed_changes"][0]
        assert change["risk"] == "high"
        assert any("batching" in r for r in report["risks"])

    def test_validation_entries(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="backend-test")
        assert len(report["validation"]) >= 2
        assert all(v["ok"] for v in report["validation"])

    def test_timestamps_present(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="backend-test")
        assert "timestamp_utc" in report
        assert "timestamp_local" in report


class TestErrorReport:
    """Verify error report generation."""

    def test_error_report_format(self) -> None:
        report = generate_error_report(
            task_id="backend-err-01",
            agent_id="backend-test",
            errors=["Sheet not found"],
        )
        assert report["status"] == "error"
        assert report["proposed_changes"] == []
        assert "Sheet not found" in report["errors"]

    def test_error_report_timestamps(self) -> None:
        report = generate_error_report(
            task_id="backend-err-02",
            agent_id="backend-test",
            errors=["Service unavailable"],
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
