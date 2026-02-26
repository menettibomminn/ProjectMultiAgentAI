"""Orchestrator — top-level entry point for state management.

Authorizes requests (only 'controller' allowed) and delegates to StateManager.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .exceptions import UnauthorizedAccessError
from .models import (
    StateHealth,
    StateUpdateRequest,
    StateUpdateResult,
    ValidationResult,
)
from .state_manager import StateManager
from .state_processor import VerifyResult

logger = logging.getLogger(__name__)

AUTHORIZED_ORIGIN = "controller"


class Orchestrator:
    """Top-level Orchestrator: authorizes and delegates state operations."""

    def __init__(
        self,
        *,
        orchestrator_dir: Path | None = None,
        state_manager: StateManager | None = None,
        lock_timeout: float = 30.0,
    ) -> None:
        """Initialize Orchestrator.

        Args:
            orchestrator_dir: Root dir of Orchestrator module.
                Derives all paths when state_manager is not provided.
            state_manager: Pre-configured StateManager (for testing).
            lock_timeout: Lock timeout in seconds.
        """
        if state_manager is not None:
            self._sm = state_manager
        elif orchestrator_dir is not None:
            self._sm = StateManager(
                state_path=orchestrator_dir / "STATE.md",
                backup_dir=orchestrator_dir / ".backup",
                lock_path=orchestrator_dir / ".state.lock",
                health_path=orchestrator_dir / "HEALTH.md",
                changelog_path=orchestrator_dir / "CHANGELOG.md",
                mistake_path=orchestrator_dir / "MISTAKE.md",
                audit_log_path=orchestrator_dir / "ops" / "logs" / "audit.log",
                lock_timeout=lock_timeout,
            )
        else:
            raise ValueError(
                "Provide either orchestrator_dir or state_manager"
            )

    def handle_state_update(
        self, request: StateUpdateRequest
    ) -> StateUpdateResult:
        """Process a state update request.

        Verifies the request originates from the controller, then delegates
        to StateManager.update_state().

        Raises:
            UnauthorizedAccessError: If request.origin != 'controller'.
        """
        if request.origin != AUTHORIZED_ORIGIN:
            logger.warning(
                "Rejected state update from '%s' (req=%s)",
                request.origin,
                request.request_id,
            )
            raise UnauthorizedAccessError(request.origin)

        logger.info(
            "Processing state update req=%s changes=%d",
            request.request_id,
            len(request.changes),
        )
        return self._sm.update_state(request)

    def verify_state_integrity(self) -> ValidationResult:
        """Verify current STATE.md consistency.

        Returns:
            ValidationResult wrapping the VerifyResult from state_processor.
        """
        result: VerifyResult = self._sm.verify_integrity()
        return ValidationResult(
            valid=result.ok,
            errors=list(result.errors),
            warnings=list(result.warnings),
        )

    def health_check(self) -> StateHealth:
        """Return current health status of the Orchestrator state."""
        return self._sm.health_check()
