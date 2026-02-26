"""Simplified audit logging facade for the Controller.

Re-exports functions from controller_audit_logger for backwards compatibility,
and adds a simpler AuditLogger class for operational logging.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Controller.controller_audit_logger import (  # noqa: F401 — re-exports
    compute_checksum,
    verify_report_checksum,
    write_audit_entry,
    write_hash_file,
)
from Controller.logger import get_logger


class AuditLogger:
    """Simple operational audit logger.

    Writes one JSON file per operation to Controller/audit/.
    """

    def __init__(
        self,
        audit_dir: Path,
        controller_id: str = "controller-01",
    ) -> None:
        self._audit_dir = audit_dir
        self._controller_id = controller_id
        self.log = get_logger(f"{controller_id}.audit")

    def log_operation(
        self,
        action: str,
        resource: str = "",
        agent: str = "",
        result: str = "",
    ) -> Path:
        """Write a single audit entry and return the file path."""
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        ts_slug = now.strftime("%Y%m%dT%H%M%SZ")

        entry: dict[str, Any] = {
            "timestamp": now.isoformat(),
            "action": action,
            "resource": resource,
            "agent": agent,
            "result": result,
            "controller_id": self._controller_id,
        }

        filename = f"{ts_slug}_{action}.json"
        path = self._audit_dir / filename
        path.write_text(
            json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return path

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def log_lock_acquired(self, resource: str, agent: str) -> Path:
        """Log a lock acquisition."""
        return self.log_operation(
            action="lock_acquired", resource=resource, agent=agent, result="ok"
        )

    def log_lock_released(self, resource: str, agent: str) -> Path:
        """Log a lock release."""
        return self.log_operation(
            action="lock_released", resource=resource, agent=agent, result="ok"
        )

    def log_alert_emitted(self, resource: str, agent: str, details: str = "") -> Path:
        """Log an alert emission."""
        return self.log_operation(
            action="alert_emitted", resource=resource, agent=agent, result=details
        )

    def log_health_check(self, result: str) -> Path:
        """Log a health check execution."""
        return self.log_operation(
            action="health_check", resource="system", result=result
        )
