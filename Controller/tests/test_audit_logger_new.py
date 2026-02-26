"""Tests for Controller.audit_logger (new facade)."""
from __future__ import annotations

import json
from pathlib import Path

from Controller.audit_logger import (
    AuditLogger,
    compute_checksum,
    verify_report_checksum,
    write_audit_entry,
    write_hash_file,
)


class TestReExports:
    """Verify that the facade re-exports from controller_audit_logger."""

    def test_compute_checksum(self) -> None:
        h = compute_checksum({"a": 1})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest

    def test_verify_report_checksum(self, tmp_path: Path) -> None:
        report = tmp_path / "r.json"
        report.write_text('{"x": 1}', encoding="utf-8")
        ok, _hash = verify_report_checksum(report)
        assert ok is True

    def test_write_hash_file(self, tmp_path: Path) -> None:
        report = tmp_path / "r.json"
        report.write_text('{"x": 1}', encoding="utf-8")
        path = write_hash_file(report, "abc123")
        assert path.exists()
        assert "abc123" in path.read_text(encoding="utf-8")

    def test_write_audit_entry(self, tmp_path: Path) -> None:
        path = write_audit_entry(
            audit_dir=tmp_path,
            task_id="t1",
            controller_id="ctrl",
            op_steps=[],
            processed_reports=[],
            directives_emitted=[],
            report={"data": 1},
        )
        assert path.exists()


class TestAuditLogger:
    """Test the AuditLogger class."""

    def test_log_operation(self, tmp_path: Path) -> None:
        logger = AuditLogger(tmp_path / "audit", controller_id="ctrl-01")
        path = logger.log_operation(
            action="test_action",
            resource="sheet-A",
            agent="agent-1",
            result="ok",
        )
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["action"] == "test_action"
        assert data["resource"] == "sheet-A"
        assert data["agent"] == "agent-1"
        assert data["result"] == "ok"
        assert data["controller_id"] == "ctrl-01"
        assert "timestamp" in data

    def test_log_operation_creates_dir(self, tmp_path: Path) -> None:
        logger = AuditLogger(tmp_path / "deep" / "audit")
        path = logger.log_operation(action="create_dir_test")
        assert path.exists()

    def test_log_lock_acquired(self, tmp_path: Path) -> None:
        logger = AuditLogger(tmp_path / "audit")
        path = logger.log_lock_acquired("res-1", "agent-a")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["action"] == "lock_acquired"
        assert data["resource"] == "res-1"

    def test_log_lock_released(self, tmp_path: Path) -> None:
        logger = AuditLogger(tmp_path / "audit")
        path = logger.log_lock_released("res-1", "agent-a")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["action"] == "lock_released"

    def test_log_alert_emitted(self, tmp_path: Path) -> None:
        logger = AuditLogger(tmp_path / "audit")
        path = logger.log_alert_emitted("res-1", "agent-a", "zombie detected")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["action"] == "alert_emitted"
        assert data["result"] == "zombie detected"

    def test_log_health_check(self, tmp_path: Path) -> None:
        logger = AuditLogger(tmp_path / "audit")
        path = logger.log_health_check("healthy")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["action"] == "health_check"
        assert data["result"] == "healthy"
        assert data["resource"] == "system"
