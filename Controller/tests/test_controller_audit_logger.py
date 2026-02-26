"""Tests for controller_audit_logger module."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from Controller.controller_audit_logger import (
    compute_checksum,
    verify_report_checksum,
    write_audit_entry,
    write_hash_file,
)


class TestChecksum:
    """Tests for checksum computation."""

    def test_deterministic(self) -> None:
        data = {"key": "value", "num": 42}
        assert compute_checksum(data) == compute_checksum(data)

    def test_different_data_different_hash(self) -> None:
        assert compute_checksum({"a": 1}) != compute_checksum({"a": 2})

    def test_key_order_does_not_matter(self) -> None:
        # sort_keys=True ensures canonical form
        d1 = {"b": 2, "a": 1}
        d2 = {"a": 1, "b": 2}
        assert compute_checksum(d1) == compute_checksum(d2)

    def test_sha256_length(self) -> None:
        h = compute_checksum({"test": True})
        assert len(h) == 64


class TestVerifyReportChecksum:
    """Tests for report integrity verification."""

    def test_valid_report_no_hash_file(self, tmp_path: Path) -> None:
        report = {"agent": "test", "task_id": "t1"}
        path = tmp_path / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        is_valid, checksum = verify_report_checksum(path)
        assert is_valid is True
        assert len(checksum) == 64

    def test_valid_report_with_matching_hash(self, tmp_path: Path) -> None:
        report = {"agent": "test", "task_id": "t1"}
        path = tmp_path / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        expected_hash = compute_checksum(report)
        hash_path = path.with_suffix(".json.hash")
        hash_path.write_text(expected_hash, encoding="utf-8")
        is_valid, checksum = verify_report_checksum(path)
        assert is_valid is True
        assert checksum == expected_hash

    def test_tampered_report(self, tmp_path: Path) -> None:
        path = tmp_path / "report.json"
        path.write_text(json.dumps({"agent": "test"}), encoding="utf-8")
        hash_path = path.with_suffix(".json.hash")
        hash_path.write_text("wrong_hash_value", encoding="utf-8")
        is_valid, checksum = verify_report_checksum(path)
        assert is_valid is False

    def test_unreadable_file(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.json"
        is_valid, checksum = verify_report_checksum(path)
        assert is_valid is False
        assert "read_error" in checksum


class TestWriteHashFile:
    """Tests for hash companion file writing."""

    def test_write_hash_file(self, tmp_path: Path) -> None:
        report_path = tmp_path / "report.json"
        report_path.write_text("{}", encoding="utf-8")
        hash_path = write_hash_file(report_path, "abc123")
        assert hash_path.exists()
        assert hash_path.read_text(encoding="utf-8").strip() == "abc123"


class TestWriteAuditEntry:
    """Tests for audit entry writing."""

    def test_basic_audit_entry(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "audit"
        report = {"task_id": "t1", "status": "success"}
        path = write_audit_entry(
            audit_dir=audit_dir,
            task_id="t1",
            controller_id="ctrl-01",
            op_steps=[{"step": "scan_inbox", "ts": "2026-02-24T10:00:00Z"}],
            processed_reports=[{"file": "r1.json", "status": "success"}],
            directives_emitted=[],
            report=report,
            duration_ms=123.45,
        )
        assert path.exists()
        entry = json.loads(path.read_text(encoding="utf-8"))
        assert entry["task_id"] == "t1"
        assert entry["controller_id"] == "ctrl-01"
        assert entry["report_checksum"] is not None
        assert entry["error"] is None
        assert entry["runtime_metrics"]["duration_ms"] == 123.45

    def test_audit_with_error(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "audit"
        error = ValueError("test error")
        path = write_audit_entry(
            audit_dir=audit_dir,
            task_id="t-err",
            controller_id="ctrl-01",
            op_steps=[],
            processed_reports=[],
            directives_emitted=[],
            report=None,
            error=error,
        )
        entry = json.loads(path.read_text(encoding="utf-8"))
        assert entry["error"] is not None
        assert entry["error"]["type"] == "ValueError"
        assert "test error" in entry["error"]["message"]
        assert entry["report_checksum"] is None

    def test_audit_dir_created(self, tmp_path: Path) -> None:
        audit_dir = tmp_path / "deep" / "nested" / "audit"
        write_audit_entry(
            audit_dir=audit_dir,
            task_id="t2",
            controller_id="ctrl-01",
            op_steps=[],
            processed_reports=[],
            directives_emitted=[],
            report={"ok": True},
        )
        assert audit_dir.exists()
