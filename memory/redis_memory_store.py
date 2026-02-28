"""Redis-backed memory store with reconnect and exponential backoff."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_MAX_RETRIES = 5
_BASE_DELAY = 1.0
_MAX_DELAY = 30.0


class RedisMemoryStore:
    """Persist agent memories in Redis.

    Key format::

        memory:{agent}:{key}

    Parameters
    ----------
    redis_url:
        Redis connection URL.
    """

    def __init__(self, redis_url: str = DEFAULT_REDIS_URL) -> None:
        self._url = redis_url
        self._client: Any = self._connect()

    # -- MemoryStore interface ------------------------------------------------

    def save(self, agent: str, key: str, value: dict[str, Any]) -> None:
        """SET the JSON-serialised *value*."""
        payload = json.dumps(value, ensure_ascii=False)
        self._retry(
            lambda: self._client.set(self._key(agent, key), payload)
        )

    def get(self, agent: str, key: str) -> dict[str, Any] | None:
        """GET and deserialise.  Returns ``None`` when absent."""
        raw: str | None = self._retry(
            lambda: self._client.get(self._key(agent, key))
        )
        if raw is None:
            return None
        result: dict[str, Any] = json.loads(raw)
        return result

    def list_keys(self, agent: str) -> list[str]:
        """SCAN for all keys belonging to *agent*."""
        prefix = f"memory:{agent}:"
        cursor: int = 0
        keys: list[str] = []
        while True:
            def _scan(c: int = cursor) -> Any:
                return self._client.scan(
                    c, match=f"{prefix}*", count=100
                )
            cursor, batch = self._retry(_scan)
            for full_key in batch:
                keys.append(full_key[len(prefix):])
            if cursor == 0:
                break
        return sorted(keys)

    def delete(self, agent: str, key: str) -> bool:
        """DEL a memory key.  Returns ``True`` if it existed."""
        removed: int = self._retry(
            lambda: self._client.delete(self._key(agent, key))
        )
        return removed > 0

    # -- Internals ------------------------------------------------------------

    @staticmethod
    def _key(agent: str, key: str) -> str:
        return f"memory:{agent}:{key}"

    def _connect(self) -> Any:
        """Create a new Redis client."""
        try:
            import redis as redis_lib
        except ImportError as exc:
            raise RuntimeError(
                "redis package is required for RedisMemoryStore. "
                "Install with: pip install redis"
            ) from exc
        client: Any = redis_lib.Redis.from_url(
            self._url, decode_responses=True
        )
        return client

    def _retry(self, fn: Callable[[], Any]) -> Any:
        """Execute *fn* with up to ``_MAX_RETRIES`` retries on failure."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                result: Any = fn()
                return result
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    delay = min(
                        _BASE_DELAY * (2 ** attempt), _MAX_DELAY
                    )
                    logger.warning(
                        "Redis error (attempt %d/%d), "
                        "retry in %.1fs: %s",
                        attempt + 1,
                        _MAX_RETRIES,
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
            _MAX_RETRIES,
            last_exc,
        )
        raise last_exc
