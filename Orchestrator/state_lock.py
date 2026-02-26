"""File-based state lock using portalocker for crash-safe concurrency."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from types import TracebackType

import portalocker

from .exceptions import StateLockError

logger = logging.getLogger(__name__)


class StateLock:
    """Exclusive file lock for STATE.md writes.

    Thread-safe via threading.Lock + OS-level file lock via portalocker.
    Supports context manager protocol.
    """

    def __init__(self, lock_path: Path, timeout: float = 30.0) -> None:
        self._lock_path = lock_path
        self._timeout = timeout
        self._mu = threading.RLock()
        self._lock: portalocker.Lock | None = None
        self._acquired = False

    def acquire_lock(self) -> None:
        """Acquire exclusive lock. Blocks until timeout."""
        acquired_thread = self._mu.acquire(timeout=self._timeout)
        if not acquired_thread:
            raise StateLockError(
                f"Thread lock timeout after {self._timeout}s"
            )

        if self._acquired:
            # Already acquired (re-entrant call from same flow).
            self._mu.release()
            return

        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock = portalocker.Lock(
                str(self._lock_path),
                mode="w",
                timeout=self._timeout,
                flags=portalocker.LOCK_EX,
            )
            lock.acquire()
            # Write PID for crash diagnostics.
            fh = lock.fh
            if fh is not None:
                pid_str: str = str(os.getpid())
                fh.write(pid_str)  # type: ignore[call-overload]
                fh.flush()
            self._lock = lock
            self._acquired = True
            logger.info(
                "Lock acquired: %s (pid=%d)", self._lock_path, os.getpid()
            )
        except portalocker.LockException as exc:
            self._lock = None
            self._mu.release()
            raise StateLockError(
                f"File lock failed on {self._lock_path}: {exc}"
            ) from exc
        except OSError as exc:
            self._lock = None
            self._mu.release()
            raise StateLockError(
                f"Cannot open lock file {self._lock_path}: {exc}"
            ) from exc

    def release_lock(self) -> None:
        """Release lock. Safe to call when not held."""
        if not self._acquired:
            return

        try:
            if self._lock is not None:
                try:
                    self._lock.release()
                except Exception:  # noqa: BLE001
                    logger.debug("portalocker release failed (ignored)")
                self._lock = None
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._acquired = False
            logger.info("Lock released: %s", self._lock_path)
        finally:
            try:
                self._mu.release()
            except RuntimeError:
                pass  # Not held — defensive.

    @property
    def is_acquired(self) -> bool:
        """Whether this lock instance currently holds the lock."""
        return self._acquired

    def __enter__(self) -> StateLock:
        self.acquire_lock()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.release_lock()
