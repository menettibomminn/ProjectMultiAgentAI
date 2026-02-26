"""Tests for metrics_report_generator."""
from __future__ import annotations

import copy
import json
from pathlib import Path


from Agents.metrics_agent.metrics_report_generator import (
    MODEL_PRICING,
    generate_error_report,
    generate_report,
    write_report,
)
from Agents.metrics_agent.tests.conftest import SAMPLE_TASK


class TestGenerateReport:
    """Verify report generation from valid tasks."""

    def test_collect_team_metrics_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="metrics-test")
        assert report["status"] == "success"
        assert report["task_id"] == "metrics-001"
        assert len(report["proposed_changes"]) == 1
        change = report["proposed_changes"][0]
        assert change["operation"] == "collect_team_metrics"
        assert change["estimated_risk"] == "low"
        assert change["confidence"] == 0.95
        # Check aggregated metrics structure
        agg = change["aggregated_metrics"]
        assert "tasks_completed" in agg
        assert "tasks_failed" in agg
        assert "avg_duration_ms" in agg
        assert "p95_duration_ms" in agg
        assert "tokens_in_total" in agg
        assert "tokens_out_total" in agg
        assert "cost_eur_total" in agg
        assert "error_rate" in agg
        assert "throughput" in agg
        assert "slo_compliance" in agg

    def test_compute_cost_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "compute_cost"
        report = generate_report(task, agent_id="metrics-test")
        change = report["proposed_changes"][0]
        assert change["operation"] == "compute_cost"
        assert change["confidence"] == 0.99
        # Verify cost estimates for all models
        estimates = change["cost_estimate"]
        assert len(estimates) == len(MODEL_PRICING)
        for est in estimates:
            assert "model" in est
            assert "tokens_in" in est
            assert "tokens_out" in est
            assert "cost_eur" in est
            assert est["cost_eur"] > 0

    def test_compute_cost_pricing_accuracy(self) -> None:
        """Verify cost calculations match MODEL_PRICING."""
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "compute_cost"
        report = generate_report(task, agent_id="metrics-test")
        estimates = report["proposed_changes"][0]["cost_estimate"]
        for est in estimates:
            model = est["model"]
            pricing = MODEL_PRICING[model]
            expected = (
                (est["tokens_in"] / 1_000_000) * pricing["input"]
                + (est["tokens_out"] / 1_000_000) * pricing["output"]
            )
            assert abs(est["cost_eur"] - round(expected, 6)) < 1e-9

    def test_check_slo_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "check_slo"
        task["metrics_request"]["slo_config"] = {
            "latency_p95_ms": 500,
            "error_rate_pct": 5.0,
            "throughput_min": 1.0,
        }
        report = generate_report(task, agent_id="metrics-test")
        change = report["proposed_changes"][0]
        assert change["operation"] == "check_slo"
        assert change["confidence"] == 0.90
        assert "slo_result" in change
        slo = change["slo_result"]
        assert "latency_p95_ok" in slo
        assert "error_rate_ok" in slo
        assert "throughput_ok" in slo
        assert "overall_compliant" in slo
        # Check SLO risk warning
        assert any("SLO" in r for r in report["risks"])

    def test_collect_agent_metrics_report(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        task["metrics_request"]["operation"] = "collect_agent_metrics"
        task["metrics_request"]["target_agent_id"] = "sheets-agent-01"
        report = generate_report(task, agent_id="metrics-test")
        change = report["proposed_changes"][0]
        assert change["operation"] == "collect_agent_metrics"
        assert "agent_metrics" in change

    def test_validation_entries(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="metrics-test")
        assert len(report["validation"]) >= 1
        assert all(v["ok"] for v in report["validation"])

    def test_timestamps_present(self) -> None:
        task = copy.deepcopy(SAMPLE_TASK)
        report = generate_report(task, agent_id="metrics-test")
        assert "timestamp_utc" in report
        assert "timestamp_local" in report


class TestErrorReport:
    """Verify error report generation."""

    def test_error_report_format(self) -> None:
        report = generate_error_report(
            task_id="metrics-err-01",
            agent_id="metrics-test",
            errors=["Metrics collection failed"],
        )
        assert report["status"] == "error"
        assert report["proposed_changes"] == []
        assert "Metrics collection failed" in report["errors"]

    def test_error_report_timestamps(self) -> None:
        report = generate_error_report(
            task_id="metrics-err-02",
            agent_id="metrics-test",
            errors=["Source unreachable"],
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
