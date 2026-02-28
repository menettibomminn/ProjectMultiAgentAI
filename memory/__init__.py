"""Agent memory — persistent key-value store per agent."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MemoryStore(Protocol):
    """Common interface for memory store backends (Redis / filesystem)."""

    def save(self, agent: str, key: str, value: dict[str, Any]) -> None:
        """Persist *value* under ``(agent, key)``."""
        ...

    def get(self, agent: str, key: str) -> dict[str, Any] | None:
        """Retrieve a stored value.  Returns ``None`` when absent."""
        ...

    def list_keys(self, agent: str) -> list[str]:
        """Return all stored keys for *agent*."""
        ...

    def delete(self, agent: str, key: str) -> bool:
        """Remove a stored value.  Returns ``True`` if it existed."""
        ...


from memory.memory_entry import MemoryEntry  # noqa: E402
from memory.memory_manager import MemoryManager  # noqa: E402

__all__ = [
    "MemoryStore",
    "MemoryEntry",
    "MemoryManager",
]
