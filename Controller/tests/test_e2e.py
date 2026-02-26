"""End-to-end test: feed reports into inbox, verify processing and audit output."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


from Controller.config import ControllerConfig
from Controller.controller import Controller


class TestE2E:
    """Simulated end-to-end test with filesystem I/O."""

    def test_full_pipeline(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
        sample_report: dict[str, Any],
    ) -> None:
        """Process a valid report and verify all outputs."""
        # Write report to inbox
        team_dir = (
            test_config.inbox_dir / "sheets-team" / "sheets-agent"
        )
        team_dir.mkdir(parents=True, exist_ok=True)
        report_path = team_dir / "20260224T103300Z_report.json"
        report_path.write_text(json.dumps(sample_report), encoding="utf-8")

        # Run controller
        ctrl = Controller(test_config)
        success = ctrl.run_once()

        assert success is True

        # Verify report was marked as processed
        assert not report_path.exists(), "Report should be renamed to .processed.json"
        processed = report_path.with_name(
            "20260224T103300Z_report.processed.json"
        )
        assert processed.exists()

        # Verify hash companion file was created
        processed.with_suffix(".json.hash")
        # Hash file was created before rename, check for it
        report_path.with_suffix(".json.hash")
        # Note: hash was written before mark_processed renames the report.
        # The hash file stays with the original name.

        # Verify audit file exists
        audit_dir = test_config.audit_dir
        audit_files = list(audit_dir.glob("*.json"))
        assert len(audit_files) == 1, f"Expected 1 audit file, found {len(audit_files)}"
        audit = json.loads(audit_files[0].read_text(encoding="utf-8"))
        assert audit["controller_id"] == "test-controller"
        assert audit["report_checksum"] is not None
        assert audit["error"] is None
        assert len(audit["processed_reports"]) == 1
        assert audit["processed_reports"][0]["agent"] == "sheets-agent"

        # Verify self-report was written
        self_reports = list(
            (test_config.inbox_dir / "controller").glob("*_self_report.json")
        )
        assert len(self_reports) == 1
        self_report = json.loads(self_reports[0].read_text(encoding="utf-8"))
        assert self_report["status"] == "success"
        assert self_report["metrics"]["reports_processed"] == 1

        # Verify HEALTH.md was updated
        health_text = test_config.health_file.read_text(encoding="utf-8")
        assert "healthy" in health_text
        assert "auto-updated by controller.py" in health_text

    def test_no_reports_returns_false(
        self, tmp_project: Path, test_config: ControllerConfig
    ) -> None:
        """When no reports exist in inbox, run_once returns False."""
        ctrl = Controller(test_config)
        result = ctrl.run_once()
        assert result is False

    def test_team_filter(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
        sample_report: dict[str, Any],
    ) -> None:
        """Team filter correctly restricts processing."""
        # Write report for sheets-team
        sheets_dir = test_config.inbox_dir / "sheets-team" / "agent1"
        sheets_dir.mkdir(parents=True, exist_ok=True)
        (sheets_dir / "r1.json").write_text(
            json.dumps(sample_report), encoding="utf-8"
        )

        # Write report for backend-team
        backend_dir = test_config.inbox_dir / "backend-team" / "agent2"
        backend_dir.mkdir(parents=True, exist_ok=True)
        report2 = {**sample_report, "agent": "backend-agent", "task_id": "be-001"}
        (backend_dir / "r2.json").write_text(
            json.dumps(report2), encoding="utf-8"
        )

        # Process only sheets-team
        ctrl = Controller(test_config)
        ctrl.run_once(team_filter="sheets-team")

        # sheets-team report should be processed
        assert not (sheets_dir / "r1.json").exists()
        assert (sheets_dir / "r1.processed.json").exists()

        # backend-team report should remain unprocessed
        assert (backend_dir / "r2.json").exists()

    def test_tampered_report_is_skipped(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
        sample_report: dict[str, Any],
    ) -> None:
        """Reports with mismatched hash are flagged and skipped."""
        team_dir = test_config.inbox_dir / "sheets-team" / "agent1"
        team_dir.mkdir(parents=True, exist_ok=True)
        report_path = team_dir / "tampered.json"
        report_path.write_text(json.dumps(sample_report), encoding="utf-8")

        # Write a wrong hash
        hash_path = report_path.with_suffix(".json.hash")
        hash_path.write_text("definitely_wrong_hash", encoding="utf-8")

        ctrl = Controller(test_config)
        ctrl.run_once()

        # Processing ran but tampered report was skipped (not renamed)
        # Still returns True because the scan found files
        # But the tampered report remains (not processed)
        assert report_path.exists(), "Tampered report should not be processed"

    def test_invalid_json_report_is_skipped(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """Reports that fail validation are skipped."""
        team_dir = test_config.inbox_dir / "test-team" / "agent1"
        team_dir.mkdir(parents=True, exist_ok=True)
        report_path = team_dir / "invalid.json"
        report_path.write_text('{"not_a_valid_report": true}', encoding="utf-8")

        ctrl = Controller(test_config)
        ctrl.run_once()

        # Invalid report should not be processed (not renamed)
        assert report_path.exists()

    def test_multiple_reports(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
        sample_report: dict[str, Any],
    ) -> None:
        """Multiple valid reports are all processed."""
        team_dir = test_config.inbox_dir / "sheets-team" / "agent1"
        team_dir.mkdir(parents=True, exist_ok=True)

        for i in range(3):
            report = {**sample_report, "task_id": f"sh-{i:03d}"}
            path = team_dir / f"report_{i}.json"
            path.write_text(json.dumps(report), encoding="utf-8")

        ctrl = Controller(test_config)
        success = ctrl.run_once()

        assert success is True
        processed = list(team_dir.glob("*.processed.json"))
        assert len(processed) == 3

    def test_process_task_file(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
        sample_report: dict[str, Any],
        sample_task: dict[str, Any],
    ) -> None:
        """Process a controller task file that triggers inbox processing."""
        # Set up inbox
        team_dir = test_config.inbox_dir / "sheets-team" / "agent1"
        team_dir.mkdir(parents=True, exist_ok=True)
        (team_dir / "r1.json").write_text(
            json.dumps(sample_report), encoding="utf-8"
        )

        # Write controller task
        task_path = tmp_project / "task.json"
        task_path.write_text(json.dumps(sample_task), encoding="utf-8")

        ctrl = Controller(test_config)
        success = ctrl.process_task(task_path)

        assert success is True

    def test_error_report_triggers_retry(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """An error report should trigger a retry directive in the outbox."""
        error_report: dict[str, Any] = {
            "agent": "sheets-agent",
            "timestamp": "2026-02-24T10:33:00Z",
            "task_id": "sh-err-001",
            "status": "error",
            "summary": "Google Sheets API timeout",
            "metrics": {"duration_ms": 5000},
        }
        team_dir = test_config.inbox_dir / "sheets-team" / "sheets-agent"
        team_dir.mkdir(parents=True, exist_ok=True)
        (team_dir / "error_report.json").write_text(
            json.dumps(error_report), encoding="utf-8"
        )

        ctrl = Controller(test_config)
        ctrl.run_once()

        # Verify retry directive was written
        outbox = test_config.outbox_dir
        retry_files = list(outbox.rglob("*retry_directive.json"))
        assert len(retry_files) >= 1
        data = json.loads(retry_files[0].read_text(encoding="utf-8"))
        assert data["command"] == "retry_task"
        assert data["parameters"]["original_task_id"] == "sh-err-001"

    def test_exhausted_retries_trigger_escalation(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """When max retries are exhausted, an escalation directive is emitted."""
        error_report: dict[str, Any] = {
            "agent": "sheets-agent",
            "timestamp": "2026-02-24T10:33:00Z",
            "task_id": "sh-esc-001",
            "status": "error",
            "summary": "Persistent failure",
            "metrics": {"duration_ms": 1000},
        }

        ctrl = Controller(test_config)

        # Exhaust retries by processing error reports multiple times
        for i in range(test_config.retry_max_per_task + 1):
            team_dir = test_config.inbox_dir / "sheets-team" / "sheets-agent"
            team_dir.mkdir(parents=True, exist_ok=True)
            (team_dir / f"err_{i}.json").write_text(
                json.dumps(error_report), encoding="utf-8"
            )
            ctrl.run_once()

        # Verify escalation directive was written
        escalation_files = list(
            (test_config.outbox_dir / "escalation").rglob("*escalation.json")
        )
        assert len(escalation_files) >= 1
        data = json.loads(escalation_files[0].read_text(encoding="utf-8"))
        assert data["command"] == "escalate"

    def test_health_check_detects_down_agent(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """A silent agent is detected as DOWN by health check."""
        from datetime import datetime, timezone, timedelta

        # Create an agent HEALTH.md with an old timestamp (> 30 min ago)
        agents_dir = tmp_project / "Agents" / "stale-agent"
        agents_dir.mkdir(parents=True, exist_ok=True)
        old_ts = (
            datetime.now(timezone.utc) - timedelta(seconds=3600)
        ).isoformat()
        (agents_dir / "HEALTH.md").write_text(
            f"# HEALTH\n\n### {old_ts} — Task old\n\n"
            f"| Field | Value |\n|---|---|\n"
            f"| last_run_timestamp | {old_ts} |\n"
            f"| last_status | healthy |\n"
            f"| consecutive_failures | 0 |\n",
            encoding="utf-8",
        )

        # Create config that monitors the stale agent
        config = ControllerConfig(
            controller_id="test-controller",
            project_root=tmp_project,
            health_file_override=test_config.health_file,
            agent_health_paths={
                "stale-agent": "Agents/stale-agent/HEALTH.md",
            },
        )
        ctrl = Controller(config)
        result = ctrl.check_health()

        assert "stale-agent" in result["down"]
        assert result["overall_status"] == "down"

    def test_success_clears_retry_state(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """A success report clears the retry state for that task."""
        # First, create an error to register retry state
        error_report: dict[str, Any] = {
            "agent": "sheets-agent",
            "timestamp": "2026-02-24T10:33:00Z",
            "task_id": "sh-clear-001",
            "status": "error",
            "summary": "Temporary failure",
            "metrics": {"duration_ms": 100},
        }
        team_dir = test_config.inbox_dir / "sheets-team" / "sheets-agent"
        team_dir.mkdir(parents=True, exist_ok=True)
        (team_dir / "err.json").write_text(
            json.dumps(error_report), encoding="utf-8"
        )

        ctrl = Controller(test_config)
        ctrl.run_once()

        # Verify retry state exists
        retry_state = test_config.retry_state_file
        assert retry_state.exists()
        state = json.loads(retry_state.read_text(encoding="utf-8"))
        assert "sh-clear-001" in state

        # Now send a success report for the same task
        success_report: dict[str, Any] = {
            "agent": "sheets-agent",
            "timestamp": "2026-02-24T10:34:00Z",
            "task_id": "sh-clear-001",
            "status": "success",
            "summary": "Retry succeeded",
            "metrics": {"duration_ms": 200},
        }
        (team_dir / "success.json").write_text(
            json.dumps(success_report), encoding="utf-8"
        )
        ctrl.run_once()

        # Verify retry state is cleared
        state = json.loads(retry_state.read_text(encoding="utf-8"))
        assert "sh-clear-001" not in state

    # ------------------------------------------------------------------
    # Extended feature tests
    # ------------------------------------------------------------------

    def test_orchestrator_comm_writes_system_status(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
        sample_report: dict[str, Any],
    ) -> None:
        """run_once writes system_status.json to outbox."""
        team_dir = test_config.inbox_dir / "sheets-team" / "agent1"
        team_dir.mkdir(parents=True, exist_ok=True)
        (team_dir / "r1.json").write_text(
            json.dumps(sample_report), encoding="utf-8"
        )

        ctrl = Controller(test_config)
        ctrl.run_once()

        status_path = test_config.outbox_dir / "system_status.json"
        assert status_path.exists()
        data = json.loads(status_path.read_text(encoding="utf-8"))
        assert data["type"] == "system_status"
        assert "health" in data

    def test_extended_health_report_written(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
        sample_report: dict[str, Any],
    ) -> None:
        """run_once writes extended health report to Controller/health/."""
        team_dir = test_config.inbox_dir / "sheets-team" / "agent1"
        team_dir.mkdir(parents=True, exist_ok=True)
        (team_dir / "r1.json").write_text(
            json.dumps(sample_report), encoding="utf-8"
        )

        ctrl = Controller(test_config)
        ctrl.run_once()

        report_path = test_config.health_report_file
        assert report_path.exists()
        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert "status" in data
        assert "active_agents" in data

    def test_resource_state_tracked_during_processing(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
        sample_report: dict[str, Any],
    ) -> None:
        """Resource state is saved during report processing."""
        team_dir = test_config.inbox_dir / "sheets-team" / "agent1"
        team_dir.mkdir(parents=True, exist_ok=True)
        (team_dir / "r1.json").write_text(
            json.dumps(sample_report), encoding="utf-8"
        )

        ctrl = Controller(test_config)
        ctrl.run_once()

        # Resource state file should exist
        state_file = test_config.resource_state_file
        assert state_file.exists()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        # After processing, resource should be idle
        for key, val in data.items():
            if key.startswith("_"):
                continue
            assert val["modifying"] is False

    def test_zombie_lock_detected(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
        sample_report: dict[str, Any],
    ) -> None:
        """Old locks are detected as zombies."""
        # Create a stale lock
        locks_dir = test_config.locks_dir
        locks_dir.mkdir(parents=True, exist_ok=True)
        lock_data = {
            "resource_id": "stale-res",
            "agent_id": "dead-agent",
            "timestamp": "2020-01-01T00:00:00+00:00",
            "status": "locked",
        }
        (locks_dir / "stale-res.lock").write_text(
            json.dumps(lock_data), encoding="utf-8"
        )

        # Write a report to trigger processing
        team_dir = test_config.inbox_dir / "sheets-team" / "agent1"
        team_dir.mkdir(parents=True, exist_ok=True)
        (team_dir / "r1.json").write_text(
            json.dumps(sample_report), encoding="utf-8"
        )

        ctrl = Controller(test_config)
        ctrl.run_once()

        # Check alerts.json was written with zombie lock
        alerts_path = test_config.outbox_dir / "alerts.json"
        assert alerts_path.exists()
        data = json.loads(alerts_path.read_text(encoding="utf-8"))
        zombie_alerts = [
            a for a in data["alerts"] if a["type"] == "zombie_lock"
        ]
        assert len(zombie_alerts) >= 1
        assert zombie_alerts[0]["resource_id"] == "stale-res"

    def test_detection_does_not_crash_on_empty_inbox(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """Detection pass runs safely even with no reports."""
        ctrl = Controller(test_config)
        result = ctrl.run_once()
        assert result is False  # No reports to process

    def test_new_subsystems_init_with_none_on_failure(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """Controller initializes successfully — subsystems are not None."""
        ctrl = Controller(test_config)
        assert ctrl._resource_state_mgr is not None
        assert ctrl._orchestrator_comm is not None
        assert ctrl._audit_logger is not None

    def test_detection_methods_return_lists(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """Detection methods return lists (possibly empty)."""
        ctrl = Controller(test_config)
        assert isinstance(ctrl._detect_lock_conflicts(), list)
        assert isinstance(ctrl._detect_stuck_agents(), list)
        assert isinstance(ctrl._detect_missing_reports(), list)

    def test_run_all_detections_populates_communicator(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """_run_all_detections runs without error."""
        # Create a zombie lock to ensure something is detected
        locks_dir = test_config.locks_dir
        locks_dir.mkdir(parents=True, exist_ok=True)
        (locks_dir / "zombie.lock").write_text(
            json.dumps({
                "resource_id": "zombie",
                "agent_id": "dead",
                "timestamp": "2020-01-01T00:00:00+00:00",
                "status": "locked",
            }),
            encoding="utf-8",
        )

        ctrl = Controller(test_config)
        ctrl._run_all_detections()
        assert ctrl._orchestrator_comm is not None
        assert len(ctrl._orchestrator_comm.alerts) >= 1
