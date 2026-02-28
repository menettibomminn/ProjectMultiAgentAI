"""Immutable memory entry — serialisable record for agent memories."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MemoryEntry:
    """Single agent memory record.

    Parameters
    ----------
    agent:
        Identifier of the owning agent.
    key:
        Human-readable memory key (e.g. ``last_spreadsheet_used``).
    value:
        Arbitrary JSON-serialisable payload.
    created_at:
        Unix timestamp.  Defaults to ``time.time()`` at creation.
    """

    agent: str
    key: str
    value: dict[str, Any]
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON storage."""
        return {
            "agent": self.agent,
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        """Reconstruct a ``MemoryEntry`` from a dict produced by ``to_dict``."""
        return cls(
            agent=data["agent"],
            key=data["key"],
            value=data["value"],
            created_at=float(data["created_at"]),
        )

    @classmethod
    def create(
        cls,
        agent: str,
        key: str,
        value: dict[str, Any],
    ) -> MemoryEntry:
        """Convenience factory that fills ``created_at`` automatically."""
        return cls(
            agent=agent,
            key=key,
            value=value,
            created_at=time.time(),
        )
