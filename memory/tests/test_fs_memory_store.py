"""Tests for FSMemoryStore."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from memory import MemoryStore
from memory.fs_memory_store import FSMemoryStore


class TestFSMemoryStore:
    def test_save_and_get(
        self, fs_store: FSMemoryStore, sample_value: dict[str, Any]
    ) -> None:
        fs_store.save("agent1", "key1", sample_value)
        assert fs_store.get("agent1", "key1") == sample_value

    def test_get_missing_returns_none(self, fs_store: FSMemoryStore) -> None:
        assert fs_store.get("agent1", "nonexistent") is None

    def test_overwrite(self, fs_store: FSMemoryStore) -> None:
        fs_store.save("a", "k", {"v": 1})
        fs_store.save("a", "k", {"v": 2})
        assert fs_store.get("a", "k") == {"v": 2}

    def test_list_keys_empty(self, fs_store: FSMemoryStore) -> None:
        assert fs_store.list_keys("agent1") == []

    def test_list_keys(self, fs_store: FSMemoryStore) -> None:
        fs_store.save("a", "beta", {"x": 1})
        fs_store.save("a", "alpha", {"x": 2})
        assert fs_store.list_keys("a") == ["alpha", "beta"]

    def test_delete_existing(self, fs_store: FSMemoryStore) -> None:
        fs_store.save("a", "k", {"v": 1})
        assert fs_store.delete("a", "k") is True
        assert fs_store.get("a", "k") is None

    def test_delete_missing(self, fs_store: FSMemoryStore) -> None:
        assert fs_store.delete("a", "nope") is False

    def test_sanitises_unsafe_chars(self, fs_store: FSMemoryStore) -> None:
        fs_store.save("ns:agent", "key/with\\slash", {"ok": True})
        result = fs_store.get("ns:agent", "key/with\\slash")
        assert result == {"ok": True}

    def test_atomic_write(self, tmp_path: Path) -> None:
        """No .tmp files remain after a successful save."""
        store = FSMemoryStore(base_dir=tmp_path)
        store.save("a", "k", {"v": 1})
        tmps = list(tmp_path.rglob("*.tmp"))
        assert tmps == []

    def test_implements_protocol(self, fs_store: FSMemoryStore) -> None:
        assert isinstance(fs_store, MemoryStore)

    def test_corrupted_file_returns_none(self, tmp_path: Path) -> None:
        store = FSMemoryStore(base_dir=tmp_path)
        agent_dir = tmp_path / "a"
        agent_dir.mkdir()
        (agent_dir / "k.json").write_text("not json", encoding="utf-8")
        assert store.get("a", "k") is None
