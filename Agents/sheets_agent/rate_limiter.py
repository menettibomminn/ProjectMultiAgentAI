"""Token-bucket rate limiter with file-based state persistence.

Enforces per-minute and per-day request quotas (aligned with Google Sheets API
defaults: 60 req/min, ~unlimited daily for most tiers).

State is persisted to a JSON file so limits survive across agent invocations.
Backoff uses exponential delay with optional jitter to prevent thundering herd.

Usage::

    limiter = RateLimiter(state_dir=Path("Controller/state"), name="sheets-api")
    limiter.acquire()            # blocks until a slot is available
    if limiter.try_acquire():    # non-blocking variant
        ...

Design:
- Sliding-window counters (per-minute, per-day).
- Atomic state writes (tmp + rename).
- No external dependencies (stdlib only).
"""
from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RateLimitError(Exception):
    """Raised when rate limit is exceeded and wait timeout expires."""


class RateLimiter:
    """Sliding-window rate limiter with file-persisted counters."""

    def __init__(
        self,
        state_dir: Path,
        name: str = "default",
        *,
        requests_per_minute: int = 60,
        requests_per_day: int = 10_000,
        burst_size: int = 10,
        backoff_base: float = 1.0,
        max_wait_seconds: float = 60.0,
        jitter: bool = True,
    ) -> None:
        self._state_dir = state_dir
        self._name = name
        self._rpm = requests_per_minute
        self._rpd = requests_per_day
        self._burst = burst_size
        self._backoff_base = backoff_base
        self._max_wait = max_wait_seconds
        self._jitter = jitter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(self) -> None:
        """Block until a request slot is available.

        Uses exponential backoff with optional jitter.
        Raises RateLimitError if *max_wait_seconds* is exceeded.
        """
        deadline = time.monotonic() + self._max_wait
        attempt = 0
        while True:
            if self.try_acquire():
                return
            if time.monotonic() >= deadline:
                remaining = self.remaining()
                raise RateLimitError(
                    f"Rate limit exceeded for '{self._name}' after "
                    f"{self._max_wait}s — remaining: {remaining}"
                )
            delay = self._backoff_base * (2 ** min(attempt, 5))
            if self._jitter:
                delay *= 0.5 + random.random()  # noqa: S311
            delay = min(delay, deadline - time.monotonic())
            if delay > 0:
                time.sleep(delay)
            attempt += 1

    def try_acquire(self) -> bool:
        """Non-blocking attempt to acquire a request slot.

        Returns True if the request is allowed, False otherwise.
        """
        now = datetime.now(timezone.utc)
        state = self._load_state()
        state = self._roll_windows(state, now)

        minute_count = state["minute_count"]
        day_count = state["day_count"]

        if minute_count >= self._rpm:
            self._save_state(state)
            return False
        if day_count >= self._rpd:
            self._save_state(state)
            return False

        state["minute_count"] = minute_count + 1
        state["day_count"] = day_count + 1
        state["last_request"] = now.isoformat()
        self._save_state(state)
        return True

    def remaining(self) -> dict[str, int]:
        """Return remaining quota for current windows."""
        now = datetime.now(timezone.utc)
        state = self._load_state()
        state = self._roll_windows(state, now)
        return {
            "per_minute": max(0, self._rpm - state["minute_count"]),
            "per_day": max(0, self._rpd - state["day_count"]),
        }

    def reset(self) -> None:
        """Reset all counters. Useful for testing."""
        now = datetime.now(timezone.utc)
        state = self._empty_state(now)
        self._save_state(state)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    @property
    def _state_path(self) -> Path:
        safe = self._name.replace("/", "_").replace("\\", "_")
        return self._state_dir / f"rate_limit_{safe}.json"

    def _load_state(self) -> dict[str, Any]:
        path = self._state_path
        if not path.exists():
            return self._empty_state(datetime.now(timezone.utc))
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            # Validate required keys
            for key in (
                "minute_window_start",
                "minute_count",
                "day_window_start",
                "day_count",
            ):
                if key not in data:
                    return self._empty_state(datetime.now(timezone.utc))
            return data
        except (json.JSONDecodeError, OSError):
            return self._empty_state(datetime.now(timezone.utc))

    def _save_state(self, state: dict[str, Any]) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self._state_path)

    @staticmethod
    def _empty_state(now: datetime) -> dict[str, Any]:
        return {
            "minute_window_start": now.isoformat(),
            "minute_count": 0,
            "day_window_start": now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat(),
            "day_count": 0,
            "last_request": None,
        }

    @staticmethod
    def _roll_windows(
        state: dict[str, Any], now: datetime
    ) -> dict[str, Any]:
        """Reset counters if their windows have elapsed."""
        # Minute window
        try:
            minute_start = datetime.fromisoformat(
                state["minute_window_start"]
            )
        except (ValueError, TypeError):
            minute_start = now
        if (now - minute_start).total_seconds() >= 60:
            state["minute_window_start"] = now.isoformat()
            state["minute_count"] = 0

        # Day window (resets at midnight UTC)
        today_midnight = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        try:
            day_start = datetime.fromisoformat(state["day_window_start"])
        except (ValueError, TypeError):
            day_start = today_midnight
        if day_start < today_midnight:
            state["day_window_start"] = today_midnight.isoformat()
            state["day_count"] = 0

        return state
