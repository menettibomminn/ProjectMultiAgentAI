"""Tests for Controller.resource_state_manager."""
from __future__ import annotations

import json
from pathlib import Path

from Controller.resource_state_manager import ResourceStateEntry, ResourceStateManager


class TestResourceStateEntry:
    """Test the ResourceStateEntry dataclass."""

    def test_defaults(self) -> None:
        entry = ResourceStateEntry(resource_id="r1")
        assert entry.resource_id == "r1"
        assert entry.modifying is False
        assert entry.modified_by == ""
        assert entry.timestamp == ""

    def test_custom_values(self) -> None:
        entry = ResourceStateEntry(
            resource_id="r2",
            modifying=True,
            modified_by="agent-x",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert entry.modifying is True
        assert entry.modified_by == "agent-x"


class TestResourceStateManagerPersistence:
    """Test load/save state."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state" / "resource_state.json"
        mgr = ResourceStateManager(state_file, controller_id="test")
        mgr.mark_modifying("sheet-A", "agent-1")

        # New manager loads persisted state
        mgr2 = ResourceStateManager(state_file, controller_id="test")
        assert mgr2.is_modifying("sheet-A")

    def test_load_empty_file(self, tmp_path: Path) -> None:
        state_file = tmp_path / "resource_state.json"
        state_file.write_text("{}", encoding="utf-8")
        mgr = ResourceStateManager(state_file)
        assert mgr.get_all() == {}

    def test_load_with_meta(self, tmp_path: Path) -> None:
        state_file = tmp_path / "resource_state.json"
        state_file.write_text(
            json.dumps({"_meta": {"version": 1}}), encoding="utf-8"
        )
        mgr = ResourceStateManager(state_file)
        assert mgr.get_all() == {}

    def test_load_corrupt_json(self, tmp_path: Path) -> None:
        state_file = tmp_path / "resource_state.json"
        state_file.write_text("NOT JSON", encoding="utf-8")
        mgr = ResourceStateManager(state_file)
        assert mgr.get_all() == {}

    def test_load_missing_file(self, tmp_path: Path) -> None:
        state_file = tmp_path / "nonexistent.json"
        mgr = ResourceStateManager(state_file)
        assert mgr.get_all() == {}

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        state_file = tmp_path / "deep" / "nested" / "state.json"
        mgr = ResourceStateManager(state_file)
        mgr.mark_modifying("res", "ag")
        assert state_file.exists()


class TestMarkModifying:
    """Test mark_modifying / mark_idle / is_modifying."""

    def test_mark_modifying(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = ResourceStateManager(state_file)
        mgr.mark_modifying("r1", "agent-a")
        assert mgr.is_modifying("r1") is True

    def test_mark_idle(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = ResourceStateManager(state_file)
        mgr.mark_modifying("r1", "agent-a")
        mgr.mark_idle("r1")
        assert mgr.is_modifying("r1") is False

    def test_mark_idle_unknown_resource(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = ResourceStateManager(state_file)
        mgr.mark_idle("unknown")  # should not raise
        assert mgr.is_modifying("unknown") is False

    def test_is_modifying_unknown(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = ResourceStateManager(state_file)
        assert mgr.is_modifying("nope") is False


class TestGetAll:
    """Test get_all / get_active_resources."""

    def test_get_all(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = ResourceStateManager(state_file)
        mgr.mark_modifying("r1", "a1")
        mgr.mark_modifying("r2", "a2")
        mgr.mark_idle("r1")
        all_res = mgr.get_all()
        assert len(all_res) == 2
        assert all_res["r1"].modifying is False
        assert all_res["r2"].modifying is True

    def test_get_active_resources(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = ResourceStateManager(state_file)
        mgr.mark_modifying("r1", "a1")
        mgr.mark_modifying("r2", "a2")
        mgr.mark_idle("r1")
        active = mgr.get_active_resources()
        assert len(active) == 1
        assert active[0].resource_id == "r2"

    def test_get_active_empty(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = ResourceStateManager(state_file)
        assert mgr.get_active_resources() == []


class TestRemove:
    """Test remove."""

    def test_remove_existing(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = ResourceStateManager(state_file)
        mgr.mark_modifying("r1", "a1")
        mgr.remove("r1")
        assert mgr.get_all() == {}

    def test_remove_nonexistent(self, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        mgr = ResourceStateManager(state_file)
        mgr.remove("ghost")  # should not raise
