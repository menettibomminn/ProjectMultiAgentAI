"""Tests for HashManager."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from Orchestrator.hash_manager import HashManager


class TestComputeHash:
    def test_deterministic(self, tmp_path: Path) -> None:
        hm = HashManager(tmp_path / "audit.log")
        h1 = hm.compute_hash("hello world")
        h2 = hm.compute_hash("hello world")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_differs_for_different_content(self, tmp_path: Path) -> None:
        hm = HashManager(tmp_path / "audit.log")
        h1 = hm.compute_hash("content A")
        h2 = hm.compute_hash("content B")
        assert h1 != h2

    def test_known_sha256(self, tmp_path: Path) -> None:
        hm = HashManager(tmp_path / "audit.log")
        content = "test content"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert hm.compute_hash(content) == expected

    def test_empty_string(self, tmp_path: Path) -> None:
        hm = HashManager(tmp_path / "audit.log")
        h = hm.compute_hash("")
        assert len(h) == 64

    def test_unicode_content(self, tmp_path: Path) -> None:
        hm = HashManager(tmp_path / "audit.log")
        h = hm.compute_hash("stato corrente del sistema — àèìòù")
        assert len(h) == 64


class TestLogHash:
    def test_creates_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "ops" / "logs" / "audit.log"
        hm = HashManager(log_path)
        hm.log_hash("abc123", "update", "req-001")
        assert log_path.exists()

    def test_jsonl_format(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.log"
        hm = HashManager(log_path)
        hm.log_hash("abc123", "update", "req-001")

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["hash"] == "abc123"
        assert entry["operation"] == "update"
        assert entry["request_id"] == "req-001"
        assert entry["status"] == "ok"
        assert "timestamp" in entry
        assert "error" not in entry

    def test_append_only(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.log"
        hm = HashManager(log_path)
        hm.log_hash("hash1", "op1", "req-1")
        hm.log_hash("hash2", "op2", "req-2")
        hm.log_hash("hash3", "op3", "req-3")

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3
        assert json.loads(lines[0])["hash"] == "hash1"
        assert json.loads(lines[1])["hash"] == "hash2"
        assert json.loads(lines[2])["hash"] == "hash3"

    def test_with_error(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.log"
        hm = HashManager(log_path)
        hm.log_hash(
            "", "update", "req-err",
            status="error", error="validation failed"
        )

        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["status"] == "error"
        assert entry["error"] == "validation failed"
        assert entry["hash"] == ""

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        log_path = tmp_path / "deep" / "nested" / "audit.log"
        hm = HashManager(log_path)
        hm.log_hash("abc", "test", "req-001")
        assert log_path.exists()

    def test_default_status_ok(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.log"
        hm = HashManager(log_path)
        hm.log_hash("h", "op", "r")
        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["status"] == "ok"
