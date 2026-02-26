"""Pydantic models for the Orchestrator module."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Health status of the Orchestrator."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class StateChangeItem(BaseModel):
    """A single state change within an update request."""

    section: str
    field: str
    column: str
    old_value: str
    new_value: str
    reason: str
    triggered_by: str


class StateUpdateRequest(BaseModel):
    """Request to update STATE.md. Only accepted from origin='controller'."""

    origin: str
    changes: list[StateChangeItem]
    reason: str
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ValidationResult(BaseModel):
    """Result of state change validation."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StateHealth(BaseModel):
    """Current health of the Orchestrator state."""

    status: HealthStatus
    last_check: datetime
    last_update: datetime | None = None
    state_hash: str = ""
    errors: list[str] = Field(default_factory=list)


class StateUpdateResult(BaseModel):
    """Result of a state update operation."""

    success: bool
    request_id: str
    state_hash: str = ""
    errors: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
