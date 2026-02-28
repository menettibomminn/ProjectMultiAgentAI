"""High-level API for agent memory operations."""
from __future__ import annotations

import logging
from typing import Any

from memory import MemoryStore
from memory.memory_entry import MemoryEntry

logger = logging.getLogger(__name__)


class MemoryManager:
    """Convenience wrapper around a :class:`MemoryStore`.

    Parameters
    ----------
    agent:
        The agent identifier whose memories are managed.
    store:
        A concrete :class:`MemoryStore` backend.
    """

    def __init__(self, agent: str, store: MemoryStore) -> None:
        self._agent = agent
        self._store = store

    def remember(self, key: str, value: dict[str, Any]) -> MemoryEntry:
        """Persist a memory and return the created entry."""
        entry = MemoryEntry.create(
            agent=self._agent,
            key=key,
            value=value,
        )
        self._store.save(self._agent, key, entry.to_dict())
        logger.debug("Remembered %s/%s", self._agent, key)
        return entry

    def recall(self, key: str) -> MemoryEntry | None:
        """Retrieve a memory by key.  Returns ``None`` if absent."""
        data = self._store.get(self._agent, key)
        if data is None:
            return None
        return MemoryEntry.from_dict(data)

    def list_memories(self) -> list[str]:
        """Return all stored memory keys for this agent."""
        return self._store.list_keys(self._agent)

    def forget(self, key: str) -> bool:
        """Delete a memory.  Returns ``True`` if it existed."""
        removed = self._store.delete(self._agent, key)
        if removed:
            logger.debug("Forgot %s/%s", self._agent, key)
        return removed
