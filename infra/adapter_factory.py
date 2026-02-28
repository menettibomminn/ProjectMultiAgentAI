"""Factory that selects the queue adapter based on environment variables.

Decision logic:
  REDIS_ENABLED=true + redis lib available  → RedisQueue
  REDIS_ENABLED=true + redis lib missing    → FSAdapter (fallback with warning)
  REDIS_ENABLED unset / false               → FSAdapter
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from infra.fs_adapter import FSAdapter

if TYPE_CHECKING:
    from infra.redis_adapter import RedisQueue

logger = logging.getLogger(__name__)


def get_queue_adapter() -> RedisQueue | FSAdapter:
    """Return the appropriate :class:`QueueAdapter` implementation."""
    if os.environ.get("REDIS_ENABLED", "").lower() != "true":
        return FSAdapter()

    redis_url = os.environ.get(
        "REDIS_URL", "redis://localhost:6379/0"
    )

    try:
        from infra.redis_adapter import RedisQueue

        adapter: RedisQueue | FSAdapter = RedisQueue(
            redis_url=redis_url
        )
        logger.info("Using Redis queue adapter at %s", redis_url)
        return adapter
    except RuntimeError:
        logger.warning(
            "redis package not available — falling back to FSAdapter"
        )
        return FSAdapter()
