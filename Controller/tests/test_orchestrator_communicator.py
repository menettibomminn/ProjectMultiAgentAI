"""Tests for Controller.orchestrator_communicator."""
from __future__ import annotations

import json
from pathlib import Path

from Controller.orchestrator_communicator import (
    Alert,
    Conflict,
    OrchestratorCommunicator,
)


class TestAlertDataclass:
    """Test Alert dataclass."""

    def test_defaults(self) -> None:
        a = Alert(type="zombie_lock", resource_id="r1", agent_id="a1")
        assert a.type == "zombie_lock"
        assert a.timestamp != ""

    def test_custom_timestamp(self) -> None:
        a = Alert(
            type="stuck_agent", resource_id="r2", agent_id="a2",
            timestamp="2026-01-01T00:00:00+00:00", details="stuck for 10m",
        )
        assert a.timestamp == "2026-01-01T00:00:00+00:00"
        assert a.details == "stuck for 10m"


class TestConflictDataclass:
    """Test Conflict dataclass."""

    def test_defaults(self) -> None:
        c = Conflict(resource_id="r1", holders=["a1", "a2"])
        assert c.resource_id == "r1"
        assert len(c.holders) == 2
        assert c.timestamp != ""

    def test_conflict_type(self) -> None:
        c = Conflict(
            resource_id="r1", holders=["a1"], conflict_type="zombie_lock"
        )
        assert c.conflict_type == "zombie_lock"


class TestAddAlertAndConflict:
    """Test accumulation of alerts and conflicts."""

    def test_add_alert(self, tmp_path: Path) -> None:
        comm = OrchestratorCommunicator(tmp_path / "outbox")
        comm.add_alert("zombie_lock", "r1", "a1", "stale 300s")
        assert len(comm.alerts) == 1
        assert comm.alerts[0].type == "zombie_lock"

    def test_add_conflict(self, tmp_path: Path) -> None:
        comm = OrchestratorCommunicator(tmp_path / "outbox")
        comm.add_conflict("r1", ["a1", "a2"], "lock_contention")
        assert len(comm.conflicts) == 1
        assert comm.conflicts[0].conflict_type == "lock_contention"

    def test_multiple_alerts(self, tmp_path: Path) -> None:
        comm = OrchestratorCommunicator(tmp_path / "outbox")
        comm.add_alert("t1", "r1", "a1")
        comm.add_alert("t2", "r2", "a2")
        assert len(comm.alerts) == 2

    def test_clear(self, tmp_path: Path) -> None:
        comm = OrchestratorCommunicator(tmp_path / "outbox")
        comm.add_alert("t1", "r1", "a1")
        comm.add_conflict("r1", ["a1"], "x")
        comm.clear()
        assert comm.alerts == []
        assert comm.conflicts == []


class TestWriteSystemStatus:
    """Test write_system_status."""

    def test_writes_json(self, tmp_path: Path) -> None:
        outbox = tmp_path / "outbox"
        comm = OrchestratorCommunicator(outbox, controller_id="ctrl-01")
        path = comm.write_system_status(
            health={"overall_status": "healthy"},
            resource_state={"r1": {"modifying": False}},
        )
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["type"] == "system_status"
        assert data["controller_id"] == "ctrl-01"
        assert data["health"]["overall_status"] == "healthy"

    def test_creates_outbox_dir(self, tmp_path: Path) -> None:
        outbox = tmp_path / "deep" / "outbox"
        comm = OrchestratorCommunicator(outbox)
        comm.write_system_status({}, {})
        assert outbox.exists()


class TestWriteAlerts:
    """Test write_alerts."""

    def test_writes_alerts(self, tmp_path: Path) -> None:
        outbox = tmp_path / "outbox"
        comm = OrchestratorCommunicator(outbox)
        comm.add_alert("zombie_lock", "r1", "a1", "details")
        path = comm.write_alerts()
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["type"] == "alerts"
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["type"] == "zombie_lock"

    def test_empty_alerts(self, tmp_path: Path) -> None:
        outbox = tmp_path / "outbox"
        comm = OrchestratorCommunicator(outbox)
        path = comm.write_alerts()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["alerts"] == []


class TestWriteConflicts:
    """Test write_conflicts."""

    def test_writes_conflicts(self, tmp_path: Path) -> None:
        outbox = tmp_path / "outbox"
        comm = OrchestratorCommunicator(outbox)
        comm.add_conflict("r1", ["a1", "a2"], "contention")
        path = comm.write_conflicts()
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["type"] == "conflicts"
        assert len(data["conflicts"]) == 1


class TestWriteOrchestratorAlert:
    """Test write_orchestrator_alert."""

    def test_writes_alert(self, tmp_path: Path) -> None:
        outbox = tmp_path / "outbox"
        comm = OrchestratorCommunicator(outbox)
        alert = Alert(type="critical", resource_id="r1", agent_id="a1")
        path = comm.write_orchestrator_alert(alert)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["type"] == "orchestrator_alert"
        assert data["alert"]["type"] == "critical"


class TestFlushAll:
    """Test flush_all."""

    def test_flush_writes_status_only_when_empty(self, tmp_path: Path) -> None:
        outbox = tmp_path / "outbox"
        comm = OrchestratorCommunicator(outbox)
        comm.flush_all({"status": "ok"}, {"r1": {}})
        assert (outbox / "system_status.json").exists()
        assert not (outbox / "alerts.json").exists()
        assert not (outbox / "conflicts.json").exists()

    def test_flush_writes_all_when_populated(self, tmp_path: Path) -> None:
        outbox = tmp_path / "outbox"
        comm = OrchestratorCommunicator(outbox)
        comm.add_alert("t1", "r1", "a1")
        comm.add_conflict("r1", ["a1"], "x")
        comm.flush_all({"status": "ok"}, {})
        assert (outbox / "system_status.json").exists()
        assert (outbox / "alerts.json").exists()
        assert (outbox / "conflicts.json").exists()

    def test_clear_after_flush(self, tmp_path: Path) -> None:
        outbox = tmp_path / "outbox"
        comm = OrchestratorCommunicator(outbox)
        comm.add_alert("t1", "r1", "a1")
        comm.flush_all({}, {})
        comm.clear()
        assert comm.alerts == []
