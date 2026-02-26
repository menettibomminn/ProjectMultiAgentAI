"""Configuration for the Auth Agent.

All paths are relative to the project root. Override via environment variables:
    AUTH_AGENT_ID         — agent identifier (default: auth-agent-01)
    AUTH_TEAM_ID          — team identifier (default: security-team)
    AUTH_PROJECT_ROOT     — absolute path to project root
    AUTH_LOCK_BACKEND     — "file" (default) | "redis" (future)
    AUTH_LOCK_TIMEOUT     — lock timeout in seconds (default: 120)
    AUTH_TASK_TIMEOUT     — task processing timeout in seconds (default: 60)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    """Derive project root: 3 levels up from Agents/auth_agent/config.py."""
    return Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class AuthAgentConfig:
    """Immutable configuration for the auth agent."""

    # Identity
    agent_id: str = "auth-agent-01"
    team_id: str = "security-team"
    version: int = 1

    # Project root
    project_root: Path = field(default_factory=_project_root)

    # Lock settings
    lock_backend: str = "file"
    lock_timeout_seconds: int = 120
    lock_max_retries: int = 5
    lock_backoff_base: float = 2.0

    # Task processing
    task_timeout_seconds: int = 60

    # Optional override for health file path (used by tests)
    health_file_override: Path | None = None

    # --- Derived paths (properties) ---

    @property
    def inbox_dir(self) -> Path:
        """Controller/inbox/security-team/auth-agent/"""
        return (
            self.project_root / "Controller" / "inbox"
            / self.team_id / "auth-agent"
        )

    @property
    def outbox_dir(self) -> Path:
        """Controller/outbox/security-team/auth-agent/"""
        return (
            self.project_root / "Controller" / "outbox"
            / self.team_id / "auth-agent"
        )

    @property
    def audit_dir(self) -> Path:
        """ops/audit/auth-agent/"""
        return self.project_root / "ops" / "audit" / "auth-agent"

    @property
    def locks_dir(self) -> Path:
        """locks/ at project root."""
        return self.project_root / "locks"

    @property
    def health_file(self) -> Path:
        """HEALTH.md in the documentation directory."""
        if self.health_file_override is not None:
            return self.health_file_override
        return (
            self.project_root / "Agents" / "auth-agent" / "HEALTH.md"
        )

    @property
    def task_file(self) -> Path:
        """Default task file path."""
        return self.inbox_dir / "task.json"

    @property
    def report_file(self) -> Path:
        """Default report file path."""
        return self.inbox_dir / "report.json"

    @classmethod
    def from_env(cls) -> AuthAgentConfig:
        """Build config from environment variables with sensible defaults."""
        kwargs: dict[str, Any] = {}
        if v := os.environ.get("AUTH_AGENT_ID"):
            kwargs["agent_id"] = v
        if v := os.environ.get("AUTH_TEAM_ID"):
            kwargs["team_id"] = v
        if v := os.environ.get("AUTH_PROJECT_ROOT"):
            kwargs["project_root"] = Path(v)
        if v := os.environ.get("AUTH_LOCK_BACKEND"):
            kwargs["lock_backend"] = v
        if v := os.environ.get("AUTH_LOCK_TIMEOUT"):
            kwargs["lock_timeout_seconds"] = int(v)
        if v := os.environ.get("AUTH_TASK_TIMEOUT"):
            kwargs["task_timeout_seconds"] = int(v)
        return cls(**kwargs)
