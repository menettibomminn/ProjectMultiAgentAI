"""Tests for auth_task_parser."""
from __future__ import annotations

import copy
import json
from typing import Any


from Agents.auth_agent.auth_task_parser import (
    parse_task,
    parse_task_file,
    validate_task,
)
from Agents.auth_agent.tests.conftest import SAMPLE_TASK


class TestValidTasks:
    """Verify acceptance of correctly formed tasks."""

    def test_issue_token(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        result = validate_task(task)
        assert result.ok
        assert result.task is not None

    def test_refresh_token(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["auth_request"]["operation"] = "refresh_token"
        result = validate_task(task)
        assert result.ok

    def test_revoke_token(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["auth_request"]["operation"] = "revoke_token"
        task["auth_request"]["target_user_id"] = "emp_099"
        result = validate_task(task)
        assert result.ok

    def test_validate_scopes(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["auth_request"]["operation"] = "validate_scopes"
        result = validate_task(task)
        assert result.ok

    def test_service_account_auth_type(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["auth_request"]["auth_type"] = "service_account"
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

    def test_missing_auth_request(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        del task["auth_request"]
        result = validate_task(task)
        assert not result.ok

    def test_bad_operation(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["auth_request"]["operation"] = "hack_token"
        result = validate_task(task)
        assert not result.ok

    def test_empty_scopes(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["auth_request"]["scopes"] = []
        result = validate_task(task)
        assert not result.ok

    def test_additional_properties(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["extra_field"] = "not_allowed"
        result = validate_task(task)
        assert not result.ok


class TestSemanticViolations:
    """Verify business-rule checks beyond JSON Schema."""

    def test_invalid_scope(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["auth_request"]["scopes"] = ["spreadsheets", "drive"]
        result = validate_task(task)
        assert not result.ok
        assert any("Scope violation" in e for e in result.errors)

    def test_revoke_without_target(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["auth_request"]["operation"] = "revoke_token"
        # No target_user_id
        result = validate_task(task)
        assert not result.ok
        assert any("target_user_id" in e for e in result.errors)


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
        assert result.task["task_id"] == "auth-042"
