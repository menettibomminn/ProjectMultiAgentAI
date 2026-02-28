"""Tests for get_memory_store factory."""
from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

from memory.fs_memory_store import FSMemoryStore
from memory.memory_factory import get_memory_store


class TestMemoryFactory:
    def test_default_returns_fs(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            store = get_memory_store()
        assert isinstance(store, FSMemoryStore)

    def test_redis_disabled_returns_fs(self) -> None:
        with patch.dict("os.environ", {"REDIS_ENABLED": "false"}):
            store = get_memory_store()
        assert isinstance(store, FSMemoryStore)

    def test_redis_enabled_without_lib_falls_back(self) -> None:
        """When REDIS_ENABLED=true but import raises RuntimeError."""
        fake_mod = types.ModuleType("memory.redis_memory_store")
        fake_cls = MagicMock(side_effect=RuntimeError("no redis"))
        fake_mod.RedisMemoryStore = fake_cls  # type: ignore[attr-defined]

        with patch.dict("os.environ", {"REDIS_ENABLED": "true"}):
            with patch.dict(
                "sys.modules",
                {"memory.redis_memory_store": fake_mod},
            ):
                store = get_memory_store()
        assert isinstance(store, FSMemoryStore)

    def test_redis_enabled_with_lib(self) -> None:
        """When REDIS_ENABLED=true and redis lib is available."""
        mock_store = MagicMock()
        fake_mod = types.ModuleType("memory.redis_memory_store")
        fake_cls = MagicMock(return_value=mock_store)
        fake_mod.RedisMemoryStore = fake_cls  # type: ignore[attr-defined]

        with patch.dict("os.environ", {"REDIS_ENABLED": "true"}):
            with patch.dict(
                "sys.modules",
                {"memory.redis_memory_store": fake_mod},
            ):
                store = get_memory_store()
        assert store is mock_store
