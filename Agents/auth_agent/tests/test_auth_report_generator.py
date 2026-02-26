"""Tests for auth_report_generator."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from Agents.auth_agent.auth_report_generator import (
    generate_error_report,
    generate_report,
    write_report,
)
from Agents.auth_agent.tests.conftest import SAMPLE_TASK


class TestGenerateReport:
    """Verify report generation from valid tasks."""

    def test_issue_token_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="auth-test")
        assert report["status"] == "success"
        assert report["task_id"] == "auth-042"
        assert len(report["proposed_changes"]) == 1
        change = report["proposed_changes"][0]
        assert change["token_action"] == "issue_token"
        assert change["estimated_risk"] == "low"
        assert change["confidence"] == 0.95

    def test_revoke_token_risk(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["auth_request"]["operation"] = "revoke_token"
        task["auth_request"]["target_user_id"] = "emp_099"
        report = generate_report(task, agent_id="auth-test")
        change = report["proposed_changes"][0]
        assert change["estimated_risk"] == "medium"
        assert change["confidence"] == 0.90
        assert any("re-authenticate" in r for r in report["risks"])

    def test_service_account_risk_warning(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["auth_request"]["auth_type"] = "service_account"
        report = generate_report(task, agent_id="auth-test")
        assert any("allowlist" in r for r in report["risks"])

    def test_no_token_values_in_report(self) -> None:
        """SECURITY: Verify no actual token values appear."""
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="auth-test")
        report_str = json.dumps(report)
        # Should not contain any token-like strings
        assert "Bearer" not in report_str
        assert "ya29." not in report_str

    def test_validation_entries(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="auth-test")
        assert len(report["validation"]) >= 3
        assert all(v["ok"] for v in report["validation"])

    def test_timestamps_present(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="auth-test")
        assert "timestamp_utc" in report
        assert "timestamp_local" in report


class TestErrorReport:
    """Verify error report generation."""

    def test_error_report_format(self) -> None:
        report = generate_error_report(
            task_id="auth-err-01",
            agent_id="auth-test",
            errors=["Token refresh failed"],
        )
        assert report["status"] == "error"
        assert report["proposed_changes"] == []
        assert "Token refresh failed" in report["errors"]

    def test_error_report_timestamps(self) -> None:
        report = generate_error_report(
            task_id="auth-err-02",
            agent_id="auth-test",
            errors=["Vault unreachable"],
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
