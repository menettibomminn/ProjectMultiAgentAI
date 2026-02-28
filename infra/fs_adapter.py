"""Filesystem-backed queue adapter (fallback when Redis is unavailable)."""
from __future__ import annotations

import itertools
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 0.1  # seconds
_counter = itertools.count()  # monotonic tie-breaker for same-µs pushes


class FSAdapter:
    """File-based FIFO queue: one directory per queue, one JSON file per item.

    Parameters
    ----------
    base_dir:
        Root directory under which per-queue subdirectories are created.
        Defaults to ``<cwd>/queues``.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or (Path.cwd() / "queues")

    # -- QueueAdapter interface -----------------------------------------------

    def push(self, queue_name: str, obj: dict[str, Any]) -> None:
        """Write *obj* as a timestamped JSON file in the queue directory."""
        queue_dir = self._queue_dir(queue_name)
        queue_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        seq = next(_counter)
        path = queue_dir / f"{ts}-{seq:06d}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(obj, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)

    def pop(
        self, queue_name: str, timeout: int = 5
    ) -> dict[str, Any] | None:
        """Poll the queue directory for up to *timeout* seconds,
        returning the oldest JSON file or ``None``."""
        deadline = time.monotonic() + timeout
        while True:
            result = self._try_pop(queue_name)
            if result is not None:
                return result
            if time.monotonic() >= deadline:
                return None
            time.sleep(_POLL_INTERVAL)

    # -- Internals ------------------------------------------------------------

    def _queue_dir(self, queue_name: str) -> Path:
        safe = queue_name.replace(":", "_").replace("/", "_")
        return self._base_dir / safe

    def _try_pop(self, queue_name: str) -> dict[str, Any] | None:
        queue_dir = self._queue_dir(queue_name)
        if not queue_dir.exists():
            return None
        files = sorted(
            (f for f in queue_dir.iterdir() if f.suffix == ".json"),
            key=lambda p: p.name,
        )
        if not files:
            return None
        oldest = files[0]
        try:
            data: dict[str, Any] = json.loads(
                oldest.read_text(encoding="utf-8")
            )
            oldest.unlink()
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Failed to read queue file %s: %s", oldest, exc
            )
            return None
