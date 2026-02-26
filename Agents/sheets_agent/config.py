"""Configuration for the Sheets Worker Agent.

All paths are relative to the project root. Override via environment variables:
    SHEETS_AGENT_ID       — agent identifier (default: sheets-worker-01)
    SHEETS_TEAM_ID        — team identifier (default: sheets-team)
    SHEETS_PROJECT_ROOT   — absolute path to project root
    SHEETS_LOCK_BACKEND   — "file" (default) | "redis"
    SHEETS_LOCK_TIMEOUT   — lock timeout in seconds (default: 120)
    SHEETS_REDIS_URL      — Redis connection URL (default: redis://localhost:6379/0)
    SHEETS_TASK_TIMEOUT   — task processing timeout in seconds (default: 60)
    SHEETS_RATE_RPM       — requests per minute (default: 60)
    SHEETS_RATE_RPD       — requests per day (default: 10000)
    SHEETS_RATE_BURST     — burst size (default: 10)
    SHEETS_RATE_MAX_WAIT  — max wait seconds when throttled (default: 60)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    """Derive project root: 3 levels up from agents/sheets/config.py."""
    return Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class SheetsAgentConfig:
    """Immutable configuration for the sheets worker agent."""

    # Identity
    agent_id: str = "sheets-worker-01"
    team_id: str = "sheets-team"
    version: int = 1

    # Project root
    project_root: Path = field(default_factory=_project_root)

    # Lock settings
    lock_backend: str = "file"          # "file" | "redis"
    lock_timeout_seconds: int = 120
    redis_url: str = "redis://localhost:6379/0"
    lock_max_retries: int = 5
    lock_backoff_base: float = 2.0

    # Task processing
    task_timeout_seconds: int = 60

    # Rate limiting (Google Sheets API quota)
    rate_requests_per_minute: int = 60
    rate_requests_per_day: int = 10_000
    rate_burst_size: int = 10
    rate_max_wait_seconds: float = 60.0
    rate_jitter: bool = True

    # Optional override for health file path (used by tests)
    health_file_override: Path | None = None

    # --- Derived paths (properties) ---

    @property
    def inbox_dir(self) -> Path:
        """inbox/sheets/{agent_id}/"""
        return self.project_root / "inbox" / "sheets" / self.agent_id

    @property
    def outbox_dir(self) -> Path:
        """outbox/sheets/{agent_id}/"""
        return self.project_root / "outbox" / "sheets" / self.agent_id

    @property
    def audit_dir(self) -> Path:
        """audit/sheets/{agent_id}/"""
        return self.project_root / "audit" / "sheets" / self.agent_id

    @property
    def locks_dir(self) -> Path:
        """locks/ at project root."""
        return self.project_root / "locks"

    @property
    def rate_state_dir(self) -> Path:
        """Directory for rate limiter state files."""
        return self.project_root / "Controller" / "state" / "rate_limits"

    @property
    def health_file(self) -> Path:
        """HEALTH.md location. Defaults to the agent package directory."""
        if self.health_file_override is not None:
            return self.health_file_override
        return Path(__file__).resolve().parent / "HEALTH.md"

    @property
    def task_file(self) -> Path:
        """Default task file path."""
        return self.inbox_dir / "task.json"

    @property
    def report_file(self) -> Path:
        """Default report file path."""
        return self.inbox_dir / "report.json"

    @classmethod
    def from_env(cls) -> SheetsAgentConfig:
        """Build config from environment variables with sensible defaults."""
        kwargs: dict[str, Any] = {}
        if v := os.environ.get("SHEETS_AGENT_ID"):
            kwargs["agent_id"] = v
        if v := os.environ.get("SHEETS_TEAM_ID"):
            kwargs["team_id"] = v
        if v := os.environ.get("SHEETS_PROJECT_ROOT"):
            kwargs["project_root"] = Path(v)
        if v := os.environ.get("SHEETS_LOCK_BACKEND"):
            kwargs["lock_backend"] = v
        if v := os.environ.get("SHEETS_LOCK_TIMEOUT"):
            kwargs["lock_timeout_seconds"] = int(v)
        if v := os.environ.get("SHEETS_REDIS_URL"):
            kwargs["redis_url"] = v
        if v := os.environ.get("SHEETS_TASK_TIMEOUT"):
            kwargs["task_timeout_seconds"] = int(v)
        if v := os.environ.get("SHEETS_RATE_RPM"):
            kwargs["rate_requests_per_minute"] = int(v)
        if v := os.environ.get("SHEETS_RATE_RPD"):
            kwargs["rate_requests_per_day"] = int(v)
        if v := os.environ.get("SHEETS_RATE_BURST"):
            kwargs["rate_burst_size"] = int(v)
        if v := os.environ.get("SHEETS_RATE_MAX_WAIT"):
            kwargs["rate_max_wait_seconds"] = float(v)
        return cls(**kwargs)
