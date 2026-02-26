"""Tests for Controller.state_store."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from Controller.state_store import (
    StateStoreError,
    atomic_write,
    load_json,
    save_json,
)


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


class TestSaveJson:
    def test_creates_file(self, state_dir: Path) -> None:
        path = state_dir / "data.json"
        save_json(path, {"key": "value"})
        assert path.exists()

    def test_creates_parent_dirs(self, state_dir: Path) -> None:
        path = state_dir / "nested" / "deep" / "data.json"
        save_json(path, [1, 2, 3])
        assert path.exists()

    def test_correct_content(self, state_dir: Path) -> None:
        path = state_dir / "data.json"
        save_json(path, {"a": 1, "b": [2, 3]})
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"a": 1, "b": [2, 3]}

    def test_overwrites_existing(self, state_dir: Path) -> None:
        path = state_dir / "data.json"
        save_json(path, {"v": 1})
        save_json(path, {"v": 2})
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"v": 2}


class TestLoadJson:
    def test_load_existing(self, state_dir: Path) -> None:
        path = state_dir / "data.json"
        state_dir.mkdir(parents=True, exist_ok=True)
        path.write_text('{"x": 42}', encoding="utf-8")
        assert load_json(path) == {"x": 42}

    def test_load_missing_returns_default(self, state_dir: Path) -> None:
        path = state_dir / "missing.json"
        assert load_json(path) is None

    def test_load_missing_with_custom_default(self, state_dir: Path) -> None:
        path = state_dir / "missing.json"
        assert load_json(path, default={}) == {}

    def test_load_corrupt_returns_default(self, state_dir: Path) -> None:
        path = state_dir / "corrupt.json"
        state_dir.mkdir(parents=True, exist_ok=True)
        path.write_text("not json{{", encoding="utf-8")
        assert load_json(path, default={"fallback": True}) == {"fallback": True}


class TestAtomicWrite:
    def test_basic_write(self, state_dir: Path) -> None:
        path = state_dir / "atomic.json"
        atomic_write(path, {"atomic": True})
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"atomic": True}

    def test_no_temp_files_left(self, state_dir: Path) -> None:
        path = state_dir / "clean.json"
        atomic_write(path, {"data": 1})
        tmp_files = list(state_dir.glob(".*_*.tmp"))
        assert len(tmp_files) == 0

    def test_replaces_existing(self, state_dir: Path) -> None:
        path = state_dir / "replace.json"
        atomic_write(path, {"v": "old"})
        atomic_write(path, {"v": "new"})
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"v": "new"}

    def test_unicode_content(self, state_dir: Path) -> None:
        path = state_dir / "unicode.json"
        atomic_write(path, {"name": "Caf\u00e9 \u2615"})
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["name"] == "Caf\u00e9 \u2615"

    def test_invalid_path_raises(self, state_dir: Path) -> None:
        # Path with null byte is invalid
        with pytest.raises((StateStoreError, OSError, ValueError)):
            atomic_write(state_dir / "inv\x00alid.json", {})
