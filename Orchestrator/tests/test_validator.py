"""Tests for StateValidator."""

from __future__ import annotations

from pathlib import Path

import pytest

from Orchestrator.models import StateChangeItem
from Orchestrator.state_processor import StateDocument, parse_state
from Orchestrator.state_validator import StateValidator


@pytest.fixture()
def validator() -> StateValidator:
    return StateValidator()


@pytest.fixture()
def sample_doc(state_file: Path) -> StateDocument:
    return parse_state(state_file)


class TestValidChanges:
    def test_valid_agent_update(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="agent_status",
                field="sheets-agent",
                column="Status",
                old_value="idle",
                new_value="active",
                reason="Task assigned",
                triggered_by="ctrl-001",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert result.valid

    def test_valid_team_update(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="team_status",
                field="sheets-team",
                column="Status",
                old_value="idle",
                new_value="active",
                reason="Cycle start",
                triggered_by="ctrl-001",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert result.valid

    def test_valid_system_metrics(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="system_metrics",
                field="",
                column="total_tasks_completed",
                old_value="5",
                new_value="10",
                reason="Cycle update",
                triggered_by="ctrl-002",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert result.valid

    def test_new_agent_valid(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="agent_status",
                field="metrics-agent",
                column="Status",
                old_value="—",
                new_value="idle",
                reason="Registered",
                triggered_by="ctrl-003",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert result.valid

    def test_lock_section_valid(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="active_locks",
                field="sheet-abc",
                column="Owner",
                old_value="—",
                new_value="sheets-agent",
                reason="Lock acquired",
                triggered_by="ctrl-004",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert result.valid

    def test_directive_section_valid(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="pending_directives",
                field="dir-001",
                column="Status",
                old_value="—",
                new_value="pending",
                reason="New directive",
                triggered_by="ctrl-005",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert result.valid

    def test_candidate_changes_valid(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="candidate_changes",
                field="chg-001",
                column="Status",
                old_value="—",
                new_value="pending",
                reason="New candidate",
                triggered_by="ctrl-006",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert result.valid


class TestInvalidChanges:
    def test_invalid_section(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="nonexistent_section",
                field="x",
                column="y",
                old_value="a",
                new_value="b",
                reason="test",
                triggered_by="test",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert not result.valid
        assert "invalid section" in result.errors[0]

    def test_change_history_rejected(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="change_history",
                field="x",
                column="y",
                old_value="a",
                new_value="b",
                reason="test",
                triggered_by="test",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert not result.valid
        assert "change_history" in result.errors[0]

    def test_empty_column_rejected(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="agent_status",
                field="sheets-agent",
                column="",
                old_value="idle",
                new_value="active",
                reason="test",
                triggered_by="test",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert not result.valid
        assert "column is empty" in result.errors[0]

    def test_no_changes_rejected(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        result = validator.validate_change(sample_doc, [])
        assert not result.valid
        assert "No changes" in result.errors[0]

    def test_multiple_errors(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="bad_section",
                field="x",
                column="y",
                old_value="",
                new_value="z",
                reason="test",
                triggered_by="test",
            ),
            StateChangeItem(
                section="change_history",
                field="x",
                column="y",
                old_value="",
                new_value="z",
                reason="test",
                triggered_by="test",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert not result.valid
        assert len(result.errors) == 2


class TestWarnings:
    def test_old_value_mismatch_warns(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="agent_status",
                field="sheets-agent",
                column="Status",
                old_value="active",  # Actual is "idle".
                new_value="error",
                reason="test",
                triggered_by="test",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert result.valid  # Mismatch is a warning, not error.
        assert len(result.warnings) > 0
        assert "current=" in result.warnings[0]

    def test_noop_change_warns(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="agent_status",
                field="sheets-agent",
                column="Status",
                old_value="idle",
                new_value="idle",
                reason="test",
                triggered_by="test",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert result.valid
        assert any("no-op" in w for w in result.warnings)

    def test_system_metrics_old_value_mismatch_warns(
        self, validator: StateValidator, sample_doc: StateDocument
    ) -> None:
        changes = [
            StateChangeItem(
                section="system_metrics",
                field="",
                column="total_tasks_completed",
                old_value="99",  # Actual is 5.
                new_value="100",
                reason="test",
                triggered_by="test",
            ),
        ]
        result = validator.validate_change(sample_doc, changes)
        assert result.valid
        assert len(result.warnings) > 0
