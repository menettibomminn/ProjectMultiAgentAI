"""SHA-256 hash computation and audit logging for state integrity."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class HashManager:
    """Compute SHA-256 hashes and log them to an audit file (JSONL)."""

    def __init__(self, audit_log_path: Path) -> None:
        self._audit_log_path = audit_log_path

    def compute_hash(self, state_content: str) -> str:
        """Compute SHA-256 hex digest of state content."""
        return hashlib.sha256(state_content.encode("utf-8")).hexdigest()

    def log_hash(
        self,
        state_hash: str,
        operation: str,
        request_id: str = "",
        status: str = "ok",
        error: str = "",
    ) -> None:
        """Append hash entry to audit log (JSONL format, fsync'd)."""
        entry: dict[str, str] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "status": status,
            "hash": state_hash,
            "request_id": request_id,
        }
        if error:
            entry["error"] = error

        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False) + "\n"

        fd = os.open(
            str(self._audit_log_path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        )
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

        logger.info(
            "Audit: op=%s status=%s hash=%s req=%s",
            operation,
            status,
            state_hash[:12] if state_hash else "(empty)",
            request_id,
        )
