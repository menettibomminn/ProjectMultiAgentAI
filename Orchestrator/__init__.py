"""Orchestrator — Single Source of Truth manager for ProjectMultiAgentAI."""

__version__ = "2.0.0"

from .exceptions import (
    OrchestratorError,
    StateIntegrityError,
    StateLockError,
    StateValidationError,
    UnauthorizedAccessError,
)
from .models import (
    HealthStatus,
    StateChangeItem,
    StateHealth,
    StateUpdateRequest,
    StateUpdateResult,
    ValidationResult,
)
from .orchestrator import Orchestrator
from .state_manager import StateManager

__all__ = [
    "HealthStatus",
    "Orchestrator",
    "OrchestratorError",
    "StateChangeItem",
    "StateHealth",
    "StateIntegrityError",
    "StateLockError",
    "StateManager",
    "StateUpdateRequest",
    "StateUpdateResult",
    "StateValidationError",
    "UnauthorizedAccessError",
    "ValidationResult",
]
