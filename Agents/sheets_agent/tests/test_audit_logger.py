"""Tests for sheets_audit_logger — audit file creation and checksums."""
from __future__ import annotations

import json
from pathlib import Path


from Agents.sheets_agent.sheets_audit_logger import compute_checksum, write_audit_entry


class TestComputeChecksum:
    """Test SHA-256 checksum computation."""

    def test_deterministic(self) -> None:
        data = {"a": 1, "b": 2}
        assert compute_checksum(data) == compute_checksum(data)

    def test_order_independent(self) -> None:
        """sort_keys ensures order independence."""
        assert compute_checksum({"a": 1, "b": 2}) == compute_checksum({"b": 2, "a": 1})

    def test_different_data(self) -> None:
        assert compute_checksum({"a": 1}) != compute_checksum({"a": 2})

    def test_returns_hex_string(self) -> None:
        h = compute_checksum({"x": "y"})
        assert len(h) == 64  # SHA-256 hex is 64 chars
        assert all(c in "0123456789abcdef" for c in h)


class TestWriteAuditEntry:
    """Test audit file writing."""

    def test_creates_file(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "audit"
        report = {"status": "success", "task_id": "t-001"}

        path = write_audit_entry(
            audit_dir=audit_dir,
            task_id="t-001",
            agent_id="test-agent",
            user_id="user@example.com",
            team_id="sales",
            config_version=1,
            op_steps=[{"step": "test", "ts": "2026-01-01T00:00:00Z"}],
            report=report,
        )

        assert path.exists()
        assert audit_dir.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["task_id"] == "t-001"
        assert data["agent_id"] == "test-agent"
        assert data["user_id"] == "user@example.com"
        assert data["report_checksum"] is not None
        assert data["error"] is None
        assert data["audit_version"] == 1

    def test_includes_runtime_metrics(self, tmp_path: Path) -> None:
        path = write_audit_entry(
            audit_dir=tmp_path,
            task_id="t-002",
            agent_id="a",
            user_id="u",
            team_id="t",
            config_version=1,
            op_steps=[],
            report={"x": 1},
            duration_ms=123.456,
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["runtime_metrics"]["duration_ms"] == 123.46

    def test_error_recording(self, tmp_path: Path) -> None:
        err = ValueError("something broke")
        path = write_audit_entry(
            audit_dir=tmp_path,
            task_id="t-003",
            agent_id="a",
            user_id="u",
            team_id="t",
            config_version=1,
            op_steps=[],
            report=None,
            error=err,
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["error"]["type"] == "ValueError"
        assert "something broke" in data["error"]["message"]
        assert data["report_checksum"] is None

    def test_filename_contains_task_id(self, tmp_path: Path) -> None:
        path = write_audit_entry(
            audit_dir=tmp_path,
            task_id="my-task",
            agent_id="a",
            user_id="u",
            team_id="t",
            config_version=1,
            op_steps=[],
            report={},
        )
        assert "my-task" in path.name
