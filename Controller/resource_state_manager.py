"""Resource state tracking for the Controller.

Tracks which resources are currently being modified and by which agent.
State is persisted as JSON in Controller/state/resource_state.json.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Controller.logger import get_logger


@dataclass
class ResourceStateEntry:
    """State of a single tracked resource."""

    resource_id: str
    modifying: bool = False
    modified_by: str = ""
    timestamp: str = ""


class ResourceStateManager:
    """Track resource modification state for conflict detection."""

    def __init__(self, state_file: Path, controller_id: str = "controller-01") -> None:
        self._state_file = state_file
        self._controller_id = controller_id
        self.log = get_logger(f"{controller_id}.resource_state")
        self._state: dict[str, ResourceStateEntry] = {}
        self.load_state()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load_state(self) -> None:
        """Load resource state from disk."""
        if not self._state_file.exists():
            self._state = {}
            return
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._state = {}
            for rid, entry_data in raw.items():
                if rid.startswith("_"):
                    continue  # skip metadata keys like _meta
                self._state[rid] = ResourceStateEntry(**entry_data)
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            self.log.error("Failed to load resource state: %s", exc)
            self._state = {}

    def save_state(self) -> None:
        """Atomically write resource state to disk."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "_meta": {
                "version": 1,
                "created_by": self._controller_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        for rid, entry in self._state.items():
            data[rid] = asdict(entry)

        tmp = self._state_file.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(self._state_file)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mark_modifying(self, resource_id: str, agent_id: str) -> None:
        """Mark a resource as currently being modified by *agent_id*."""
        now = datetime.now(timezone.utc).isoformat()
        self._state[resource_id] = ResourceStateEntry(
            resource_id=resource_id,
            modifying=True,
            modified_by=agent_id,
            timestamp=now,
        )
        self.save_state()

    def mark_idle(self, resource_id: str) -> None:
        """Mark a resource as no longer being modified."""
        entry = self._state.get(resource_id)
        if entry is not None:
            entry.modifying = False
            entry.timestamp = datetime.now(timezone.utc).isoformat()
            self.save_state()

    def is_modifying(self, resource_id: str) -> bool:
        """Check if a resource is currently being modified."""
        entry = self._state.get(resource_id)
        return entry.modifying if entry is not None else False

    def get_all(self) -> dict[str, ResourceStateEntry]:
        """Return all tracked resource states."""
        return dict(self._state)

    def get_active_resources(self) -> list[ResourceStateEntry]:
        """Return only resources currently being modified."""
        return [e for e in self._state.values() if e.modifying]

    def remove(self, resource_id: str) -> None:
        """Remove a resource from tracking."""
        if resource_id in self._state:
            del self._state[resource_id]
            self.save_state()
