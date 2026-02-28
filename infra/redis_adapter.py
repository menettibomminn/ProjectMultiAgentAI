"""Redis-backed queue adapter with reconnect and exponential backoff."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_MAX_RECONNECT = 5
_BASE_DELAY = 1.0
_MAX_DELAY = 30.0


class RedisQueue:
    """RPUSH / BLPOP queue over Redis, with automatic reconnect.

    Parameters
    ----------
    redis_url:
        Redis connection URL.  Falls back to ``REDIS_URL`` env var.
    queue_prefix:
        Namespace prefix for all queue keys (e.g. ``tasks:inbox:sheets``).
    """

    def __init__(
        self,
        redis_url: str = DEFAULT_REDIS_URL,
        queue_prefix: str = "tasks",
    ) -> None:
        self._url = redis_url
        self._prefix = queue_prefix
        self._client: Any = self._connect()

    # -- QueueAdapter interface -----------------------------------------------

    def push(self, queue_name: str, obj: dict[str, Any]) -> None:
        """RPUSH *obj* serialised as JSON."""
        payload = json.dumps(obj, ensure_ascii=False)
        self._retry(
            lambda: self._client.rpush(self._key(queue_name), payload)
        )

    def pop(
        self, queue_name: str, timeout: int = 5
    ) -> dict[str, Any] | None:
        """BLPOP with *timeout*.  Returns parsed dict or ``None``."""
        result: Any = self._retry(
            lambda: self._client.blpop(
                self._key(queue_name), timeout=timeout
            )
        )
        if result is None:
            return None
        _, raw = result
        parsed: dict[str, Any] = json.loads(raw)
        return parsed

    # -- Pub/Sub (optional) ---------------------------------------------------

    def publish(self, channel: str, message: dict[str, Any]) -> None:
        """PUBLISH *message* as JSON to *channel*."""
        payload = json.dumps(message, ensure_ascii=False)
        self._retry(lambda: self._client.publish(channel, payload))

    def subscribe(self, channel: str) -> Iterator[dict[str, Any]]:
        """Yield dicts from a Redis SUBSCRIBE channel (blocking)."""
        pubsub: Any = self._client.pubsub()
        pubsub.subscribe(channel)
        try:
            for raw_msg in pubsub.listen():
                if raw_msg["type"] == "message":
                    data: dict[str, Any] = json.loads(raw_msg["data"])
                    yield data
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()

    # -- Internals ------------------------------------------------------------

    def _key(self, queue_name: str) -> str:
        return f"{self._prefix}:{queue_name}"

    def _connect(self) -> Any:
        """Create a new Redis client.  Raises ``RuntimeError`` if the
        ``redis`` package is not installed."""
        try:
            import redis as redis_lib
        except ImportError as exc:
            raise RuntimeError(
                "redis package is required for RedisQueue. "
                "Install with: pip install redis"
            ) from exc
        client: Any = redis_lib.Redis.from_url(
            self._url, decode_responses=True
        )
        return client

    def _retry(self, fn: Callable[[], Any]) -> Any:
        """Execute *fn* with up to ``_MAX_RECONNECT`` retries on failure."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RECONNECT):
            try:
                result: Any = fn()
                return result
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RECONNECT - 1:
                    delay = min(
                        _BASE_DELAY * (2 ** attempt), _MAX_DELAY
                    )
                    logger.warning(
                        "Redis error (attempt %d/%d), "
                        "retry in %.1fs: %s",
                        attempt + 1,
                        _MAX_RECONNECT,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                    try:
                        self._client = self._connect()
                    except Exception:
                        pass
        assert last_exc is not None
        logger.error(
            "Redis unavailable after %d attempts: %s",
            _MAX_RECONNECT,
            last_exc,
        )
        raise last_exc
