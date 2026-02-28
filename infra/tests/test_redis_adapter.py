"""Unit tests for RedisQueue — all Redis calls are mocked (offline)."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# We patch the redis import inside redis_adapter so the real lib is not needed.


def _make_adapter(
    mock_redis_cls: MagicMock,
    url: str = "redis://localhost:6379/0",
) -> Any:
    """Build a RedisQueue with a mocked redis.Redis underneath."""
    from infra.redis_adapter import RedisQueue

    return RedisQueue(redis_url=url, queue_prefix="test")


class TestPush:
    """Verify push serialises to JSON and calls RPUSH."""

    @patch("infra.redis_adapter.redis_lib", create=True)
    def test_push_calls_rpush(self, _mock_lib: MagicMock) -> None:
        mock_client = MagicMock()
        with patch(
            "infra.redis_adapter.RedisQueue._connect",
            return_value=mock_client,
        ):
            from infra.redis_adapter import RedisQueue

            adapter = RedisQueue(queue_prefix="test")

        obj: dict[str, Any] = {"task_id": "t1", "op": "update"}
        adapter.push("inbox", obj)

        mock_client.rpush.assert_called_once()
        args = mock_client.rpush.call_args
        assert args[0][0] == "test:inbox"
        assert json.loads(args[0][1]) == obj

    @patch("infra.redis_adapter.RedisQueue._connect")
    def test_push_utf8(self, mock_connect: MagicMock) -> None:
        mock_client = MagicMock()
        mock_connect.return_value = mock_client
        from infra.redis_adapter import RedisQueue

        adapter = RedisQueue(queue_prefix="q")
        adapter.push("ch", {"name": "héllo"})

        payload = mock_client.rpush.call_args[0][1]
        assert "héllo" in payload


class TestPop:
    """Verify pop deserialises BLPOP results."""

    @patch("infra.redis_adapter.RedisQueue._connect")
    def test_pop_returns_dict(self, mock_connect: MagicMock) -> None:
        mock_client = MagicMock()
        obj: dict[str, Any] = {"task_id": "t2"}
        mock_client.blpop.return_value = ("test:q", json.dumps(obj))
        mock_connect.return_value = mock_client

        from infra.redis_adapter import RedisQueue

        adapter = RedisQueue(queue_prefix="test")
        result = adapter.pop("q", timeout=1)
        assert result == obj

    @patch("infra.redis_adapter.RedisQueue._connect")
    def test_pop_returns_none_on_timeout(
        self, mock_connect: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client.blpop.return_value = None
        mock_connect.return_value = mock_client

        from infra.redis_adapter import RedisQueue

        adapter = RedisQueue(queue_prefix="test")
        result = adapter.pop("q", timeout=1)
        assert result is None


class TestReconnect:
    """Verify retry + reconnect logic on transient failures."""

    @patch("infra.redis_adapter.time.sleep")
    @patch("infra.redis_adapter.RedisQueue._connect")
    def test_retry_succeeds_after_transient_error(
        self,
        mock_connect: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        # First call fails, second succeeds
        mock_client.rpush.side_effect = [
            ConnectionError("lost"),
            42,
        ]
        mock_connect.return_value = mock_client

        from infra.redis_adapter import RedisQueue

        adapter = RedisQueue(queue_prefix="test")
        adapter.push("q", {"ok": True})  # should not raise

        assert mock_client.rpush.call_count == 2
        mock_sleep.assert_called_once()

    @patch("infra.redis_adapter.time.sleep")
    @patch("infra.redis_adapter.RedisQueue._connect")
    def test_raises_after_max_retries(
        self,
        mock_connect: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.rpush.side_effect = ConnectionError("down")
        mock_connect.return_value = mock_client

        from infra.redis_adapter import RedisQueue

        adapter = RedisQueue(queue_prefix="test")

        with pytest.raises(ConnectionError):
            adapter.push("q", {"fail": True})

        assert mock_client.rpush.call_count == 5  # _MAX_RECONNECT


class TestPublish:
    """Verify publish serialises and calls PUBLISH."""

    @patch("infra.redis_adapter.RedisQueue._connect")
    def test_publish(self, mock_connect: MagicMock) -> None:
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        from infra.redis_adapter import RedisQueue

        adapter = RedisQueue(queue_prefix="test")
        adapter.publish("events", {"type": "task_done"})

        mock_client.publish.assert_called_once()
        assert "task_done" in mock_client.publish.call_args[0][1]


class TestMissingRedisLib:
    """Verify clear error when redis package is not installed."""

    def test_import_error_gives_clear_message(self) -> None:
        with patch.dict("sys.modules", {"redis": None}):
            from importlib import reload
            from infra import redis_adapter

            # Force reimport with redis blocked
            with pytest.raises(RuntimeError, match="redis package"):
                reload(redis_adapter)
                redis_adapter.RedisQueue()
