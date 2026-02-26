"""Structured JSON logging for the Auth Agent."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "agent_id": getattr(record, "agent_id", "unknown"),
            "task_id": getattr(record, "task_id", None),
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            entry["error"] = str(record.exc_info[1])
        return json.dumps(entry, ensure_ascii=False)


def get_logger(agent_id: str, task_id: str | None = None) -> logging.Logger:
    """Return a logger configured for structured JSON output.

    Args:
        agent_id: The agent identifier (injected into every record).
        task_id: Optional current task id.
    """
    name = f"auth_agent.{agent_id}"
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    class _ContextFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.agent_id = agent_id
            record.task_id = task_id
            return True

    for f in list(logger.filters):
        if isinstance(f, _ContextFilter):
            logger.removeFilter(f)
    logger.addFilter(_ContextFilter())

    return logger
