"""Shared fixtures for memory tests."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from memory.fs_memory_store import FSMemoryStore
from memory.memory_manager import MemoryManager


@pytest.fixture()
def sample_value() -> dict[str, Any]:
    """A representative memory payload."""
    return {
        "spreadsheet_id": "abc123",
        "sheet_name": "Sheet1",
        "range": "A1:C5",
    }


@pytest.fixture()
def fs_store(tmp_path: Path) -> FSMemoryStore:
    """FSMemoryStore rooted in a temporary directory."""
    return FSMemoryStore(base_dir=tmp_path / "memory_store")


@pytest.fixture()
def memory_manager(fs_store: FSMemoryStore) -> MemoryManager:
    """MemoryManager backed by an ephemeral FS store."""
    return MemoryManager(agent="test-agent", store=fs_store)
