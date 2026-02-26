"""Configuration for the Controller.

All paths are relative to the project root. Override via environment variables:
    CTRL_ID                  — controller identifier (default: controller-01)
    CTRL_PROJECT_ROOT        — absolute path to project root
    CTRL_LOCK_TIMEOUT        — lock timeout in seconds (default: 120)
    CTRL_PROCESS_TIMEOUT     — inbox processing timeout in seconds (default: 30)
    CTRL_ZOMBIE_LOCK_TIMEOUT — zombie lock timeout in seconds (default: 300)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    """Derive project root: 2 levels up from Controller/config.py."""
    return Path(__file__).resolve().parent.parent


def _default_agent_health_paths() -> dict[str, str]:
    """Default mapping of agent names to their HEALTH.md paths (relative to project root)."""
    return {
        "sheets-agent": "Agents/sheets_agent/HEALTH.md",
        "auth-agent": "Agents/auth_agent/HEALTH.md",
        "backend-agent": "Agents/backend_agent/HEALTH.md",
        "frontend-agent": "Agents/frontend_agent/HEALTH.md",
        "metrics-agent": "Agents/metrics_agent/HEALTH.md",
    }


@dataclass(frozen=True)
class ControllerConfig:
    """Immutable configuration for the controller."""

    # Identity
    controller_id: str = "controller-01"
    version: int = 1

    # Project root
    project_root: Path = field(default_factory=_project_root)

    # Lock settings
    lock_backend: str = "file"
    lock_timeout_seconds: int = 120
    lock_max_retries: int = 5
    lock_backoff_base: float = 2.0

    # Processing
    process_timeout_seconds: int = 30

    # Optional override for health file path (used by tests)
    health_file_override: Path | None = None

    # Health monitoring
    health_check_timeout_seconds: int = 600       # silence > 10min = degraded
    health_down_timeout_seconds: int = 1800       # silence > 30min = down
    health_degraded_failures: int = 3             # failures >= 3 = degraded
    health_down_failures: int = 6                 # failures >= 6 = down

    # Retry
    retry_max_per_task: int = 3
    retry_backoff_base: float = 2.0

    # Zombie lock detection
    zombie_lock_timeout_seconds: int = 300

    # Agent health paths (relative to project root)
    agent_health_paths: dict[str, str] = field(
        default_factory=_default_agent_health_paths
    )

    # --- Derived paths (properties) ---

    @property
    def inbox_dir(self) -> Path:
        """Controller/inbox/ — where agent reports arrive."""
        return self.project_root / "Controller" / "inbox"

    @property
    def outbox_dir(self) -> Path:
        """Controller/outbox/ — where directives are written."""
        return self.project_root / "Controller" / "outbox"

    @property
    def audit_dir(self) -> Path:
        """audit/controller/{controller_id}/"""
        return self.project_root / "audit" / "controller" / self.controller_id

    @property
    def locks_dir(self) -> Path:
        """locks/ at project root."""
        return self.project_root / "locks"

    @property
    def state_file(self) -> Path:
        """Orchestrator/STATE.md — single source of truth."""
        return self.project_root / "Orchestrator" / "STATE.md"

    @property
    def state_dir(self) -> Path:
        """Controller/state/ — runtime state files."""
        return self.project_root / "Controller" / "state"

    @property
    def retry_state_file(self) -> Path:
        """Controller/state/retry_state.json"""
        return self.state_dir / "retry_state.json"

    @property
    def system_health_file(self) -> Path:
        """Controller/state/system_health.json"""
        return self.state_dir / "system_health.json"

    @property
    def health_report_file(self) -> Path:
        """Controller/health/health_report.json — extended health report."""
        return self.project_root / "Controller" / "health" / "health_report.json"

    @property
    def controller_audit_dir(self) -> Path:
        """Controller/audit/ — simplified operational audit logs."""
        return self.project_root / "Controller" / "audit"

    @property
    def tasks_file(self) -> Path:
        """Controller/state/tasks.json — managed task registry."""
        return self.state_dir / "tasks.json"

    @property
    def audit_log_file(self) -> Path:
        """Controller/state/audit_log.jsonl — structured audit log."""
        return self.state_dir / "audit_log.jsonl"

    @property
    def resource_state_file(self) -> Path:
        """Controller/state/resource_state.json"""
        return self.state_dir / "resource_state.json"

    @property
    def orchestrator_alert_file(self) -> Path:
        """Controller/outbox/orchestrator_alert.json"""
        return self.outbox_dir / "orchestrator_alert.json"

    @property
    def health_file(self) -> Path:
        """HEALTH.md location."""
        if self.health_file_override is not None:
            return self.health_file_override
        return Path(__file__).resolve().parent / "HEALTH.md"

    @classmethod
    def from_env(cls) -> ControllerConfig:
        """Build config from environment variables with sensible defaults."""
        kwargs: dict[str, Any] = {}
        if v := os.environ.get("CTRL_ID"):
            kwargs["controller_id"] = v
        if v := os.environ.get("CTRL_PROJECT_ROOT"):
            kwargs["project_root"] = Path(v)
        if v := os.environ.get("CTRL_LOCK_TIMEOUT"):
            kwargs["lock_timeout_seconds"] = int(v)
        if v := os.environ.get("CTRL_PROCESS_TIMEOUT"):
            kwargs["process_timeout_seconds"] = int(v)
        if v := os.environ.get("CTRL_HEALTH_CHECK_TIMEOUT"):
            kwargs["health_check_timeout_seconds"] = int(v)
        if v := os.environ.get("CTRL_HEALTH_DOWN_TIMEOUT"):
            kwargs["health_down_timeout_seconds"] = int(v)
        if v := os.environ.get("CTRL_HEALTH_DEGRADED_FAILURES"):
            kwargs["health_degraded_failures"] = int(v)
        if v := os.environ.get("CTRL_HEALTH_DOWN_FAILURES"):
            kwargs["health_down_failures"] = int(v)
        if v := os.environ.get("CTRL_RETRY_MAX"):
            kwargs["retry_max_per_task"] = int(v)
        if v := os.environ.get("CTRL_RETRY_BACKOFF"):
            kwargs["retry_backoff_base"] = float(v)
        if v := os.environ.get("CTRL_ZOMBIE_LOCK_TIMEOUT"):
            kwargs["zombie_lock_timeout_seconds"] = int(v)
        return cls(**kwargs)
