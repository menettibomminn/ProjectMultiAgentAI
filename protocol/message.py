"""AgentMessage — frozen dataclass for structured inter-agent messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


VALID_STATUSES: frozenset[str] = frozenset({"success", "error", "retry"})


class InvalidMessageStatusError(ValueError):
    """Raised when an AgentMessage is created with an invalid status."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(
            f"Invalid message status {status!r}; "
            f"expected one of {sorted(VALID_STATUSES)}"
        )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AgentMessage:
    """Immutable inter-agent message with serialisation helpers.

    Parameters
    ----------
    status:
        One of ``"success"``, ``"error"``, ``"retry"``.
    agent:
        Identifier of the agent that produced the message.
    action:
        Logical action performed (e.g. ``"process_task"``).
    data:
        Optional payload dict (e.g. the report body).
    error:
        Human-readable error string (empty when *status* is ``"success"``).
    timestamp:
        ISO-8601 UTC timestamp.  Auto-generated when omitted.
    protocol_version:
        Schema version tag for forward compatibility.
    """

    status: str
    agent: str
    action: str
    data: dict[str, Any] | None = None
    error: str = ""
    timestamp: str = field(default_factory=_utcnow_iso)
    protocol_version: int = 1

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise InvalidMessageStatusError(self.status)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a flat dict.

        When *data* is present its keys are merged as top-level entries
        so that existing consumers (Controller ``parse_report_file``) see
        the same shape.  Envelope fields (``agent``, ``status``,
        ``action``, ``error``, ``timestamp``, ``protocol_version``) are
        always present and **cannot** be overridden by *data* keys.
        """
        base: dict[str, Any] = {}
        if self.data is not None:
            base.update(self.data)
        # Envelope always wins
        base["agent"] = self.agent
        base["status"] = self.status
        base["action"] = self.action
        base["error"] = self.error
        base["timestamp"] = self.timestamp
        base["protocol_version"] = self.protocol_version
        return base

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentMessage":
        """Reconstruct from a dict (new-format or legacy report_v1).

        Legacy reports use ``agent_id`` instead of ``agent``; both are
        accepted.
        """
        agent = d.get("agent") or d.get("agent_id", "")
        status = d.get("status", "error")
        action = d.get("action", "unknown")
        error = d.get("error", "")
        timestamp = d.get("timestamp", _utcnow_iso())
        protocol_version = d.get("protocol_version", 1)

        # Everything that is *not* an envelope field is treated as data.
        _envelope_keys = {
            "agent", "agent_id", "status", "action",
            "error", "timestamp", "protocol_version",
        }
        data = {k: v for k, v in d.items() if k not in _envelope_keys}

        return cls(
            status=status,
            agent=str(agent),
            action=str(action),
            data=data if data else None,
            error=str(error),
            timestamp=str(timestamp),
            protocol_version=int(protocol_version),
        )
