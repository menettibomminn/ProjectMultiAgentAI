"""Tests for Controller.audit_manager."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from Controller.audit_manager import AuditManager, AuditManagerError


@pytest.fixture
def audit_file(tmp_path: Path) -> Path:
    return tmp_path / "state" / "audit_log.jsonl"


@pytest.fixture
def audit(audit_file: Path) -> AuditManager:
    return AuditManager(audit_file)


class TestLogEvent:
    def test_creates_file(self, audit: AuditManager, audit_file: Path) -> None:
        audit.log_event("t-1", "agent-a", "test_action", "ok")
        assert audit_file.exists()

    def test_jsonl_format(self, audit: AuditManager, audit_file: Path) -> None:
        audit.log_event("t-1", "agent-a", "action1", "ok")
        audit.log_event("t-2", "agent-b", "action2", "error")
        lines = audit_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "timestamp" in data
            assert "task_id" in data

    def test_required_fields(self, audit: AuditManager, audit_file: Path) -> None:
        audit.log_event("t-1", "controller", "run_once", "ok")
        data = json.loads(audit_file.read_text(encoding="utf-8").strip())
        assert data["task_id"] == "t-1"
        assert data["agent"] == "controller"
        assert data["action"] == "run_once"
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert isinstance(data["details"], dict)

    def test_with_details(self, audit: AuditManager, audit_file: Path) -> None:
        audit.log_event("t-1", "a", "x", "ok", {"count": 5, "items": ["a", "b"]})
        data = json.loads(audit_file.read_text(encoding="utf-8").strip())
        assert data["details"]["count"] == 5
        assert data["details"]["items"] == ["a", "b"]

    def test_empty_details_default(self, audit: AuditManager, audit_file: Path) -> None:
        audit.log_event("t-1", "a", "x", "ok")
        data = json.loads(audit_file.read_text(encoding="utf-8").strip())
        assert data["details"] == {}

    def test_append_only(self, audit: AuditManager, audit_file: Path) -> None:
        audit.log_event("t-1", "a", "first", "ok")
        audit.log_event("t-2", "b", "second", "ok")
        audit.log_event("t-3", "c", "third", "ok")
        lines = audit_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3
        assert json.loads(lines[0])["action"] == "first"
        assert json.loads(lines[2])["action"] == "third"


class TestValidation:
    def test_empty_action_rejected(self, audit: AuditManager) -> None:
        with pytest.raises(AuditManagerError):
            audit.log_event("t-1", "a", "", "ok")

    def test_empty_status_rejected(self, audit: AuditManager) -> None:
        with pytest.raises(AuditManagerError):
            audit.log_event("t-1", "a", "action", "")

    def test_empty_task_id_rejected(self, audit: AuditManager) -> None:
        with pytest.raises(AuditManagerError):
            audit.log_event("", "a", "action", "ok")


class TestDirectoryCreation:
    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "a" / "b" / "c" / "audit.jsonl"
        audit = AuditManager(deep_path)
        audit.log_event("t-1", "a", "init", "ok")
        assert deep_path.exists()
