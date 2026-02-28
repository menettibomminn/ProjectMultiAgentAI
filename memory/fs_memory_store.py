"""Filesystem-backed memory store (fallback when Redis is unavailable)."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_UNSAFE_CHARS = re.compile(r"[:/\\]")


class FSMemoryStore:
    """Persist agent memories as individual JSON files.

    Layout::

        {base_dir}/{agent}/{key}.json

    Parameters
    ----------
    base_dir:
        Root directory.  Defaults to ``<cwd>/memory_store``.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or (Path.cwd() / "memory_store")

    # -- MemoryStore interface ------------------------------------------------

    def save(self, agent: str, key: str, value: dict[str, Any]) -> None:
        """Write *value* as JSON to ``{agent}/{key}.json``."""
        path = self._path(agent, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(value, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)

    def get(self, agent: str, key: str) -> dict[str, Any] | None:
        """Read a stored memory.  Returns ``None`` when absent."""
        path = self._path(agent, key)
        if not path.exists():
            return None
        try:
            data: dict[str, Any] = json.loads(
                path.read_text(encoding="utf-8")
            )
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read memory %s: %s", path, exc)
            return None

    def list_keys(self, agent: str) -> list[str]:
        """Return all stored keys for *agent*."""
        agent_dir = self._base_dir / self._safe(agent)
        if not agent_dir.exists():
            return []
        return sorted(
            f.stem for f in agent_dir.iterdir() if f.suffix == ".json"
        )

    def delete(self, agent: str, key: str) -> bool:
        """Remove a stored memory.  Returns ``True`` if it existed."""
        path = self._path(agent, key)
        if not path.exists():
            return False
        path.unlink()
        return True

    # -- Internals ------------------------------------------------------------

    def _path(self, agent: str, key: str) -> Path:
        return self._base_dir / self._safe(agent) / f"{self._safe(key)}.json"

    @staticmethod
    def _safe(name: str) -> str:
        """Sanitise a name for use as a directory/file component."""
        return _UNSAFE_CHARS.sub("_", name)
