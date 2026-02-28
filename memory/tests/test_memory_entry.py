"""Tests for MemoryEntry dataclass."""
from __future__ import annotations

import time
from typing import Any

import pytest

from memory.memory_entry import MemoryEntry


class TestMemoryEntry:
    def test_to_dict_roundtrip(self) -> None:
        entry = MemoryEntry(
            agent="a1", key="k1", value={"x": 1}, created_at=100.0
        )
        restored = MemoryEntry.from_dict(entry.to_dict())
        assert restored == entry

    def test_to_dict_keys(self) -> None:
        entry = MemoryEntry(
            agent="a1", key="k1", value={"x": 1}, created_at=100.0
        )
        d = entry.to_dict()
        assert set(d.keys()) == {"agent", "key", "value", "created_at"}

    def test_frozen(self) -> None:
        entry = MemoryEntry(
            agent="a1", key="k1", value={"x": 1}, created_at=100.0
        )
        with pytest.raises(AttributeError):
            entry.agent = "changed"  # type: ignore[misc]

    def test_create_sets_timestamp(self) -> None:
        before = time.time()
        entry = MemoryEntry.create(agent="a", key="k", value={"v": 1})
        after = time.time()
        assert before <= entry.created_at <= after

    def test_from_dict_coerces_created_at(self) -> None:
        d: dict[str, Any] = {
            "agent": "a",
            "key": "k",
            "value": {},
            "created_at": "42",
        }
        entry = MemoryEntry.from_dict(d)
        assert entry.created_at == 42.0
