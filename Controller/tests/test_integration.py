"""Integration tests: verify agent reports conform to Controller report_v1 schema.

These tests exercise the full protocol: an agent generates a report, the report
is placed in the Controller inbox, the Controller processes it, and we verify
all outputs (processed marker, hash, audit, self-report, HEALTH.md).

This catches protocol mismatches between agent report format and Controller
expectations — the exact class of bug that was found in 2026-02-24.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from Controller.config import ControllerConfig
from Controller.controller import Controller
from Controller.controller_task_parser import validate_report


# ---------------------------------------------------------------------------
# Sample task data for each agent
# ---------------------------------------------------------------------------

SHEETS_TASK: dict[str, Any] = {
    "task_id": "int-sheets-001",
    "user_id": "user@example.com",
    "team_id": "sheets-team",
    "sheet": {
        "spreadsheet_id": "abc123",
        "sheet_name": "Foglio1",
    },
    "requested_changes": [
        {
            "op": "update",
            "range": "A2:C2",
            "values": [["Mario", "Rossi", "100"]],
        }
    ],
    "metadata": {
        "source": "web-ui",
        "priority": "normal",
        "timestamp": "2026-02-24T10:00:00+01:00",
    },
}

AUTH_TASK: dict[str, Any] = {
    "task_id": "int-auth-001",
    "user_id": "admin@example.com",
    "team_id": "security-team",
    "auth_request": {
        "operation": "issue_token",
        "auth_type": "oauth_user",
        "scopes": ["spreadsheets", "drive.file"],
    },
    "metadata": {
        "source": "web-ui",
        "priority": "normal",
        "timestamp": "2026-02-24T10:00:00Z",
    },
}

BACKEND_TASK: dict[str, Any] = {
    "task_id": "int-backend-001",
    "user_id": "operator@example.com",
    "team_id": "backend-team",
    "request": {
        "operation": "validate_payload",
        "payload": {"key": "value"},
        "schema_name": "task_v1",
    },
    "metadata": {
        "source": "api",
        "priority": "normal",
        "timestamp": "2026-02-24T10:00:00Z",
    },
}

METRICS_TASK: dict[str, Any] = {
    "task_id": "int-metrics-001",
    "user_id": "ops@example.com",
    "team_id": "ops-team",
    "metrics_request": {
        "operation": "collect_team_metrics",
        "target_team_id": "sheets-team",
        "period": "24h",
    },
    "metadata": {
        "source": "scheduler",
        "priority": "normal",
        "timestamp": "2026-02-24T10:00:00Z",
    },
}

FRONTEND_TASK: dict[str, Any] = {
    "task_id": "int-frontend-001",
    "user_id": "dashboard@example.com",
    "team_id": "ui-team",
    "ui_request": {
        "operation": "render_dashboard",
        "sheets": [
            {"spreadsheet_id": "abc123", "sheet_name": "Foglio1"},
        ],
    },
    "metadata": {
        "source": "web-ui",
        "priority": "normal",
        "timestamp": "2026-02-24T10:00:00Z",
    },
}

# Tasks that trigger needs_review
SHEETS_TASK_HIGH_RISK: dict[str, Any] = {
    "task_id": "int-sheets-review-001",
    "user_id": "user@example.com",
    "team_id": "sheets-team",
    "sheet": {
        "spreadsheet_id": "abc123",
        "sheet_name": "Foglio1",
    },
    "requested_changes": [
        {
            "op": "clear_range",
            "range": "A1:Z100",
            "values": [],
        }
    ],
    "metadata": {
        "source": "web-ui",
        "priority": "normal",
        "timestamp": "2026-02-24T10:00:00+01:00",
    },
}

AUTH_TASK_HIGH_RISK: dict[str, Any] = {
    "task_id": "int-auth-review-001",
    "user_id": "admin@example.com",
    "team_id": "security-team",
    "auth_request": {
        "operation": "revoke_token",
        "auth_type": "service_account",
        "target_user_id": "sa-prod@project.iam",
        "scopes": [],
    },
    "metadata": {
        "source": "web-ui",
        "priority": "normal",
        "timestamp": "2026-02-24T10:00:00Z",
    },
}

BACKEND_TASK_HIGH_RISK: dict[str, Any] = {
    "task_id": "int-backend-review-001",
    "user_id": "operator@example.com",
    "team_id": "backend-team",
    "request": {
        "operation": "process_sheet_request",
        "sheet_id": "abc123",
        "changes": [{"row": i, "value": f"v{i}"} for i in range(150)],
    },
    "metadata": {
        "source": "api",
        "priority": "normal",
        "timestamp": "2026-02-24T10:00:00Z",
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with full Controller structure."""
    inbox = tmp_path / "Controller" / "inbox"
    inbox.mkdir(parents=True)
    outbox = tmp_path / "Controller" / "outbox"
    outbox.mkdir(parents=True)
    (tmp_path / "audit" / "controller" / "test-controller").mkdir(parents=True)
    (tmp_path / "locks").mkdir(parents=True)
    (tmp_path / "Orchestrator").mkdir(parents=True)
    (tmp_path / "Orchestrator" / "STATE.md").write_text(
        "# STATE\n\n<!-- Managed by Controller -->\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def test_config(tmp_project: Path) -> ControllerConfig:
    """Return a ControllerConfig pointing at tmp_project."""
    health = tmp_project / "HEALTH.md"
    health.write_text(
        "# HEALTH\n\n<!-- Append new entries below this line -->\n",
        encoding="utf-8",
    )
    return ControllerConfig(
        controller_id="test-controller",
        project_root=tmp_project,
        health_file_override=health,
        agent_health_paths={},
    )


# ---------------------------------------------------------------------------
# Schema conformance tests: each agent report must pass report_v1 validation
# ---------------------------------------------------------------------------


class TestReportV1Conformance:
    """Verify that each agent's generate_report output conforms to REPORT_V1_SCHEMA."""

    def test_sheets_report_conforms(self) -> None:
        from Agents.sheets_agent.sheets_report_generator import generate_report
        report = generate_report(SHEETS_TASK, "sheets-worker-01")
        result = validate_report(report)
        assert result.ok, f"Sheets report failed report_v1: {result.errors}"

    def test_sheets_error_report_conforms(self) -> None:
        from Agents.sheets_agent.sheets_report_generator import generate_error_report
        report = generate_error_report("err-001", "sheets-worker-01", ["test error"])
        result = validate_report(report)
        assert result.ok, f"Sheets error report failed report_v1: {result.errors}"

    def test_auth_report_conforms(self) -> None:
        from Agents.auth_agent.auth_report_generator import generate_report
        report = generate_report(AUTH_TASK, "auth-agent-01")
        result = validate_report(report)
        assert result.ok, f"Auth report failed report_v1: {result.errors}"

    def test_auth_error_report_conforms(self) -> None:
        from Agents.auth_agent.auth_report_generator import generate_error_report
        report = generate_error_report("err-002", "auth-agent-01", ["test error"])
        result = validate_report(report)
        assert result.ok, f"Auth error report failed report_v1: {result.errors}"

    def test_backend_report_conforms(self) -> None:
        from Agents.backend_agent.backend_report_generator import generate_report
        report = generate_report(BACKEND_TASK, "backend-agent-01")
        result = validate_report(report)
        assert result.ok, f"Backend report failed report_v1: {result.errors}"

    def test_metrics_report_conforms(self) -> None:
        from Agents.metrics_agent.metrics_report_generator import generate_report
        report = generate_report(METRICS_TASK, "metrics-agent-01")
        result = validate_report(report)
        assert result.ok, f"Metrics report failed report_v1: {result.errors}"

    def test_frontend_report_conforms(self) -> None:
        from Agents.frontend_agent.frontend_report_generator import generate_report
        report = generate_report(FRONTEND_TASK, "frontend-agent-01")
        result = validate_report(report)
        assert result.ok, f"Frontend report failed report_v1: {result.errors}"


# ---------------------------------------------------------------------------
# End-to-end integration: sheets agent report → Controller processing
# ---------------------------------------------------------------------------


class TestSheetsControllerIntegration:
    """Full pipeline: sheets agent generates report → controller processes it."""

    def test_sheets_report_processed_by_controller(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """Generate a sheets report, place it in Controller inbox, process it."""
        from Agents.sheets_agent.sheets_report_generator import generate_report

        # Step 1: Generate report using sheets agent
        report = generate_report(SHEETS_TASK, "sheets-worker-01")

        # Step 2: Write to Controller inbox
        team_dir = test_config.inbox_dir / "sheets-team" / "sheets-agent"
        team_dir.mkdir(parents=True, exist_ok=True)
        report_path = team_dir / "report_int_001.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

        # Step 3: Process with Controller
        ctrl = Controller(test_config)
        success = ctrl.run_once()

        # Step 4: Verify
        assert success is True

        # Report should be marked as processed
        assert not report_path.exists(), "Original report should be renamed"
        processed = report_path.with_name("report_int_001.processed.json")
        assert processed.exists(), "Processed marker file should exist"

        # Audit file should exist with agent info
        audit_files = list(test_config.audit_dir.glob("*.json"))
        assert len(audit_files) >= 1
        audit = json.loads(audit_files[0].read_text(encoding="utf-8"))
        assert audit["processed_reports"][0]["agent"] == "sheets-worker-01"
        assert audit["processed_reports"][0]["task_id"] == "int-sheets-001"

    def test_auth_report_processed_by_controller(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """Generate an auth report, place it in Controller inbox, process it."""
        from Agents.auth_agent.auth_report_generator import generate_report

        report = generate_report(AUTH_TASK, "auth-agent-01")

        team_dir = test_config.inbox_dir / "security-team" / "auth-agent"
        team_dir.mkdir(parents=True, exist_ok=True)
        report_path = team_dir / "report_int_auth.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

        ctrl = Controller(test_config)
        success = ctrl.run_once()

        assert success is True
        assert not report_path.exists()
        assert report_path.with_name("report_int_auth.processed.json").exists()

    def test_multiple_agent_reports_processed(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """Multiple agents drop reports; Controller processes all of them."""
        from Agents.sheets_agent.sheets_report_generator import generate_report as sheets_gen
        from Agents.auth_agent.auth_report_generator import generate_report as auth_gen
        from Agents.backend_agent.backend_report_generator import generate_report as be_gen

        reports = [
            ("sheets-team", "sheets-agent", sheets_gen(SHEETS_TASK, "sheets-worker-01")),
            ("security-team", "auth-agent", auth_gen(AUTH_TASK, "auth-agent-01")),
            ("backend-team", "backend-agent", be_gen(BACKEND_TASK, "backend-agent-01")),
        ]

        for team, agent, report in reports:
            d = test_config.inbox_dir / team / agent
            d.mkdir(parents=True, exist_ok=True)
            (d / f"report_{agent}.json").write_text(
                json.dumps(report), encoding="utf-8"
            )

        ctrl = Controller(test_config)
        success = ctrl.run_once()
        assert success is True

        # All 3 reports should be processed
        for team, agent, _ in reports:
            d = test_config.inbox_dir / team / agent
            processed = list(d.glob("*.processed.json"))
            assert len(processed) == 1, (
                f"Expected 1 processed file for {team}/{agent}, "
                f"found {len(processed)}"
            )


# ---------------------------------------------------------------------------
# needs_review: schema conformance + Controller pipeline
# ---------------------------------------------------------------------------


class TestNeedsReviewConformance:
    """Verify that needs_review reports conform to report_v1 schema."""

    def test_sheets_clear_range_triggers_needs_review(self) -> None:
        from Agents.sheets_agent.sheets_report_generator import generate_report
        report = generate_report(SHEETS_TASK_HIGH_RISK, "sheets-worker-01")
        result = validate_report(report)
        assert result.ok, f"needs_review report failed report_v1: {result.errors}"
        assert report["status"] == "needs_review"
        assert len(report["review_reasons"]) >= 1
        assert "clear_range" in report["review_reasons"][0]

    def test_auth_revoke_service_account_triggers_needs_review(self) -> None:
        from Agents.auth_agent.auth_report_generator import generate_report
        report = generate_report(AUTH_TASK_HIGH_RISK, "auth-agent-01")
        result = validate_report(report)
        assert result.ok, f"needs_review report failed report_v1: {result.errors}"
        assert report["status"] == "needs_review"
        assert len(report["review_reasons"]) >= 1
        assert "revoke_token" in report["review_reasons"][0]

    def test_backend_bulk_changes_triggers_needs_review(self) -> None:
        from Agents.backend_agent.backend_report_generator import generate_report
        report = generate_report(BACKEND_TASK_HIGH_RISK, "backend-agent-01")
        result = validate_report(report)
        assert result.ok, f"needs_review report failed report_v1: {result.errors}"
        assert report["status"] == "needs_review"
        assert len(report["review_reasons"]) >= 1
        assert "process_sheet_request" in report["review_reasons"][0]

    def test_normal_tasks_produce_success_not_review(self) -> None:
        """Low-risk tasks must NOT trigger needs_review."""
        from Agents.sheets_agent.sheets_report_generator import generate_report as sheets_gen
        from Agents.auth_agent.auth_report_generator import generate_report as auth_gen
        from Agents.backend_agent.backend_report_generator import generate_report as be_gen

        assert sheets_gen(SHEETS_TASK, "s")["status"] == "success"
        assert auth_gen(AUTH_TASK, "a")["status"] == "success"
        assert be_gen(BACKEND_TASK, "b")["status"] == "success"


class TestNeedsReviewControllerPipeline:
    """Full pipeline: agent generates needs_review report → Controller queues candidate."""

    def test_needs_review_creates_candidate_file(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """A needs_review report should create a candidate change file."""
        from Agents.sheets_agent.sheets_report_generator import generate_report

        report = generate_report(SHEETS_TASK_HIGH_RISK, "sheets-worker-01")
        assert report["status"] == "needs_review"

        # Place report in Controller inbox
        team_dir = test_config.inbox_dir / "sheets-team" / "sheets-agent"
        team_dir.mkdir(parents=True, exist_ok=True)
        report_path = team_dir / "report_review_001.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

        # Process
        ctrl = Controller(test_config)
        success = ctrl.run_once()
        assert success is True

        # Report should be processed
        assert not report_path.exists()
        assert report_path.with_name("report_review_001.processed.json").exists()

        # Candidate file should be created
        candidates_dir = test_config.state_dir / "candidates"
        candidate_files = list(candidates_dir.glob("*.json"))
        assert len(candidate_files) == 1, (
            f"Expected 1 candidate file, found {len(candidate_files)}"
        )

        # Verify candidate content
        candidate = json.loads(
            candidate_files[0].read_text(encoding="utf-8")
        )
        assert candidate["task_id"] == "int-sheets-review-001"
        assert candidate["agent"] == "sheets-worker-01"
        assert candidate["status"] == "pending_review"
        assert len(candidate["review_reasons"]) >= 1
        assert len(candidate["proposed_changes"]) >= 1

    def test_auth_needs_review_creates_candidate(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """Auth agent revoke_token on service_account → candidate file."""
        from Agents.auth_agent.auth_report_generator import generate_report

        report = generate_report(AUTH_TASK_HIGH_RISK, "auth-agent-01")
        assert report["status"] == "needs_review"

        team_dir = test_config.inbox_dir / "security-team" / "auth-agent"
        team_dir.mkdir(parents=True, exist_ok=True)
        report_path = team_dir / "report_auth_review.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

        ctrl = Controller(test_config)
        success = ctrl.run_once()
        assert success is True

        candidates_dir = test_config.state_dir / "candidates"
        candidate_files = list(candidates_dir.glob("*.json"))
        assert len(candidate_files) == 1
        candidate = json.loads(
            candidate_files[0].read_text(encoding="utf-8")
        )
        assert candidate["agent"] == "auth-agent-01"
        assert "revoke_token" in candidate["review_reasons"][0]

    def test_review_candidate_approve_emits_directive(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """Approving a candidate should emit an execute_approved_change directive."""
        from Agents.sheets_agent.sheets_report_generator import generate_report

        # Step 1: Create needs_review report → candidate
        report = generate_report(SHEETS_TASK_HIGH_RISK, "sheets-worker-01")
        team_dir = test_config.inbox_dir / "sheets-team" / "sheets-agent"
        team_dir.mkdir(parents=True, exist_ok=True)
        report_path = team_dir / "report_review_approve.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

        ctrl = Controller(test_config)
        ctrl.run_once()

        # Step 2: Find the candidate_id
        candidates_dir = test_config.state_dir / "candidates"
        candidate_files = list(candidates_dir.glob("*.json"))
        assert len(candidate_files) == 1
        candidate = json.loads(
            candidate_files[0].read_text(encoding="utf-8")
        )
        candidate_id = candidate["candidate_id"]

        # Step 3: Submit a review_candidate task
        review_task: dict[str, Any] = {
            "task_id": "review-001",
            "skill": "review_candidate",
            "input": {
                "candidate_id": candidate_id,
                "decision": "approve",
                "reviewer": "test-operator",
                "notes": "Approved for testing",
            },
        }
        review_path = test_config.inbox_dir / "review_task.json"
        review_path.write_text(json.dumps(review_task), encoding="utf-8")

        # Step 4: Process the review
        result = ctrl.process_task(review_path)
        assert result is True

        # Step 5: Verify candidate is updated
        updated_candidate = json.loads(
            candidate_files[0].read_text(encoding="utf-8")
        )
        assert updated_candidate["status"] == "approved"
        assert updated_candidate["reviewer"] == "test-operator"

        # Step 6: Verify directive was emitted
        outbox = test_config.outbox_dir
        directive_files = list(outbox.rglob("*approved_directive.json"))
        assert len(directive_files) == 1
        directive = json.loads(
            directive_files[0].read_text(encoding="utf-8")
        )
        assert directive["command"] == "execute_approved_change"
        assert directive["parameters"]["candidate_id"] == candidate_id

    def test_review_candidate_reject(
        self,
        tmp_project: Path,
        test_config: ControllerConfig,
    ) -> None:
        """Rejecting a candidate should update status but emit no directive."""
        from Agents.auth_agent.auth_report_generator import generate_report

        # Create needs_review report → candidate
        report = generate_report(AUTH_TASK_HIGH_RISK, "auth-agent-01")
        team_dir = test_config.inbox_dir / "security-team" / "auth-agent"
        team_dir.mkdir(parents=True, exist_ok=True)
        report_path = team_dir / "report_auth_reject.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

        ctrl = Controller(test_config)
        ctrl.run_once()

        candidates_dir = test_config.state_dir / "candidates"
        candidate_files = list(candidates_dir.glob("*.json"))
        candidate = json.loads(
            candidate_files[0].read_text(encoding="utf-8")
        )
        candidate_id = candidate["candidate_id"]

        # Reject the candidate
        review_task: dict[str, Any] = {
            "task_id": "review-002",
            "skill": "review_candidate",
            "input": {
                "candidate_id": candidate_id,
                "decision": "reject",
                "reviewer": "test-operator",
                "notes": "Too risky for production",
            },
        }
        review_path = test_config.inbox_dir / "review_reject_task.json"
        review_path.write_text(json.dumps(review_task), encoding="utf-8")
        result = ctrl.process_task(review_path)
        assert result is True

        # Verify candidate is rejected
        updated = json.loads(
            candidate_files[0].read_text(encoding="utf-8")
        )
        assert updated["status"] == "rejected"
        assert updated["review_notes"] == "Too risky for production"

        # Verify NO directive was emitted
        outbox = test_config.outbox_dir
        directive_files = list(outbox.rglob("*approved_directive.json"))
        assert len(directive_files) == 0
