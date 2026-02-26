"""Tests for controller_report_generator module."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from Controller.controller_report_generator import (
    generate_directive,
    generate_error_report,
    generate_processing_report,
    write_directive,
    write_report,
)


class TestDirectiveGeneration:
    """Tests for directive generation."""

    def test_basic_directive(self) -> None:
        directive = generate_directive(
            directive_id="dir-001",
            target_agent="sheets-agent",
            command="write_range",
            parameters={"sheet_id": "abc123", "range": "A1:B2"},
            controller_id="ctrl-01",
        )
        assert directive["directive_id"] == "dir-001"
        assert directive["target_agent"] == "sheets-agent"
        assert directive["command"] == "write_range"
        assert directive["issued_by"] == "ctrl-01"
        assert "signature" in directive
        assert len(directive["signature"]) == 64  # SHA-256 hex

    def test_directive_signature_is_deterministic(self) -> None:
        kwargs = dict(
            directive_id="dir-001",
            target_agent="sheets-agent",
            command="write_range",
            parameters={"key": "value"},
            controller_id="ctrl-01",
        )
        d1 = generate_directive(**kwargs)
        d2 = generate_directive(**kwargs)
        assert d1["signature"] == d2["signature"]

    def test_directive_signature_changes_with_params(self) -> None:
        common = dict(
            directive_id="dir-001",
            target_agent="sheets-agent",
            command="write_range",
            controller_id="ctrl-01",
        )
        d1 = generate_directive(parameters={"a": 1}, **common)
        d2 = generate_directive(parameters={"a": 2}, **common)
        assert d1["signature"] != d2["signature"]

    def test_write_directive_creates_file(self, tmp_path: Path) -> None:
        directive = generate_directive(
            directive_id="dir-write-test",
            target_agent="test-agent",
            command="noop",
            parameters={},
            controller_id="ctrl-01",
        )
        path = tmp_path / "outbox" / "test" / "directive.json"
        write_directive(directive, path)
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["directive_id"] == "dir-write-test"


class TestProcessingReport:
    """Tests for processing report generation."""

    def test_success_report(self) -> None:
        report = generate_processing_report(
            controller_id="ctrl-01",
            task_id="ctrl-test-001",
            processed_reports=[{"file": "r1.json", "status": "success"}],
            directives_emitted=["dir-001"],
            state_changes=[{"type": "report_processed"}],
        )
        assert report["status"] == "success"
        assert report["task_id"] == "ctrl-test-001"
        assert report["metrics"]["reports_processed"] == 1
        assert report["metrics"]["directives_emitted"] == 1
        assert len(report["errors"]) == 0

    def test_report_with_errors(self) -> None:
        report = generate_processing_report(
            controller_id="ctrl-01",
            task_id="ctrl-test-002",
            processed_reports=[],
            directives_emitted=[],
            state_changes=[],
            errors=["something went wrong"],
        )
        assert report["status"] == "error"
        assert len(report["errors"]) == 1

    def test_error_report(self) -> None:
        report = generate_error_report(
            task_id="ctrl-err",
            controller_id="ctrl-01",
            errors=["Internal failure"],
        )
        assert report["status"] == "error"
        assert "Internal failure" in report["errors"]
        assert report["metrics"]["reports_processed"] == 0

    def test_write_report_creates_file(self, tmp_path: Path) -> None:
        report = generate_processing_report(
            controller_id="ctrl-01",
            task_id="ctrl-write-test",
            processed_reports=[],
            directives_emitted=[],
            state_changes=[],
        )
        path = tmp_path / "self_report.json"
        write_report(report, path)
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["task_id"] == "ctrl-write-test"
