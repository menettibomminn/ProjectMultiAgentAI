"""StateManager — core of the Orchestrator state management.

Implements the full update sequence:
    1. Acquire lock
    2. Backup state
    3. Validate changes
    4. Apply changes
    5. Save file (atomic)
    6. Compute & log hash
    7. Update HEALTH.md
    8. Update CHANGELOG.md
    9. Release lock

On error: restore backup → log → MISTAKE.md → release lock.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .exceptions import OrchestratorError, StateValidationError
from .hash_manager import HashManager
from .models import (
    HealthStatus,
    StateChangeItem,
    StateHealth,
    StateUpdateRequest,
    StateUpdateResult,
)
from .state_lock import StateLock
from .state_processor import (
    StateChange,
    StateDocument,
    VerifyResult,
    apply_state_changes,
    backup_state as _backup_state,
    parse_state,
    render_state,
    verify_state as _verify_state,
)
from .state_validator import StateValidator

logger = logging.getLogger(__name__)


class StateManager:
    """Manages STATE.md with locking, backup, validation, and audit trail."""

    def __init__(
        self,
        state_path: Path,
        backup_dir: Path,
        lock_path: Path,
        health_path: Path,
        changelog_path: Path,
        mistake_path: Path,
        audit_log_path: Path,
        lock_timeout: float = 30.0,
    ) -> None:
        self._state_path = state_path
        self._backup_dir = backup_dir
        self._lock = StateLock(lock_path, timeout=lock_timeout)
        self._validator = StateValidator()
        self._hash_manager = HashManager(audit_log_path)
        self._health_path = health_path
        self._changelog_path = changelog_path
        self._mistake_path = mistake_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_state(self) -> StateDocument:
        """Load and parse STATE.md."""
        return parse_state(self._state_path)

    def save_state(self, doc: StateDocument) -> str:
        """Render and atomically write STATE.md. Returns the SHA-256 hash."""
        content = render_state(doc)
        state_hash = self._hash_manager.compute_hash(content)

        # Atomic write: temp file → fsync → rename.
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(self._state_path.parent), suffix=".tmp"
        )
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        Path(tmp).replace(self._state_path)

        # Write checksum companion file.
        hash_path = self._state_path.with_suffix(".md.hash")
        hash_path.write_text(state_hash + "\n", encoding="utf-8")

        return state_hash

    def backup_state(self) -> Path:
        """Create a timestamped backup of STATE.md."""
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        return _backup_state(self._state_path, self._backup_dir)

    def restore_state(self, backup_path: Path) -> None:
        """Restore STATE.md from a backup file."""
        content = backup_path.read_text(encoding="utf-8")
        self._state_path.write_text(content, encoding="utf-8")
        logger.info("State restored from %s", backup_path)

    def update_state(
        self, request: StateUpdateRequest
    ) -> StateUpdateResult:
        """Full update sequence with lock, backup, validation, and audit.

        Returns:
            StateUpdateResult with success=True or success=False + errors.
        """
        backup_path: Path | None = None
        lock_acquired = False

        try:
            # 1 — acquire lock
            self._lock.acquire_lock()
            lock_acquired = True

            # 2 — backup state
            if self._state_path.exists():
                backup_path = self.backup_state()

            # 3 — load current state & validate
            current = self.load_state()
            validation = self._validator.validate_change(
                current, request.changes
            )
            if not validation.valid:
                raise StateValidationError(validation.errors)

            # 4 — apply changes
            changes = _to_state_changes(request.changes)
            apply_state_changes(current, changes)

            # 5 — save file (atomic)
            state_hash = self.save_state(current)

            # 6 — log hash to audit
            self._hash_manager.log_hash(
                state_hash, "update", request.request_id
            )

            # 7 — update HEALTH.md
            self._append_health(HealthStatus.HEALTHY, state_hash)

            # 8 — update CHANGELOG.md
            self._append_changelog(request, len(request.changes))

            return StateUpdateResult(
                success=True,
                request_id=request.request_id,
                state_hash=state_hash,
            )

        except OrchestratorError as exc:
            self._handle_error(backup_path, request.request_id, str(exc))
            return StateUpdateResult(
                success=False,
                request_id=request.request_id,
                errors=[str(exc)],
            )

        except Exception as exc:
            self._handle_error(backup_path, request.request_id, str(exc))
            raise

        finally:
            if lock_acquired:
                self._lock.release_lock()

    def verify_integrity(self) -> VerifyResult:
        """Verify STATE.md consistency and integrity."""
        return _verify_state(self._state_path)

    def health_check(self) -> StateHealth:
        """Return current health status."""
        now = datetime.now(timezone.utc)

        try:
            if not self._state_path.exists():
                return StateHealth(
                    status=HealthStatus.DOWN,
                    last_check=now,
                    errors=["STATE.md not found"],
                )

            content = self._state_path.read_text(encoding="utf-8")
            state_hash = self._hash_manager.compute_hash(content)

            verify = self.verify_integrity()
            if not verify.ok:
                return StateHealth(
                    status=HealthStatus.DEGRADED,
                    last_check=now,
                    state_hash=state_hash,
                    errors=list(verify.errors),
                )

            doc = self.load_state()
            return StateHealth(
                status=HealthStatus.HEALTHY,
                last_check=now,
                last_update=_parse_iso(doc.last_updated),
                state_hash=state_hash,
            )

        except Exception as exc:
            return StateHealth(
                status=HealthStatus.DOWN,
                last_check=now,
                errors=[str(exc)],
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_error(
        self,
        backup_path: Path | None,
        request_id: str,
        error_msg: str,
    ) -> None:
        """Restore backup, log error, update MISTAKE.md."""
        if backup_path is not None:
            try:
                self.restore_state(backup_path)
            except Exception as restore_exc:
                logger.critical("Backup restore failed: %s", restore_exc)

        self._hash_manager.log_hash(
            "", "update", request_id, status="error", error=error_msg
        )
        self._append_mistake(request_id, error_msg)
        self._append_health(HealthStatus.DEGRADED, "", errors=[error_msg])

    def _append_health(
        self,
        status: HealthStatus,
        state_hash: str,
        errors: list[str] | None = None,
    ) -> None:
        """Append JSON entry to HEALTH.md."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status.value,
            "state_hash": state_hash,
            "errors": errors or [],
        }
        _safe_append(
            self._health_path,
            json.dumps(entry, ensure_ascii=False) + "\n",
        )

    def _append_changelog(
        self, request: StateUpdateRequest, change_count: int
    ) -> None:
        """Append markdown entry to CHANGELOG.md."""
        now = datetime.now(timezone.utc).isoformat()
        entry = (
            f"\n## [{now}] {request.request_id}\n"
            f"- **operation**: state_update\n"
            f"- **origin**: {request.origin}\n"
            f"- **changes**: {change_count}\n"
            f"- **reason**: {request.reason}\n"
        )
        _safe_append(self._changelog_path, entry)

    def _append_mistake(self, request_id: str, error_msg: str) -> None:
        """Append markdown entry to MISTAKE.md."""
        now = datetime.now(timezone.utc).isoformat()
        entry = (
            f"\n## [{now}] {request_id}\n"
            f"- **error**: {error_msg}\n"
            f"- **operation**: state_update\n"
            f"- **remediation**: Review change validity and retry\n"
        )
        _safe_append(self._mistake_path, entry)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _safe_append(path: Path, content: str) -> None:
    """Append content to file with fsync. Creates parent dirs if missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def _to_state_changes(items: list[StateChangeItem]) -> list[StateChange]:
    """Convert pydantic StateChangeItem list to dataclass StateChange list."""
    return [
        StateChange(
            section=item.section,
            field=item.field,
            column=item.column,
            old_value=item.old_value,
            new_value=item.new_value,
            reason=item.reason,
            triggered_by=item.triggered_by,
        )
        for item in items
    ]


def _parse_iso(ts: str) -> datetime | None:
    """Try to parse an ISO 8601 timestamp (handles trailing Z)."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
