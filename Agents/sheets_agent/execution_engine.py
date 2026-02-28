"""Execution engine — runs real operations on Google Sheets via SheetsClient.

The engine produces structured :class:`ChangeResult` / :class:`ExecutionResult`
dataclasses instead of raw dicts, and optionally verifies writes with a
read-back step.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChangeResult:
    """Outcome of a single requested change."""

    op: str
    range: str
    status: str           # "success" | "error" | "skipped"
    updated_cells: int = 0
    verified: bool = False
    error_message: str = ""
    retries_used: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict for report embedding."""
        return {
            "op": self.op,
            "range": self.range,
            "status": self.status,
            "updated_cells": self.updated_cells,
            "verified": self.verified,
            "error_message": self.error_message,
            "retries_used": self.retries_used,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class ExecutionResult:
    """Aggregated result for all changes in a task."""

    task_id: str
    spreadsheet_id: str
    changes: list[ChangeResult]
    total_duration_ms: float

    @property
    def all_success(self) -> bool:
        """True when every change completed successfully."""
        return all(c.status == "success" for c in self.changes)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ExecutionEngine:
    """Execute real Google Sheets operations via :class:`SheetsClient`.

    Parameters
    ----------
    rate_limiter:
        An optional rate limiter.  When provided, a slot is acquired
        before each API call.
    verify_writes:
        When ``True``, each write is followed by a ``read_range`` call
        to confirm the values landed correctly.
    """

    def __init__(
        self,
        rate_limiter: Any = None,
        verify_writes: bool = False,
    ) -> None:
        self._rate_limiter = rate_limiter
        self._verify_writes = verify_writes
        self._client: Any = None

    # -- Public API ----------------------------------------------------------

    def execute(self, task: dict[str, Any]) -> ExecutionResult:
        """Process all ``requested_changes`` in *task*.

        Returns an :class:`ExecutionResult` with one :class:`ChangeResult`
        per change.
        """
        from utils.sheets_client import SheetsClientError

        t0 = time.monotonic()
        task_id: str = task["task_id"]
        spreadsheet_id: str = task["sheet"]["spreadsheet_id"]
        results: list[ChangeResult] = []

        try:
            client = self._get_client()
        except (RuntimeError, SheetsClientError) as exc:
            logger.error("Cannot initialise SheetsClient: %s", exc)
            for change in task["requested_changes"]:
                results.append(ChangeResult(
                    op=change["op"],
                    range=change["range"],
                    status="error",
                    error_message=str(exc),
                ))
            return ExecutionResult(
                task_id=task_id,
                spreadsheet_id=spreadsheet_id,
                changes=results,
                total_duration_ms=(time.monotonic() - t0) * 1000,
            )

        for change in task["requested_changes"]:
            cr = self._execute_single_change(client, spreadsheet_id, change)
            results.append(cr)

        return ExecutionResult(
            task_id=task_id,
            spreadsheet_id=spreadsheet_id,
            changes=results,
            total_duration_ms=(time.monotonic() - t0) * 1000,
        )

    # -- Internals -----------------------------------------------------------

    def _get_client(self) -> Any:
        """Lazily create and cache a :class:`SheetsClient` instance."""
        if self._client is None:
            from utils.sheets_client import SheetsClient
            self._client = SheetsClient()
        return self._client

    def _execute_single_change(
        self,
        client: Any,
        spreadsheet_id: str,
        change: dict[str, Any],
    ) -> ChangeResult:
        """Execute one requested change and return a :class:`ChangeResult`."""
        from utils.sheets_client import SheetsClientError

        op: str = change["op"]
        range_name: str = change["range"]
        t0 = time.monotonic()

        # Acquire rate-limit slot (if limiter provided)
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        try:
            if op in ("update", "append_row"):
                resp = client.write_range(
                    spreadsheet_id, range_name, change["values"]
                )
                verified = False
                if self._verify_writes:
                    verified = self._verify_write(
                        client, spreadsheet_id, range_name,
                        change["values"],
                    )
                return ChangeResult(
                    op=op,
                    range=range_name,
                    status=resp.status.value,
                    updated_cells=resp.updated_cells,
                    verified=verified,
                    retries_used=resp.retries_used,
                    duration_ms=(time.monotonic() - t0) * 1000,
                )

            if op in ("clear_range", "delete_row"):
                resp = client.clear_range(spreadsheet_id, range_name)
                return ChangeResult(
                    op=op,
                    range=range_name,
                    status=resp.status.value,
                    retries_used=resp.retries_used,
                    duration_ms=(time.monotonic() - t0) * 1000,
                )

            # Unknown op → skipped
            return ChangeResult(
                op=op,
                range=range_name,
                status="skipped",
                error_message=f"Unsupported op: {op}",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        except SheetsClientError as exc:
            logger.error("Sheets API error for %s %s: %s", op, range_name, exc)
            return ChangeResult(
                op=op,
                range=range_name,
                status="error",
                error_message=str(exc),
                duration_ms=(time.monotonic() - t0) * 1000,
            )

    def _verify_write(
        self,
        client: Any,
        spreadsheet_id: str,
        range_name: str,
        expected: list[list[str]] | Any,
    ) -> bool:
        """Read-back *range_name* and compare against *expected* values."""
        try:
            resp = client.read_range(spreadsheet_id, range_name)
            if resp.data is None:
                return False
            result: bool = resp.data == [list(row) for row in expected]
            return result
        except Exception as exc:
            logger.warning("Verify read-back failed for %s: %s", range_name, exc)
            return False
