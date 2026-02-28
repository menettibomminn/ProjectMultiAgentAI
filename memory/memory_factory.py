"""Factory that selects the memory store based on environment variables.

Decision logic:
  REDIS_ENABLED=true + redis lib available  -> RedisMemoryStore
  REDIS_ENABLED=true + redis lib missing    -> FSMemoryStore (fallback)
  REDIS_ENABLED unset / false               -> FSMemoryStore
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from memory.fs_memory_store import FSMemoryStore

if TYPE_CHECKING:
    from memory.redis_memory_store import RedisMemoryStore

logger = logging.getLogger(__name__)


def get_memory_store() -> RedisMemoryStore | FSMemoryStore:
    """Return the appropriate :class:`MemoryStore` implementation."""
    if os.environ.get("REDIS_ENABLED", "").lower() != "true":
        return FSMemoryStore()

    redis_url = os.environ.get(
        "REDIS_URL", "redis://localhost:6379/0"
    )

    try:
        from memory.redis_memory_store import RedisMemoryStore

        store: RedisMemoryStore | FSMemoryStore = RedisMemoryStore(
            redis_url=redis_url
        )
        logger.info("Using Redis memory store at %s", redis_url)
        return store
    except RuntimeError:
        logger.warning(
            "redis package not available — falling back to FSMemoryStore"
        )
        return FSMemoryStore()
