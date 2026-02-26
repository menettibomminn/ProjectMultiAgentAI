"""Tests for metrics_audit_logger."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from Agents.metrics_agent.metrics_audit_logger import (
    compute_checksum,
    write_audit_entry,
)


class TestComputeChecksum:
    """Verify SHA-256 checksum behaviour."""

    def test_deterministic(self) -> None:
        data = {"a": 1, "b": 2}
        assert compute_checksum(data) == compute_checksum(data)

    def test_order_independent(self) -> None:
        """Keys are sorted internally so order should not matter."""
        a = compute_checksum({"x": 1, "y": 2})
        b = compute_checksum({"y": 2, "x": 1})
        assert a == b

    def test_hex_format(self) -> None:
        digest = compute_checksum({"test": True})
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)


class TestWriteAuditEntry:
    """Verify audit file creation."""

    def _base_kwargs(self, audit_dir: Path) -> dict[str, Any]:
        return {
            "audit_dir": audit_dir,
            "task_id": "metrics-001",
            "agent_id": "metrics-test",
            "user_id": "system",
            "team_id": "platform-team",
            "config_version": 1,
            "op_steps": [{"step": "test", "ts": "2026-01-01T00:00:00Z"}],
            "report": {"status": "success", "task_id": "metrics-001"},
        }

    def test_creates_file(self, tmp_path: Path) -> None:
        path = write_audit_entry(**self._base_kwargs(tmp_path))
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["task_id"] == "metrics-001"
        assert data["report_checksum"] is not None

    def test_runtime_metrics(self, tmp_path: Path) -> None:
        kwargs = self._base_kwargs(tmp_path)
        kwargs["duration_ms"] = 123.45
        path = write_audit_entry(**kwargs)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["runtime_metrics"]["duration_ms"] == 123.45

    def test_error_recording(self, tmp_path: Path) -> None:
        kwargs = self._base_kwargs(tmp_path)
        kwargs["report"] = None
        kwargs["error"] = ValueError("test error")
        path = write_audit_entry(**kwargs)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["error"]["type"] == "ValueError"
        assert "test error" in data["error"]["message"]

    def test_no_sensitive_data_in_audit(self, tmp_path: Path) -> None:
        """Verify no sensitive data leaks into audit."""
        kwargs = self._base_kwargs(tmp_path)
        path = write_audit_entry(**kwargs)
        text = path.read_text(encoding="utf-8")
        assert "Bearer" not in text
        assert "ya29." not in text

    def test_filename_format(self, tmp_path: Path) -> None:
        path = write_audit_entry(**self._base_kwargs(tmp_path))
        assert path.name.endswith("_metrics-001.json")
        assert "T" in path.stem  # timestamp format
