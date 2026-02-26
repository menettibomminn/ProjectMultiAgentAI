"""Tests for controller_task_parser module."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


from Controller.controller_task_parser import (
    parse_report,
    parse_report_file,
    parse_task,
    parse_task_file,
    validate_report,
    validate_task,
)


class TestReportValidation:
    """Tests for report_v1 validation."""

    def test_valid_report(self, sample_report: dict[str, Any]) -> None:
        result = validate_report(sample_report)
        assert result.ok is True
        assert result.data is not None
        assert result.data["agent"] == "sheets-agent"

    def test_missing_required_field(self, sample_report: dict[str, Any]) -> None:
        del sample_report["agent"]
        result = validate_report(sample_report)
        assert result.ok is False
        assert any("agent" in e for e in result.errors)

    def test_invalid_status(self, sample_report: dict[str, Any]) -> None:
        sample_report["status"] = "unknown_status"
        result = validate_report(sample_report)
        assert result.ok is False
        assert any("status" in e for e in result.errors)

    def test_missing_metrics_duration(self, sample_report: dict[str, Any]) -> None:
        del sample_report["metrics"]["duration_ms"]
        result = validate_report(sample_report)
        assert result.ok is False
        assert any("duration_ms" in e for e in result.errors)

    def test_negative_duration(self, sample_report: dict[str, Any]) -> None:
        sample_report["metrics"]["duration_ms"] = -1
        result = validate_report(sample_report)
        assert result.ok is False

    def test_parse_report_valid_json(self, sample_report: dict[str, Any]) -> None:
        raw = json.dumps(sample_report)
        result = parse_report(raw)
        assert result.ok is True

    def test_parse_report_invalid_json(self) -> None:
        result = parse_report("{broken")
        assert result.ok is False
        assert any("Invalid JSON" in e for e in result.errors)

    def test_parse_report_file_not_found(self, tmp_path: Path) -> None:
        result = parse_report_file(tmp_path / "missing.json")
        assert result.ok is False
        assert any("not found" in e for e in result.errors)

    def test_parse_report_file_valid(
        self, tmp_path: Path, sample_report: dict[str, Any]
    ) -> None:
        path = tmp_path / "report.json"
        path.write_text(json.dumps(sample_report), encoding="utf-8")
        result = parse_report_file(path)
        assert result.ok is True

    def test_additional_properties_allowed(
        self, sample_report: dict[str, Any]
    ) -> None:
        sample_report["extra_field"] = "extra_value"
        result = validate_report(sample_report)
        assert result.ok is True


class TestControllerTaskValidation:
    """Tests for controller task validation."""

    def test_valid_process_inbox(self, sample_task: dict[str, Any]) -> None:
        result = validate_task(sample_task)
        assert result.ok is True

    def test_missing_skill(self, sample_task: dict[str, Any]) -> None:
        del sample_task["skill"]
        result = validate_task(sample_task)
        assert result.ok is False

    def test_invalid_skill(self, sample_task: dict[str, Any]) -> None:
        sample_task["skill"] = "invalid_skill"
        result = validate_task(sample_task)
        assert result.ok is False

    def test_emit_directive_requires_directive(self) -> None:
        task = {
            "task_id": "ctrl-002",
            "skill": "emit_directive",
            "input": {},
        }
        result = validate_task(task)
        assert result.ok is False
        assert any("directive" in e for e in result.errors)

    def test_reroute_task_requires_failed_agent(self) -> None:
        task = {
            "task_id": "ctrl-003",
            "skill": "reroute_task",
            "input": {},
        }
        result = validate_task(task)
        assert result.ok is False
        assert any("failed_agent" in e for e in result.errors)

    def test_aggregate_requires_team(self) -> None:
        task = {
            "task_id": "ctrl-004",
            "skill": "aggregate_team_reports",
            "input": {},
        }
        result = validate_task(task)
        assert result.ok is False
        assert any("team" in e for e in result.errors)

    def test_parse_task_invalid_json(self) -> None:
        result = parse_task("{broken")
        assert result.ok is False

    def test_parse_task_file_not_found(self, tmp_path: Path) -> None:
        result = parse_task_file(tmp_path / "missing.json")
        assert result.ok is False
