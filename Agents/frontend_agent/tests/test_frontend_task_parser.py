"""Tests for frontend_task_parser."""
from __future__ import annotations

import copy
import json
from typing import Any


from Agents.frontend_agent.frontend_task_parser import (
    parse_task,
    parse_task_file,
    validate_task,
)
from Agents.frontend_agent.tests.conftest import SAMPLE_TASK


class TestValidTasks:
    """Verify acceptance of correctly formed tasks."""

    def test_render_dashboard(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        result = validate_task(task)
        assert result.ok
        assert result.task is not None

    def test_render_approval_form(self) -> None:
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
        result = validate_task(task)
        assert result.ok

    def test_render_audit_log(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "render_audit_log"
        task["ui_request"].pop("sheets", None)
        task["ui_request"]["filters"] = {
            "agent": "sheets-agent",
            "date_from": "2026-01-01",
            "date_to": "2026-02-23",
        }
        result = validate_task(task)
        assert result.ok

    def test_validate_input(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "validate_input"
        task["ui_request"].pop("sheets", None)
        task["ui_request"]["form_data"] = {"name": "Test User", "email": "test@example.com"}
        task["ui_request"]["schema_name"] = "user_profile"
        result = validate_task(task)
        assert result.ok

    def test_format_error(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "format_error"
        task["ui_request"].pop("sheets", None)
        task["ui_request"]["error"] = {
            "code": "ERR_TIMEOUT",
            "message": "Request timed out after 30s",
        }
        result = validate_task(task)
        assert result.ok

    def test_render_audit_log_no_filters(self) -> None:
        """render_audit_log does not require filters."""
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "render_audit_log"
        task["ui_request"].pop("sheets", None)
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

    def test_missing_ui_request(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        del task["ui_request"]
        result = validate_task(task)
        assert not result.ok

    def test_bad_operation(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "render_magic"
        result = validate_task(task)
        assert not result.ok

    def test_additional_properties(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["extra_field"] = "not_allowed"
        result = validate_task(task)
        assert not result.ok

    def test_bad_metadata_source(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metadata"]["source"] = "unknown-source"
        result = validate_task(task)
        assert not result.ok

    def test_missing_metadata(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        del task["metadata"]
        result = validate_task(task)
        assert not result.ok


class TestSemanticViolations:
    """Verify business-rule checks beyond JSON Schema."""

    def test_render_dashboard_missing_sheets(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "render_dashboard"
        task["ui_request"].pop("sheets", None)
        result = validate_task(task)
        assert not result.ok
        assert any("sheets" in e for e in result.errors)

    def test_render_dashboard_empty_sheets(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "render_dashboard"
        task["ui_request"]["sheets"] = []
        result = validate_task(task)
        assert not result.ok
        assert any("sheets" in e for e in result.errors)

    def test_render_approval_form_missing_change(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "render_approval_form"
        task["ui_request"].pop("sheets", None)
        # No change object
        result = validate_task(task)
        assert not result.ok
        assert any("change" in e for e in result.errors)

    def test_validate_input_missing_form_data(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "validate_input"
        task["ui_request"].pop("sheets", None)
        task["ui_request"]["schema_name"] = "user_profile"
        # No form_data
        result = validate_task(task)
        assert not result.ok
        assert any("form_data" in e for e in result.errors)

    def test_validate_input_missing_schema_name(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "validate_input"
        task["ui_request"].pop("sheets", None)
        task["ui_request"]["form_data"] = {"key": "value"}
        # No schema_name
        result = validate_task(task)
        assert not result.ok
        assert any("schema_name" in e for e in result.errors)

    def test_format_error_missing_error(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["ui_request"]["operation"] = "format_error"
        task["ui_request"].pop("sheets", None)
        # No error object
        result = validate_task(task)
        assert not result.ok
        assert any("error" in e for e in result.errors)


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
        assert result.task["task_id"] == "fe-001"
