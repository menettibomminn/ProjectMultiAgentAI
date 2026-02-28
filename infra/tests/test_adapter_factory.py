"""Unit tests for adapter_factory — env var selection logic."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from infra.fs_adapter import FSAdapter


class TestGetQueueAdapter:
    """Verify factory returns correct adapter based on env vars."""

    def test_default_returns_fs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("REDIS_ENABLED", raising=False)
        from infra.adapter_factory import get_queue_adapter

        adapter = get_queue_adapter()
        assert isinstance(adapter, FSAdapter)

    def test_false_returns_fs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REDIS_ENABLED", "false")
        from infra.adapter_factory import get_queue_adapter

        adapter = get_queue_adapter()
        assert isinstance(adapter, FSAdapter)

    def test_true_without_redis_lib_returns_fs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When REDIS_ENABLED=true but redis lib is missing → FSAdapter."""
        monkeypatch.setenv("REDIS_ENABLED", "true")

        from infra.adapter_factory import get_queue_adapter

        # Patch the lazy import target so RedisQueue() raises RuntimeError
        with patch(
            "infra.redis_adapter.RedisQueue.__init__",
            side_effect=RuntimeError("no redis"),
        ):
            adapter = get_queue_adapter()
            assert isinstance(adapter, FSAdapter)

    def test_true_with_redis_returns_redis(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When REDIS_ENABLED=true and redis lib available → RedisQueue."""
        monkeypatch.setenv("REDIS_ENABLED", "true")
        monkeypatch.setenv("REDIS_URL", "redis://test:6379/0")

        with patch(
            "infra.redis_adapter.RedisQueue._connect"
        ) as mock_conn:
            mock_conn.return_value = None  # skip real connection
            from infra.adapter_factory import get_queue_adapter
            from infra.redis_adapter import RedisQueue

            # Need to patch at the import site inside factory
            adapter = get_queue_adapter()
            assert isinstance(adapter, RedisQueue)
