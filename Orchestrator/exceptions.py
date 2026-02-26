"""Custom exceptions for the Orchestrator module."""

from __future__ import annotations


class OrchestratorError(Exception):
    """Base exception for all Orchestrator errors."""


class StateValidationError(OrchestratorError):
    """Raised when state validation fails."""

    def __init__(
        self,
        errors: list[str],
        message: str = "State validation failed",
    ) -> None:
        self.errors = errors
        super().__init__(f"{message}: {'; '.join(errors)}")


class StateLockError(OrchestratorError):
    """Raised when lock acquisition or release fails."""


class StateIntegrityError(OrchestratorError):
    """Raised when state integrity check fails (hash mismatch, corruption)."""


class UnauthorizedAccessError(OrchestratorError):
    """Raised when a non-controller entity attempts state modification."""

    def __init__(self, origin: str) -> None:
        self.origin = origin
        super().__init__(f"Unauthorized state update from: {origin}")
