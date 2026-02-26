"""Tests for StateManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from Orchestrator.models import (
    HealthStatus,
    StateChangeItem,
    StateUpdateRequest,
)
from Orchestrator.state_manager import StateManager
from Orchestrator.state_processor import compute_state_checksum, parse_state


def _make_manager(orch_dir: Path, timeout: float = 5.0) -> StateManager:
    return StateManager(
        state_path=orch_dir / "STATE.md",
        backup_dir=orch_dir / ".backup",
        lock_path=orch_dir / ".state.lock",
        health_path=orch_dir / "HEALTH.md",
        changelog_path=orch_dir / "CHANGELOG.md",
        mistake_path=orch_dir / "MISTAKE.md",
        audit_log_path=orch_dir / "ops" / "logs" / "audit.log",
        lock_timeout=timeout,
    )


def _make_request(
    changes: list[StateChangeItem] | None = None,
    reason: str = "Test update",
) -> StateUpdateRequest:
    if changes is None:
        changes = [
            StateChangeItem(
                section="agent_status",
                field="sheets-agent",
                column="Status",
                old_value="idle",
                new_value="active",
                reason="Task assigned",
                triggered_by="ctrl-001",
            ),
        ]
    return StateUpdateRequest(
        origin="controller",
        reason=reason,
        changes=changes,
    )


# -----------------------------------------------------------------------
# load / save
# -----------------------------------------------------------------------


class TestLoadState:
    def test_load_valid(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        doc = sm.load_state()
        assert len(doc.teams) == 2
        assert len(doc.agents) == 2

    def test_load_missing_raises(self, tmp_path: Path) -> None:
        sm = _make_manager(tmp_path)
        with pytest.raises(FileNotFoundError):
            sm.load_state()


class TestSaveState:
    def test_creates_file_and_hash(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        doc = sm.load_state()
        state_hash = sm.save_state(doc)

        assert len(state_hash) == 64
        hash_path = orchestrator_dir / "STATE.md.hash"
        assert hash_path.exists()
        assert hash_path.read_text(encoding="utf-8").strip() == state_hash

    def test_atomic_roundtrip(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        doc = sm.load_state()
        doc.agents[0]["Status"] = "error"
        sm.save_state(doc)

        doc2 = sm.load_state()
        assert doc2.agents[0]["Status"] == "error"


# -----------------------------------------------------------------------
# backup / restore
# -----------------------------------------------------------------------


class TestBackupRestore:
    def test_backup_creates_file(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        backup_path = sm.backup_state()
        assert backup_path.exists()
        assert ".state_backup_" in backup_path.name

    def test_restore_from_backup(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        original = (orchestrator_dir / "STATE.md").read_text(encoding="utf-8")
        backup_path = sm.backup_state()

        # Modify state.
        doc = sm.load_state()
        doc.agents[0]["Status"] = "error"
        sm.save_state(doc)

        # Restore.
        sm.restore_state(backup_path)
        restored = (orchestrator_dir / "STATE.md").read_text(encoding="utf-8")
        assert restored == original


# -----------------------------------------------------------------------
# update_state — full sequence
# -----------------------------------------------------------------------


class TestUpdateState:
    def test_successful_update(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        result = sm.update_state(_make_request())

        assert result.success
        assert len(result.state_hash) == 64
        assert result.errors == []

        doc = sm.load_state()
        assert doc.agents[0]["Status"] == "active"

    def test_creates_backup(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        sm.update_state(_make_request())
        backups = list((orchestrator_dir / ".backup").glob(".state_backup_*.md"))
        assert len(backups) >= 1

    def test_logs_hash_to_audit(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        result = sm.update_state(_make_request())

        audit_log = orchestrator_dir / "ops" / "logs" / "audit.log"
        assert audit_log.exists()
        lines = audit_log.read_text(encoding="utf-8").strip().split("\n")
        last = json.loads(lines[-1])
        assert last["hash"] == result.state_hash
        assert last["status"] == "ok"

    def test_appends_health(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        sm.update_state(_make_request())

        health = (orchestrator_dir / "HEALTH.md").read_text(encoding="utf-8")
        assert '"healthy"' in health

    def test_appends_changelog(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        sm.update_state(_make_request(reason="Agent activation"))

        changelog = (orchestrator_dir / "CHANGELOG.md").read_text(encoding="utf-8")
        assert "Agent activation" in changelog
        assert "state_update" in changelog

    def test_multiple_changes(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        changes = [
            StateChangeItem(
                section="agent_status",
                field="sheets-agent",
                column="Status",
                old_value="idle",
                new_value="active",
                reason="task",
                triggered_by="ctrl-001",
            ),
            StateChangeItem(
                section="system_metrics",
                field="",
                column="total_tasks_completed",
                old_value="5",
                new_value="6",
                reason="increment",
                triggered_by="ctrl-001",
            ),
        ]
        result = sm.update_state(_make_request(changes=changes))
        assert result.success

        doc = sm.load_state()
        assert doc.agents[0]["Status"] == "active"
        assert doc.system_metrics["total_tasks_completed"] == 6

    def test_lock_released_after_success(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        sm.update_state(_make_request())
        assert not sm._lock.is_acquired


# -----------------------------------------------------------------------
# update_state — error recovery
# -----------------------------------------------------------------------


class TestUpdateStateErrors:
    def test_validation_error_returns_failure(
        self, orchestrator_dir: Path
    ) -> None:
        sm = _make_manager(orchestrator_dir)
        request = _make_request(changes=[
            StateChangeItem(
                section="change_history",
                field="x",
                column="y",
                old_value="a",
                new_value="b",
                reason="test",
                triggered_by="test",
            ),
        ])
        result = sm.update_state(request)
        assert not result.success
        assert len(result.errors) > 0

    def test_validation_error_rolls_back_state(
        self, orchestrator_dir: Path
    ) -> None:
        sm = _make_manager(orchestrator_dir)
        original = (orchestrator_dir / "STATE.md").read_text(encoding="utf-8")

        request = _make_request(changes=[
            StateChangeItem(
                section="change_history",
                field="x",
                column="y",
                old_value="a",
                new_value="b",
                reason="test",
                triggered_by="test",
            ),
        ])
        sm.update_state(request)

        current = (orchestrator_dir / "STATE.md").read_text(encoding="utf-8")
        assert current == original

    def test_validation_error_logs_mistake(
        self, orchestrator_dir: Path
    ) -> None:
        sm = _make_manager(orchestrator_dir)
        request = _make_request(changes=[
            StateChangeItem(
                section="change_history",
                field="x",
                column="y",
                old_value="a",
                new_value="b",
                reason="test",
                triggered_by="test",
            ),
        ])
        sm.update_state(request)

        mistake = (orchestrator_dir / "MISTAKE.md").read_text(encoding="utf-8")
        assert "error" in mistake.lower()

    def test_validation_error_logs_audit_error(
        self, orchestrator_dir: Path
    ) -> None:
        sm = _make_manager(orchestrator_dir)
        request = _make_request(changes=[
            StateChangeItem(
                section="change_history",
                field="x",
                column="y",
                old_value="a",
                new_value="b",
                reason="test",
                triggered_by="test",
            ),
        ])
        sm.update_state(request)

        audit_log = orchestrator_dir / "ops" / "logs" / "audit.log"
        assert audit_log.exists()
        entry = json.loads(
            audit_log.read_text(encoding="utf-8").strip().split("\n")[-1]
        )
        assert entry["status"] == "error"

    def test_lock_released_after_error(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        request = _make_request(changes=[])  # Will fail validation.
        sm.update_state(request)
        assert not sm._lock.is_acquired

    def test_empty_changes_fails(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        result = sm.update_state(_make_request(changes=[]))
        assert not result.success
        assert any("No changes" in e for e in result.errors)


# -----------------------------------------------------------------------
# verify & health
# -----------------------------------------------------------------------


class TestVerifyIntegrity:
    def test_valid_state(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        content = (orchestrator_dir / "STATE.md").read_text(encoding="utf-8")
        checksum = compute_state_checksum(content)
        (orchestrator_dir / "STATE.md.hash").write_text(
            checksum, encoding="utf-8"
        )
        result = sm.verify_integrity()
        assert result.ok

    def test_missing_state(self, tmp_path: Path) -> None:
        sm = _make_manager(tmp_path)
        result = sm.verify_integrity()
        assert not result.ok


class TestHealthCheck:
    def test_healthy(self, orchestrator_dir: Path) -> None:
        sm = _make_manager(orchestrator_dir)
        health = sm.health_check()
        assert health.status == HealthStatus.HEALTHY
        assert len(health.state_hash) == 64

    def test_missing_state_down(self, tmp_path: Path) -> None:
        sm = _make_manager(tmp_path)
        health = sm.health_check()
        assert health.status == HealthStatus.DOWN
        assert len(health.errors) > 0

    def test_degraded_on_checksum_mismatch(
        self, orchestrator_dir: Path
    ) -> None:
        sm = _make_manager(orchestrator_dir)
        (orchestrator_dir / "STATE.md.hash").write_text(
            "wrong_hash", encoding="utf-8"
        )
        health = sm.health_check()
        assert health.status == HealthStatus.DEGRADED
        assert any("Checksum" in e for e in health.errors)
