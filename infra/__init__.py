"""Infrastructure adapters for task queuing."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class QueueAdapter(Protocol):
    """Common interface for task queue backends (Redis / filesystem)."""

    def push(self, queue_name: str, obj: dict[str, Any]) -> None:
        """Enqueue *obj* as JSON into *queue_name*."""
        ...

    def pop(self, queue_name: str, timeout: int = 5) -> dict[str, Any] | None:
        """Dequeue next item from *queue_name*.  Block up to *timeout* seconds."""
        ...
