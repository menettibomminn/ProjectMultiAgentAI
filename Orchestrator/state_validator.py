"""Validates proposed state changes before applying them."""

from __future__ import annotations

import logging

from .models import StateChangeItem, ValidationResult
from .state_processor import StateDocument

logger = logging.getLogger(__name__)

# Section name → key column used to identify rows.
_SECTION_KEY: dict[str, str] = {
    "team_status": "Team",
    "agent_status": "Agent",
    "active_locks": "Sheet ID",
    "pending_directives": "Directive ID",
    "candidate_changes": "Change ID",
}

VALID_SECTIONS = frozenset(list(_SECTION_KEY.keys()) + ["system_metrics"])


class StateValidator:
    """Validates proposed StateChangeItem list against the current state."""

    def validate_change(
        self,
        current_state: StateDocument,
        proposed_changes: list[StateChangeItem],
    ) -> ValidationResult:
        """Validate all proposed changes.

        Checks:
            - At least one change provided.
            - Section is valid (not change_history, not unknown).
            - column is non-empty.
            - For table sections: old_value matches current if row exists.
            - For system_metrics: key mismatch emits a warning.
            - No-op changes (old == new) emit a warning.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not proposed_changes:
            errors.append("No changes provided")
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        for i, change in enumerate(proposed_changes):
            prefix = f"change[{i}]"

            # Reject direct modification of change_history.
            if change.section == "change_history":
                errors.append(
                    f"{prefix}: cannot modify change_history directly "
                    "(append-only, managed internally)"
                )
                continue

            # Section must be valid.
            if change.section not in VALID_SECTIONS:
                errors.append(f"{prefix}: invalid section '{change.section}'")
                continue

            # Column must be non-empty.
            if not change.column:
                errors.append(f"{prefix}: column is empty")
                continue

            # Warn on no-op.
            if change.new_value == change.old_value:
                warnings.append(f"{prefix}: new_value == old_value (no-op)")

            # --- System metrics ---
            if change.section == "system_metrics":
                self._validate_metrics(
                    current_state, change, prefix, warnings
                )
                continue

            # --- Table sections ---
            self._validate_table_row(
                current_state, change, prefix, warnings
            )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def _validate_metrics(
        state: StateDocument,
        change: StateChangeItem,
        prefix: str,
        warnings: list[str],
    ) -> None:
        """Warn if system_metrics current value does not match old_value."""
        if change.old_value in ("—", ""):
            return
        if not state.system_metrics:
            return
        current_val = state.system_metrics.get(change.column)
        if current_val is not None and str(current_val) != change.old_value:
            warnings.append(
                f"{prefix}: system_metrics.{change.column} "
                f"current='{current_val}' != old_value='{change.old_value}'"
            )

    @staticmethod
    def _validate_table_row(
        state: StateDocument,
        change: StateChangeItem,
        prefix: str,
        warnings: list[str],
    ) -> None:
        """Warn if table row's current value does not match old_value."""
        rows = _get_section_rows(state, change.section)
        if rows is None:
            return

        key_col = _SECTION_KEY.get(change.section)
        if key_col is None or not change.field:
            return

        target_row = _find_row(rows, key_col, change.field)
        if target_row is None:
            return  # New row — no current value to compare.

        current_val = target_row.get(change.column, "—")
        if change.old_value not in ("—", "") and current_val != change.old_value:
            warnings.append(
                f"{prefix}: {change.section}.{change.field}.{change.column} "
                f"current='{current_val}' != old_value='{change.old_value}'"
            )


def _get_section_rows(
    doc: StateDocument, section: str
) -> list[dict[str, str]] | None:
    """Return the list of row dicts for the given table section."""
    mapping: dict[str, list[dict[str, str]]] = {
        "team_status": doc.teams,
        "agent_status": doc.agents,
        "active_locks": doc.active_locks,
        "pending_directives": doc.pending_directives,
        "candidate_changes": doc.candidate_changes,
    }
    return mapping.get(section)


def _find_row(
    rows: list[dict[str, str]], key_col: str, key_val: str
) -> dict[str, str] | None:
    """Find a row by key column value."""
    for row in rows:
        if row.get(key_col) == key_val:
            return row
    return None
