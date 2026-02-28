"""Google Sheets API client with retry and structured responses.

Standalone utility — no dependency on agents, controller, or orchestrator.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 60.0  # seconds

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------

class ResponseStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


@dataclass(frozen=True)
class SheetsResponse:
    """Structured response returned by every SheetsClient method."""

    status: ResponseStatus
    data: list[list[str]] | None = None
    updated_cells: int = 0
    cleared_range: str = ""
    error: str = ""
    error_code: int = 0
    retries_used: int = 0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SheetsClientError(Exception):
    """Base exception for SheetsClient errors."""

    def __init__(self, message: str, code: int = 0) -> None:
        super().__init__(message)
        self.code = code


class SheetsAuthError(SheetsClientError):
    """Raised when service-account credentials cannot be loaded."""


class SheetsPermissionError(SheetsClientError):
    """HTTP 403 — insufficient permissions."""


class SheetsNotFoundError(SheetsClientError):
    """HTTP 404 — spreadsheet or range not found."""


class SheetsRateLimitError(SheetsClientError):
    """HTTP 429 — rate limit exceeded after all retries."""


class SheetsServerError(SheetsClientError):
    """HTTP 5xx — Google server error after all retries."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class SheetsClient:
    """Thin wrapper around the Google Sheets v4 API.

    Parameters
    ----------
    credentials_path:
        Filesystem path to the service-account JSON key file.
        Falls back to the ``GOOGLE_SERVICE_ACCOUNT_PATH`` env var.
    max_retries:
        Maximum retry attempts for transient errors (429 / 5xx).
    base_delay:
        Initial backoff delay in seconds.
    max_delay:
        Upper bound for backoff delay in seconds.
    """

    def __init__(
        self,
        credentials_path: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
    ) -> None:
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay

        resolved_path = credentials_path or os.environ.get(
            "GOOGLE_SERVICE_ACCOUNT_PATH", ""
        )
        if not resolved_path:
            raise SheetsAuthError(
                "No credentials path provided. Set GOOGLE_SERVICE_ACCOUNT_PATH "
                "or pass credentials_path to SheetsClient()."
            )

        try:
            creds: Credentials = (
                Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
                    resolved_path, scopes=SCOPES
                )
            )
        except Exception as exc:
            raise SheetsAuthError(
                f"Failed to load service-account credentials from "
                f"{resolved_path}: {exc}"
            ) from exc

        self._service: Resource = build(
            "sheets", "v4", credentials=creds, cache_discovery=False
        )

    # -- public API ----------------------------------------------------------

    def read_range(
        self, spreadsheet_id: str, range_name: str
    ) -> SheetsResponse:
        """Read values from *range_name* in the given spreadsheet."""

        def _call() -> dict[str, Any]:
            resp: dict[str, Any] = (
                self._service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=range_name)
                .execute()
            )
            return resp

        result, retries = self._execute_with_retry(_call)

        rows: list[list[str]] = result.get("values", [])
        return SheetsResponse(
            status=ResponseStatus.SUCCESS,
            data=rows,
            retries_used=retries,
        )

    def write_range(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: Sequence[Sequence[str]],
    ) -> SheetsResponse:
        """Write *values* into *range_name* (RAW input, overwrite)."""

        body: dict[str, Any] = {"values": [list(row) for row in values]}

        def _call() -> dict[str, Any]:
            resp: dict[str, Any] = (
                self._service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption="RAW",
                    body=body,
                )
                .execute()
            )
            return resp

        result, retries = self._execute_with_retry(_call)

        return SheetsResponse(
            status=ResponseStatus.SUCCESS,
            updated_cells=result.get("updatedCells", 0),
            retries_used=retries,
        )

    def clear_range(
        self, spreadsheet_id: str, range_name: str
    ) -> SheetsResponse:
        """Clear all values in *range_name*."""

        def _call() -> dict[str, Any]:
            resp: dict[str, Any] = (
                self._service.spreadsheets()
                .values()
                .clear(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    body={},
                )
                .execute()
            )
            return resp

        result, retries = self._execute_with_retry(_call)

        return SheetsResponse(
            status=ResponseStatus.SUCCESS,
            cleared_range=result.get("clearedRange", range_name),
            retries_used=retries,
        )

    # -- retry engine --------------------------------------------------------

    def _execute_with_retry(
        self,
        call: Any,
    ) -> tuple[dict[str, Any], int]:
        """Run *call* with exponential backoff on transient errors.

        Returns ``(result_dict, retries_used)``.
        Raises a typed ``SheetsClientError`` on permanent failure.
        """
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                result: dict[str, Any] = call()
                return result, attempt
            except HttpError as exc:
                status_code: int = exc.resp.status
                last_exc = exc

                if status_code == 403:
                    raise SheetsPermissionError(
                        f"Permission denied: {exc}", code=403
                    ) from exc

                if status_code == 404:
                    raise SheetsNotFoundError(
                        f"Spreadsheet or range not found: {exc}", code=404
                    ) from exc

                if status_code not in _RETRYABLE_STATUS_CODES:
                    raise SheetsClientError(
                        f"HTTP {status_code}: {exc}", code=status_code
                    ) from exc

                # Transient — backoff and retry
                if attempt < self._max_retries:
                    delay = min(
                        self._base_delay * (2 ** attempt), self._max_delay
                    )
                    logger.warning(
                        "Transient error (HTTP %d), retry %d/%d in %.1fs",
                        status_code,
                        attempt + 1,
                        self._max_retries,
                        delay,
                    )
                    time.sleep(delay)

            except Exception as exc:
                raise SheetsClientError(str(exc)) from exc

        # All retries exhausted
        assert last_exc is not None
        status_code = getattr(
            getattr(last_exc, "resp", None), "status", 0
        )
        if status_code == 429:
            raise SheetsRateLimitError(
                f"Rate limit exceeded after {self._max_retries} retries: "
                f"{last_exc}",
                code=429,
            ) from last_exc
        raise SheetsServerError(
            f"Server error after {self._max_retries} retries: {last_exc}",
            code=status_code,
        ) from last_exc
