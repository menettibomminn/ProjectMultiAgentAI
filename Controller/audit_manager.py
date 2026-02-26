"""Structured audit logging for the Controller.

Writes one JSON object per line (JSONL) to Controller/state/audit_log.jsonl.
Every action taken by the Controller or its agents is recorded with a
timestamp, task_id, agent, action, status, and optional details.

The log is append-only and designed for machine parsing.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Controller.logger import get_logger
from Controller.schema_validator import SchemaValidationError, validate_audit


class AuditManagerError(Exception):
    """Raised when an audit write operation fails."""


class AuditManager:
    """Append-only structured audit logger (JSONL format)."""

    def __init__(self, audit_log_file: Path) -> None:
        self._audit_log_file = audit_log_file
        self._log = get_logger("audit_manager")
        self._ensure_dir()

    def log_event(
        self,
        task_id: str,
        agent: str,
        action: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Append a structured audit entry.

        Args:
            task_id: The task this event relates to.
            agent: The agent that performed the action.
            action: Description of the action (e.g. "lock_acquired").
            status: Outcome (e.g. "ok", "error", "skipped").
            details: Optional additional context.

        Raises:
            AuditManagerError: If writing fails.
        """
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "agent": agent,
            "action": action,
            "status": status,
            "details": details or {},
        }

        try:
            validate_audit(entry)
        except SchemaValidationError as exc:
            raise AuditManagerError(
                f"Audit entry validation failed: {exc}"
            ) from exc

        line = json.dumps(entry, ensure_ascii=False) + "\n"

        try:
            fd = os.open(
                str(self._audit_log_file),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o644,
            )
            try:
                os.write(fd, line.encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise AuditManagerError(
                f"Failed to write audit log: {exc}"
            ) from exc

        self._log.info(
            "Audit: task=%s agent=%s action=%s status=%s",
            task_id, agent, action, status,
        )

    def _ensure_dir(self) -> None:
        """Create the parent directory for the audit log file."""
        self._audit_log_file.parent.mkdir(parents=True, exist_ok=True)
