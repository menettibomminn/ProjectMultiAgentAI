"""Tests for the rate_limiter module."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pytest

from Agents.sheets_agent.rate_limiter import RateLimiter, RateLimitError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_limiter(
    tmp_path: Path,
    *,
    rpm: int = 5,
    rpd: int = 100,
    max_wait: float = 0.1,
    jitter: bool = False,
    backoff_base: float = 0.01,
) -> RateLimiter:
    """Create a rate limiter with tight limits for fast tests."""
    return RateLimiter(
        state_dir=tmp_path,
        name="test-api",
        requests_per_minute=rpm,
        requests_per_day=rpd,
        burst_size=5,
        backoff_base=backoff_base,
        max_wait_seconds=max_wait,
        jitter=jitter,
    )


def _write_state(tmp_path: Path, state: dict[str, Any]) -> None:
    """Write a state file directly for test setup."""
    path = tmp_path / "rate_limit_test-api.json"
    path.write_text(json.dumps(state), encoding="utf-8")


def _read_state(tmp_path: Path) -> dict[str, Any]:
    """Read the persisted state file."""
    path = tmp_path / "rate_limit_test-api.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tests: basic operations
# ---------------------------------------------------------------------------


class TestTryAcquire:
    """Non-blocking slot acquisition."""

    def test_first_request_succeeds(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path)
        assert limiter.try_acquire() is True

    def test_increments_counters(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path)
        limiter.try_acquire()
        state = _read_state(tmp_path)
        assert state["minute_count"] == 1
        assert state["day_count"] == 1

    def test_multiple_requests_within_limit(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path, rpm=5)
        for _ in range(5):
            assert limiter.try_acquire() is True

    def test_last_request_timestamp_set(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path)
        limiter.try_acquire()
        state = _read_state(tmp_path)
        assert state["last_request"] is not None


class TestAcquire:
    """Blocking slot acquisition."""

    def test_acquire_succeeds_when_available(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path)
        limiter.acquire()  # should not raise


class TestRemaining:
    """Quota reporting."""

    def test_full_quota_on_fresh_limiter(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path, rpm=10, rpd=100)
        rem = limiter.remaining()
        assert rem["per_minute"] == 10
        assert rem["per_day"] == 100

    def test_decrements_after_requests(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path, rpm=10, rpd=100)
        limiter.try_acquire()
        limiter.try_acquire()
        rem = limiter.remaining()
        assert rem["per_minute"] == 8
        assert rem["per_day"] == 98


class TestReset:
    """Counter reset."""

    def test_reset_clears_counters(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path, rpm=5)
        for _ in range(5):
            limiter.try_acquire()
        assert limiter.try_acquire() is False  # exhausted
        limiter.reset()
        assert limiter.try_acquire() is True  # fresh


# ---------------------------------------------------------------------------
# Tests: rate limit enforcement
# ---------------------------------------------------------------------------


class TestPerMinuteLimit:
    """Per-minute quota enforcement."""

    def test_rejects_when_minute_exhausted(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path, rpm=3)
        for _ in range(3):
            assert limiter.try_acquire() is True
        assert limiter.try_acquire() is False

    def test_acquire_raises_on_timeout(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path, rpm=1, max_wait=0.05)
        limiter.try_acquire()  # exhaust the limit
        with pytest.raises(RateLimitError, match="Rate limit exceeded"):
            limiter.acquire()

    def test_remaining_is_zero_when_exhausted(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path, rpm=2)
        limiter.try_acquire()
        limiter.try_acquire()
        rem = limiter.remaining()
        assert rem["per_minute"] == 0


class TestPerDayLimit:
    """Per-day quota enforcement."""

    def test_rejects_when_day_exhausted(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path, rpm=100, rpd=3)
        for _ in range(3):
            assert limiter.try_acquire() is True
        assert limiter.try_acquire() is False

    def test_day_limit_independent_of_minute_limit(
        self, tmp_path: Path
    ) -> None:
        """Day limit can block even when minute limit is fine."""
        limiter = _make_limiter(tmp_path, rpm=10, rpd=2)
        limiter.try_acquire()
        limiter.try_acquire()
        # Minute has 8 left, but day is exhausted
        assert limiter.try_acquire() is False
        rem = limiter.remaining()
        assert rem["per_minute"] == 8
        assert rem["per_day"] == 0


# ---------------------------------------------------------------------------
# Tests: window rolling
# ---------------------------------------------------------------------------


class TestWindowRolling:
    """Verify counters reset when time windows elapse."""

    def test_minute_window_resets_after_60s(self, tmp_path: Path) -> None:
        """Simulate minute window expiry by writing old state."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(seconds=61)
        _write_state(tmp_path, {
            "minute_window_start": old.isoformat(),
            "minute_count": 999,  # should be reset
            "day_window_start": now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat(),
            "day_count": 5,
            "last_request": old.isoformat(),
        })
        limiter = _make_limiter(tmp_path, rpm=10)
        assert limiter.try_acquire() is True
        state = _read_state(tmp_path)
        assert state["minute_count"] == 1  # reset + 1 new request

    def test_day_window_resets_after_midnight(self, tmp_path: Path) -> None:
        """Simulate day window expiry by writing yesterday's state."""
        now = datetime.now(timezone.utc)
        yesterday = (now - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        _write_state(tmp_path, {
            "minute_window_start": now.isoformat(),
            "minute_count": 0,
            "day_window_start": yesterday.isoformat(),
            "day_count": 9999,  # should be reset
            "last_request": yesterday.isoformat(),
        })
        limiter = _make_limiter(tmp_path, rpd=100)
        assert limiter.try_acquire() is True
        state = _read_state(tmp_path)
        assert state["day_count"] == 1  # reset + 1 new request

    def test_minute_window_does_not_reset_within_60s(
        self, tmp_path: Path
    ) -> None:
        """Counter should persist within the same minute window."""
        now = datetime.now(timezone.utc)
        recent = now - timedelta(seconds=30)
        _write_state(tmp_path, {
            "minute_window_start": recent.isoformat(),
            "minute_count": 3,
            "day_window_start": now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat(),
            "day_count": 10,
            "last_request": recent.isoformat(),
        })
        limiter = _make_limiter(tmp_path, rpm=10)
        limiter.try_acquire()
        state = _read_state(tmp_path)
        assert state["minute_count"] == 4  # 3 + 1 (no reset)


# ---------------------------------------------------------------------------
# Tests: state persistence
# ---------------------------------------------------------------------------


class TestStatePersistence:
    """File-based state survives limiter re-instantiation."""

    def test_state_survives_new_instance(self, tmp_path: Path) -> None:
        limiter1 = _make_limiter(tmp_path, rpm=5)
        for _ in range(3):
            limiter1.try_acquire()

        # New instance reads same state
        limiter2 = _make_limiter(tmp_path, rpm=5)
        rem = limiter2.remaining()
        assert rem["per_minute"] == 2

    def test_state_file_created_on_first_write(
        self, tmp_path: Path
    ) -> None:
        state_file = tmp_path / "rate_limit_test-api.json"
        assert not state_file.exists()
        limiter = _make_limiter(tmp_path)
        limiter.try_acquire()
        assert state_file.exists()

    def test_state_dir_created_if_missing(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested" / "dir"
        limiter = RateLimiter(
            state_dir=nested,
            name="test-api",
            requests_per_minute=5,
            requests_per_day=100,
        )
        limiter.try_acquire()
        assert nested.exists()


# ---------------------------------------------------------------------------
# Tests: corrupt / missing state
# ---------------------------------------------------------------------------


class TestCorruptState:
    """Graceful handling of corrupt or incomplete state files."""

    def test_corrupt_json_resets_state(self, tmp_path: Path) -> None:
        state_file = tmp_path / "rate_limit_test-api.json"
        tmp_path.mkdir(parents=True, exist_ok=True)
        state_file.write_text("NOT VALID JSON!!!", encoding="utf-8")
        limiter = _make_limiter(tmp_path, rpm=5)
        assert limiter.try_acquire() is True
        assert limiter.remaining()["per_minute"] == 4

    def test_missing_keys_resets_state(self, tmp_path: Path) -> None:
        _write_state(tmp_path, {"minute_count": 999})  # missing other keys
        limiter = _make_limiter(tmp_path, rpm=5)
        assert limiter.try_acquire() is True

    def test_invalid_timestamp_handled(self, tmp_path: Path) -> None:
        _write_state(tmp_path, {
            "minute_window_start": "NOT-A-DATE",
            "minute_count": 0,
            "day_window_start": "NOT-A-DATE",
            "day_count": 0,
            "last_request": None,
        })
        limiter = _make_limiter(tmp_path, rpm=5)
        assert limiter.try_acquire() is True


# ---------------------------------------------------------------------------
# Tests: name sanitization
# ---------------------------------------------------------------------------


class TestNameSanitization:
    """State file names handle special characters."""

    def test_slashes_replaced(self, tmp_path: Path) -> None:
        limiter = RateLimiter(
            state_dir=tmp_path,
            name="team/agent",
            requests_per_minute=5,
            requests_per_day=100,
        )
        limiter.try_acquire()
        state_file = tmp_path / "rate_limit_team_agent.json"
        assert state_file.exists()
