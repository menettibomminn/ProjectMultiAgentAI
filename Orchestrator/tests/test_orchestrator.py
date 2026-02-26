"""Tests for Orchestrator core."""

from __future__ import annotations

from pathlib import Path

import pytest

from Orchestrator.exceptions import UnauthorizedAccessError
from Orchestrator.models import (
    HealthStatus,
    StateChangeItem,
    StateUpdateRequest,
)
from Orchestrator.orchestrator import Orchestrator


def _orch(orch_dir: Path) -> Orchestrator:
    return Orchestrator(orchestrator_dir=orch_dir, lock_timeout=5.0)


def _valid_request() -> StateUpdateRequest:
    return StateUpdateRequest(
        origin="controller",
        reason="Test",
        changes=[
            StateChangeItem(
                section="agent_status",
                field="sheets-agent",
                column="Status",
                old_value="idle",
                new_value="active",
                reason="test",
                triggered_by="ctrl-001",
            ),
        ],
    )


# -----------------------------------------------------------------------
# handle_state_update
# -----------------------------------------------------------------------


class TestHandleStateUpdate:
    def test_controller_accepted(self, orchestrator_dir: Path) -> None:
        orch = _orch(orchestrator_dir)
        result = orch.handle_state_update(_valid_request())
        assert result.success
        assert len(result.state_hash) == 64

    def test_unauthorized_rejected(self, orchestrator_dir: Path) -> None:
        orch = _orch(orchestrator_dir)
        request = StateUpdateRequest(
            origin="rogue-agent",
            reason="Hack",
            changes=[
                StateChangeItem(
                    section="agent_status",
                    field="sheets-agent",
                    column="Status",
                    old_value="idle",
                    new_value="compromised",
                    reason="attack",
                    triggered_by="rogue",
                ),
            ],
        )
        with pytest.raises(UnauthorizedAccessError) as exc_info:
            orch.handle_state_update(request)
        assert exc_info.value.origin == "rogue-agent"

    def test_empty_origin_rejected(self, orchestrator_dir: Path) -> None:
        orch = _orch(orchestrator_dir)
        request = StateUpdateRequest(
            origin="",
            reason="test",
            changes=[
                StateChangeItem(
                    section="agent_status",
                    field="x",
                    column="y",
                    old_value="a",
                    new_value="b",
                    reason="test",
                    triggered_by="test",
                ),
            ],
        )
        with pytest.raises(UnauthorizedAccessError):
            orch.handle_state_update(request)

    def test_agent_origin_rejected(self, orchestrator_dir: Path) -> None:
        orch = _orch(orchestrator_dir)
        request = StateUpdateRequest(
            origin="sheets-agent",
            reason="Direct write attempt",
            changes=[
                StateChangeItem(
                    section="agent_status",
                    field="sheets-agent",
                    column="Status",
                    old_value="idle",
                    new_value="active",
                    reason="self-update",
                    triggered_by="sheets-agent",
                ),
            ],
        )
        with pytest.raises(UnauthorizedAccessError):
            orch.handle_state_update(request)

    def test_validation_error_returns_failure(
        self, orchestrator_dir: Path
    ) -> None:
        orch = _orch(orchestrator_dir)
        request = StateUpdateRequest(
            origin="controller",
            reason="bad",
            changes=[],
        )
        result = orch.handle_state_update(request)
        assert not result.success


# -----------------------------------------------------------------------
# verify_state_integrity
# -----------------------------------------------------------------------


class TestVerifyStateIntegrity:
    def test_valid_state(self, orchestrator_dir: Path) -> None:
        orch = _orch(orchestrator_dir)
        result = orch.verify_state_integrity()
        assert result.valid  # No hash file → no checksum check.

    def test_missing_state(self, tmp_path: Path) -> None:
        orch_dir = tmp_path / "Orchestrator"
        orch_dir.mkdir()
        (orch_dir / ".backup").mkdir()
        (orch_dir / "ops" / "logs").mkdir(parents=True)
        (orch_dir / "HEALTH.md").write_text("", encoding="utf-8")
        (orch_dir / "CHANGELOG.md").write_text("", encoding="utf-8")
        (orch_dir / "MISTAKE.md").write_text("", encoding="utf-8")

        orch = _orch(orch_dir)
        result = orch.verify_state_integrity()
        assert not result.valid


# -----------------------------------------------------------------------
# health_check
# -----------------------------------------------------------------------


class TestHealthCheck:
    def test_healthy(self, orchestrator_dir: Path) -> None:
        orch = _orch(orchestrator_dir)
        health = orch.health_check()
        assert health.status == HealthStatus.HEALTHY

    def test_down_when_missing(self, tmp_path: Path) -> None:
        orch_dir = tmp_path / "Orchestrator"
        orch_dir.mkdir()
        (orch_dir / ".backup").mkdir()
        (orch_dir / "ops" / "logs").mkdir(parents=True)
        (orch_dir / "HEALTH.md").write_text("", encoding="utf-8")
        (orch_dir / "CHANGELOG.md").write_text("", encoding="utf-8")
        (orch_dir / "MISTAKE.md").write_text("", encoding="utf-8")

        orch = _orch(orch_dir)
        health = orch.health_check()
        assert health.status == HealthStatus.DOWN


# -----------------------------------------------------------------------
# init
# -----------------------------------------------------------------------


class TestOrchestratorInit:
    def test_requires_dir_or_manager(self) -> None:
        with pytest.raises(ValueError, match="Provide either"):
            Orchestrator()

    def test_with_orchestrator_dir(self, orchestrator_dir: Path) -> None:
        orch = Orchestrator(orchestrator_dir=orchestrator_dir)
        assert orch.health_check().status == HealthStatus.HEALTHY

    def test_with_state_manager(self, orchestrator_dir: Path) -> None:
        from Orchestrator.state_manager import StateManager

        sm = StateManager(
            state_path=orchestrator_dir / "STATE.md",
            backup_dir=orchestrator_dir / ".backup",
            lock_path=orchestrator_dir / ".state.lock",
            health_path=orchestrator_dir / "HEALTH.md",
            changelog_path=orchestrator_dir / "CHANGELOG.md",
            mistake_path=orchestrator_dir / "MISTAKE.md",
            audit_log_path=orchestrator_dir / "ops" / "logs" / "audit.log",
        )
        orch = Orchestrator(state_manager=sm)
        assert orch.health_check().status == HealthStatus.HEALTHY
