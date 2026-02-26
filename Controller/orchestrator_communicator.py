"""Structured communication with the Orchestrator.

Accumulates alerts and conflicts during a processing cycle, then
flushes them as JSON files to Controller/outbox/ for the Orchestrator
to consume.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Controller.logger import get_logger


@dataclass
class Alert:
    """A single alert to be communicated to the Orchestrator."""

    type: str
    resource_id: str
    agent_id: str
    timestamp: str = ""
    details: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class Conflict:
    """A detected resource conflict."""

    resource_id: str
    holders: list[str] = field(default_factory=list)
    conflict_type: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class OrchestratorCommunicator:
    """Accumulate alerts/conflicts and flush them to the outbox."""

    def __init__(
        self,
        outbox_dir: Path,
        controller_id: str = "controller-01",
    ) -> None:
        self._outbox_dir = outbox_dir
        self._controller_id = controller_id
        self.log = get_logger(f"{controller_id}.orchestrator_comm")
        self._alerts: list[Alert] = []
        self._conflicts: list[Conflict] = []

    # ------------------------------------------------------------------
    # Accumulate
    # ------------------------------------------------------------------

    def add_alert(
        self,
        alert_type: str,
        resource_id: str,
        agent_id: str,
        details: str = "",
    ) -> None:
        """Accumulate a new alert."""
        self._alerts.append(Alert(
            type=alert_type,
            resource_id=resource_id,
            agent_id=agent_id,
            details=details,
        ))

    def add_conflict(
        self,
        resource_id: str,
        holders: list[str],
        conflict_type: str = "",
    ) -> None:
        """Accumulate a new conflict."""
        self._conflicts.append(Conflict(
            resource_id=resource_id,
            holders=holders,
            conflict_type=conflict_type,
        ))

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write_system_status(
        self,
        health: dict[str, Any],
        resource_state: dict[str, Any],
    ) -> Path:
        """Write a system status snapshot to the outbox."""
        self._outbox_dir.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "type": "system_status",
            "controller_id": self._controller_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health": health,
            "resource_state": resource_state,
            "alert_count": len(self._alerts),
            "conflict_count": len(self._conflicts),
        }
        path = self._outbox_dir / "system_status.json"
        self._write_json(path, data)
        return path

    def write_alerts(self) -> Path:
        """Write accumulated alerts to the outbox."""
        self._outbox_dir.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "type": "alerts",
            "controller_id": self._controller_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alerts": [asdict(a) for a in self._alerts],
        }
        path = self._outbox_dir / "alerts.json"
        self._write_json(path, data)
        return path

    def write_conflicts(self) -> Path:
        """Write accumulated conflicts to the outbox."""
        self._outbox_dir.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "type": "conflicts",
            "controller_id": self._controller_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "conflicts": [asdict(c) for c in self._conflicts],
        }
        path = self._outbox_dir / "conflicts.json"
        self._write_json(path, data)
        return path

    def write_orchestrator_alert(self, alert: Alert) -> Path:
        """Write a single high-priority alert for the Orchestrator."""
        self._outbox_dir.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "type": "orchestrator_alert",
            "controller_id": self._controller_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert": asdict(alert),
        }
        path = self._outbox_dir / "orchestrator_alert.json"
        self._write_json(path, data)
        return path

    def flush_all(
        self,
        health: dict[str, Any],
        resource_state: dict[str, Any],
    ) -> None:
        """Write all accumulated data to the outbox."""
        self.write_system_status(health, resource_state)
        if self._alerts:
            self.write_alerts()
        if self._conflicts:
            self.write_conflicts()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Reset internal accumulation state."""
        self._alerts.clear()
        self._conflicts.clear()

    @property
    def alerts(self) -> list[Alert]:
        """Return accumulated alerts (read-only)."""
        return list(self._alerts)

    @property
    def conflicts(self) -> list[Conflict]:
        """Return accumulated conflicts (read-only)."""
        return list(self._conflicts)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        """Atomically write a JSON file."""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(path)
