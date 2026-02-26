"""Persistent state abstraction for the Controller.

Provides safe JSON read/write with atomic operations to prevent file
corruption on crashes or concurrent access.

All write operations use a write-to-temp + atomic-replace pattern.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from Controller.logger import get_logger

_log = get_logger("state_store")


class StateStoreError(Exception):
    """Raised when a state store operation fails."""


def save_json(path: Path, data: Any) -> None:
    """Write *data* as formatted JSON to *path*.

    Creates parent directories if they don't exist.
    Uses atomic_write internally to prevent corruption.
    """
    atomic_write(path, data)


def load_json(path: Path, default: Any = None) -> Any:
    """Read and parse a JSON file.

    Returns *default* if the file does not exist or cannot be parsed.
    """
    if not path.exists():
        return default

    try:
        raw = path.read_text(encoding="utf-8")
        return json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        _log.warning("Failed to load %s: %s — returning default", path, exc)
        return default


def atomic_write(path: Path, data: Any) -> None:
    """Write *data* as JSON atomically using a temp-file + replace pattern.

    Steps:
        1. Create parent directories.
        2. Write to a temporary file in the same directory.
        3. Flush and fsync the temporary file.
        4. Atomically replace the target file.

    This guarantees that *path* always contains either the old or the new
    content — never a partial write.

    Raises StateStoreError on failure.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False)

    fd = -1
    tmp_path = ""
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.stem}_",
            suffix=".tmp",
        )
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        fd = -1

        # Atomic replace (works on POSIX and Windows 3.3+)
        Path(tmp_path).replace(path)
    except OSError as exc:
        if fd >= 0:
            os.close(fd)
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink(missing_ok=True)
        raise StateStoreError(f"Atomic write to {path} failed: {exc}") from exc
