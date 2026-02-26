"""Tests for backend_task_parser."""
from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from Agents.backend_agent.backend_task_parser import (
    parse_task,
    parse_task_file,
    validate_task,
)
from Agents.backend_agent.tests.conftest import SAMPLE_TASK


class TestValidTasks:
    """Verify acceptance of correctly formed tasks."""

    def test_process_sheet_request(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        result = validate_task(task)
        assert result.ok
        assert result.task is not None

    def test_validate_payload(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"] = {
            "operation": "validate_payload",
            "payload": {"key": "value"},
            "schema_name": "user_schema_v1",
        }
        result = validate_task(task)
        assert result.ok

    def test_aggregate_reports(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"] = {
            "operation": "aggregate_reports",
            "reports": [{"id": "r1", "status": "ok"}],
        }
        result = validate_task(task)
        assert result.ok

    def test_route_directive(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"] = {
            "operation": "route_directive",
            "directive": "sync_all",
        }
        result = validate_task(task)
        assert result.ok

    def test_compute_diff(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"] = {
            "operation": "compute_diff",
            "sheet_id": "sheet_xyz",
        }
        result = validate_task(task)
        assert result.ok


class TestInvalidSchema:
    """Verify rejection of malformed tasks."""

    def test_missing_task_id(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        del task["task_id"]
        result = validate_task(task)
        assert not result.ok
        assert any("task_id" in e for e in result.errors)

    def test_missing_request(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        del task["request"]
        result = validate_task(task)
        assert not result.ok

    def test_bad_operation(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"]["operation"] = "hack_server"
        result = validate_task(task)
        assert not result.ok

    def test_additional_properties(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["extra_field"] = "not_allowed"
        result = validate_task(task)
        assert not result.ok

    def test_missing_metadata(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        del task["metadata"]
        result = validate_task(task)
        assert not result.ok

    def test_bad_source(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metadata"]["source"] = "unknown_source"
        result = validate_task(task)
        assert not result.ok


class TestSemanticViolations:
    """Verify business-rule checks beyond JSON Schema."""

    def test_process_sheet_request_missing_sheet_id(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        del task["request"]["sheet_id"]
        result = validate_task(task)
        assert not result.ok
        assert any("sheet_id" in e for e in result.errors)

    def test_process_sheet_request_missing_changes(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        del task["request"]["changes"]
        result = validate_task(task)
        assert not result.ok
        assert any("changes" in e for e in result.errors)

    def test_process_sheet_request_empty_changes(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"]["changes"] = []
        result = validate_task(task)
        assert not result.ok
        assert any("changes" in e for e in result.errors)

    def test_validate_payload_missing_payload(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"] = {
            "operation": "validate_payload",
            "schema_name": "test_schema",
        }
        result = validate_task(task)
        assert not result.ok
        assert any("payload" in e for e in result.errors)

    def test_validate_payload_missing_schema_name(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"] = {
            "operation": "validate_payload",
            "payload": {"key": "value"},
        }
        result = validate_task(task)
        assert not result.ok
        assert any("schema_name" in e for e in result.errors)

    def test_aggregate_reports_missing_reports(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"] = {
            "operation": "aggregate_reports",
        }
        result = validate_task(task)
        assert not result.ok
        assert any("reports" in e for e in result.errors)

    def test_aggregate_reports_empty_reports(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["request"] = {
            "operation": "aggregate_reports",
            "reports": [],
        }
        result = validate_task(task)
        assert not result.ok
        assert any("reports" in e for e in result.errors)


class TestRawParsing:
    """Test parsing from raw JSON strings."""

    def test_valid_json(self) -> None:
        raw = json.dumps(SAMPLE_TASK)
        result = parse_task(raw)
        assert result.ok

    def test_invalid_json(self) -> None:
        result = parse_task("{not valid json}")
        assert not result.ok
        assert any("Invalid JSON" in e for e in result.errors)


class TestFileParsing:
    """Test parsing from files."""

    def test_file_not_found(self, tmp_path: Any) -> None:
        result = parse_task_file(tmp_path / "nonexistent.json")
        assert not result.ok
        assert any("not found" in e for e in result.errors)

    def test_valid_file(self, task_file: Any) -> None:
        result = parse_task_file(task_file)
        assert result.ok
        assert result.task is not None
        assert result.task["task_id"] == "backend-042"
