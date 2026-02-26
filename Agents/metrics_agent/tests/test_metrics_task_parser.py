"""Tests for metrics_task_parser."""
from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from Agents.metrics_agent.metrics_task_parser import (
    parse_task,
    parse_task_file,
    validate_task,
)
from Agents.metrics_agent.tests.conftest import SAMPLE_TASK


class TestValidTasks:
    """Verify acceptance of correctly formed tasks."""

    def test_collect_team_metrics(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        result = validate_task(task)
        assert result.ok
        assert result.task is not None

    def test_collect_agent_metrics(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "collect_agent_metrics"
        task["metrics_request"]["target_agent_id"] = "sheets-agent-01"
        result = validate_task(task)
        assert result.ok

    def test_compute_cost(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "compute_cost"
        result = validate_task(task)
        assert result.ok

    def test_check_slo(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "check_slo"
        task["metrics_request"]["slo_config"] = {
            "latency_p95_ms": 500,
            "error_rate_pct": 5.0,
            "throughput_min": 1.0,
        }
        result = validate_task(task)
        assert result.ok

    def test_generate_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "generate_report"
        result = validate_task(task)
        assert result.ok

    def test_all_metadata_sources(self) -> None:
        """All valid source values should be accepted."""
        for source in ["system", "scheduler", "api", "manual"]:
            task = copy.deepcopy(SAMPLE_TASK)
            task["metadata"]["source"] = source
            result = validate_task(task)
            assert result.ok, f"source '{source}' should be valid"


class TestInvalidSchema:
    """Verify rejection of malformed tasks."""

    def test_missing_task_id(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        del task["task_id"]
        result = validate_task(task)
        assert not result.ok
        assert any("task_id" in e for e in result.errors)

    def test_missing_metrics_request(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        del task["metrics_request"]
        result = validate_task(task)
        assert not result.ok

    def test_bad_operation(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "hack_metrics"
        result = validate_task(task)
        assert not result.ok

    def test_additional_properties(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["extra_field"] = "not_allowed"
        result = validate_task(task)
        assert not result.ok

    def test_bad_metadata_source(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metadata"]["source"] = "web-ui"
        result = validate_task(task)
        assert not result.ok

    def test_missing_metadata(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        del task["metadata"]
        result = validate_task(task)
        assert not result.ok


class TestSemanticViolations:
    """Verify business-rule checks beyond JSON Schema."""

    def test_collect_agent_metrics_without_target(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "collect_agent_metrics"
        # No target_agent_id
        result = validate_task(task)
        assert not result.ok
        assert any("target_agent_id" in e for e in result.errors)

    def test_collect_team_metrics_without_target(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "collect_team_metrics"
        del task["metrics_request"]["target_team_id"]
        result = validate_task(task)
        assert not result.ok
        assert any("target_team_id" in e for e in result.errors)

    def test_check_slo_without_config(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "check_slo"
        # No slo_config
        result = validate_task(task)
        assert not result.ok
        assert any("slo_config" in e for e in result.errors)


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
        assert result.task["task_id"] == "metrics-001"
