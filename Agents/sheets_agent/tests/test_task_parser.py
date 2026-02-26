"""Tests for sheets_task_parser — schema and semantic validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


from Agents.sheets_agent.sheets_task_parser import parse_task, parse_task_file, validate_task
from Agents.sheets_agent.tests.conftest import SAMPLE_TASK


class TestParseTaskValid:
    """Valid task scenarios."""

    def test_valid_update(self, sample_task: dict[str, Any]) -> None:
        result = validate_task(sample_task)
        assert result.ok is True
        assert result.task is not None
        assert result.task["task_id"] == "test-task-001"
        assert result.errors == []

    def test_valid_append_row(self, sample_task: dict[str, Any]) -> None:
        sample_task["requested_changes"] = [
            {"op": "append_row", "range": "A10:C10", "values": [["X", "Y", "Z"]]}
        ]
        result = validate_task(sample_task)
        assert result.ok is True

    def test_valid_delete_row(self, sample_task: dict[str, Any]) -> None:
        sample_task["requested_changes"] = [
            {"op": "delete_row", "range": "A5:A5"}
        ]
        result = validate_task(sample_task)
        assert result.ok is True

    def test_valid_clear_range(self, sample_task: dict[str, Any]) -> None:
        sample_task["requested_changes"] = [
            {"op": "clear_range", "range": "B1:D10"}
        ]
        result = validate_task(sample_task)
        assert result.ok is True

    def test_multiple_changes(self, sample_task: dict[str, Any]) -> None:
        sample_task["requested_changes"] = [
            {"op": "update", "range": "A1:A1", "values": [["1"]]},
            {"op": "append_row", "range": "A2:B2", "values": [["a", "b"]]},
        ]
        result = validate_task(sample_task)
        assert result.ok is True
        assert len(result.task["requested_changes"]) == 2  # type: ignore[index]


class TestParseTaskInvalid:
    """Invalid task scenarios."""

    def test_missing_task_id(self, sample_task: dict[str, Any]) -> None:
        del sample_task["task_id"]
        result = validate_task(sample_task)
        assert result.ok is False
        assert any("task_id" in e for e in result.errors)

    def test_missing_sheet(self, sample_task: dict[str, Any]) -> None:
        del sample_task["sheet"]
        result = validate_task(sample_task)
        assert result.ok is False

    def test_empty_requested_changes(self, sample_task: dict[str, Any]) -> None:
        sample_task["requested_changes"] = []
        result = validate_task(sample_task)
        assert result.ok is False

    def test_invalid_op(self, sample_task: dict[str, Any]) -> None:
        sample_task["requested_changes"] = [
            {"op": "drop_table", "range": "A1:A1"}
        ]
        result = validate_task(sample_task)
        assert result.ok is False

    def test_invalid_source(self, sample_task: dict[str, Any]) -> None:
        sample_task["metadata"]["source"] = "ftp"
        result = validate_task(sample_task)
        assert result.ok is False

    def test_invalid_priority(self, sample_task: dict[str, Any]) -> None:
        sample_task["metadata"]["priority"] = "critical"
        result = validate_task(sample_task)
        assert result.ok is False

    def test_additional_properties_rejected(self, sample_task: dict[str, Any]) -> None:
        sample_task["extra_field"] = "nope"
        result = validate_task(sample_task)
        assert result.ok is False

    def test_update_without_values(self, sample_task: dict[str, Any]) -> None:
        """Semantic: update requires values."""
        sample_task["requested_changes"] = [
            {"op": "update", "range": "A1:A1"}
        ]
        result = validate_task(sample_task)
        assert result.ok is False
        assert any("values" in e for e in result.errors)

    def test_delete_row_with_values(self, sample_task: dict[str, Any]) -> None:
        """Semantic: delete_row should not have values."""
        sample_task["requested_changes"] = [
            {"op": "delete_row", "range": "A1:A1", "values": [["oops"]]}
        ]
        result = validate_task(sample_task)
        assert result.ok is False


class TestParseTaskRawJson:
    """Tests for parse_task (raw JSON string input)."""

    def test_valid_json(self) -> None:
        raw = json.dumps(SAMPLE_TASK)
        result = parse_task(raw)
        assert result.ok is True

    def test_invalid_json(self) -> None:
        result = parse_task("{not valid json")
        assert result.ok is False
        assert any("Invalid JSON" in e for e in result.errors)

    def test_empty_string(self) -> None:
        result = parse_task("")
        assert result.ok is False


class TestParseTaskFile:
    """Tests for parse_task_file (file-based input)."""

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = parse_task_file(tmp_path / "nonexistent.json")
        assert result.ok is False
        assert any("not found" in e for e in result.errors)

    def test_valid_file(self, task_file: Path) -> None:
        result = parse_task_file(task_file)
        assert result.ok is True
        assert result.task is not None
