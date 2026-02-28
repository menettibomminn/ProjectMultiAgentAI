"""Tests for RedisMemoryStore (mocked Redis)."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestRedisMemoryStore:
    @pytest.fixture(autouse=True)
    def _mock_redis(self) -> Any:
        """Patch ``redis.Redis.from_url`` with a mock client."""
        self.mock_client = MagicMock()
        with patch.dict("sys.modules", {"redis": MagicMock()}) as _:
            import redis as redis_mock
            redis_mock.Redis.from_url.return_value = self.mock_client
            from memory.redis_memory_store import RedisMemoryStore
            self.StoreClass = RedisMemoryStore
            yield

    def test_save_calls_set(self) -> None:
        store = self.StoreClass.__new__(self.StoreClass)
        store._client = self.mock_client
        store._url = ""
        store.save("agent1", "key1", {"x": 1})
        self.mock_client.set.assert_called_once_with(
            "memory:agent1:key1",
            json.dumps({"x": 1}, ensure_ascii=False),
        )

    def test_get_returns_parsed(self) -> None:
        self.mock_client.get.return_value = '{"x": 1}'
        store = self.StoreClass.__new__(self.StoreClass)
        store._client = self.mock_client
        store._url = ""
        assert store.get("a", "k") == {"x": 1}

    def test_get_missing_returns_none(self) -> None:
        self.mock_client.get.return_value = None
        store = self.StoreClass.__new__(self.StoreClass)
        store._client = self.mock_client
        store._url = ""
        assert store.get("a", "k") is None

    def test_delete_returns_bool(self) -> None:
        self.mock_client.delete.return_value = 1
        store = self.StoreClass.__new__(self.StoreClass)
        store._client = self.mock_client
        store._url = ""
        assert store.delete("a", "k") is True

    def test_missing_redis_lib_raises(self) -> None:
        with patch.dict("sys.modules", {"redis": None}):
            # Reload to trigger ImportError path
            with pytest.raises((RuntimeError, ModuleNotFoundError)):
                from memory import redis_memory_store as _mod
                # Force re-import
                import importlib
                importlib.reload(_mod)
                _mod.RedisMemoryStore()
