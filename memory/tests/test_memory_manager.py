"""Tests for MemoryManager high-level API."""
from __future__ import annotations

from typing import Any

from memory.memory_entry import MemoryEntry
from memory.memory_manager import MemoryManager


class TestMemoryManager:
    def test_remember_and_recall(
        self, memory_manager: MemoryManager, sample_value: dict[str, Any]
    ) -> None:
        entry = memory_manager.remember("test_key", sample_value)
        assert isinstance(entry, MemoryEntry)
        assert entry.key == "test_key"
        assert entry.value == sample_value

        recalled = memory_manager.recall("test_key")
        assert recalled is not None
        assert recalled.value == sample_value

    def test_recall_missing(self, memory_manager: MemoryManager) -> None:
        assert memory_manager.recall("missing") is None

    def test_forget(
        self, memory_manager: MemoryManager, sample_value: dict[str, Any]
    ) -> None:
        memory_manager.remember("to_forget", sample_value)
        assert memory_manager.forget("to_forget") is True
        assert memory_manager.recall("to_forget") is None

    def test_forget_missing(self, memory_manager: MemoryManager) -> None:
        assert memory_manager.forget("nope") is False

    def test_list_memories(
        self, memory_manager: MemoryManager
    ) -> None:
        memory_manager.remember("beta", {"x": 1})
        memory_manager.remember("alpha", {"x": 2})
        keys = memory_manager.list_memories()
        assert keys == ["alpha", "beta"]
