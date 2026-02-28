"""Unit tests for FSAdapter — uses real filesystem via tmp_path."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from infra.fs_adapter import FSAdapter


class TestPush:
    """Verify push creates a JSON file in the queue directory."""

    def test_push_creates_file(self, tmp_path: Path) -> None:
        adapter = FSAdapter(base_dir=tmp_path)
        adapter.push("inbox", {"task_id": "t1"})

        queue_dir = tmp_path / "inbox"
        files = list(queue_dir.glob("*.json"))
        assert len(files) == 1

        data: dict[str, Any] = json.loads(
            files[0].read_text(encoding="utf-8")
        )
        assert data["task_id"] == "t1"

    def test_push_multiple_creates_ordered_files(
        self, tmp_path: Path
    ) -> None:
        adapter = FSAdapter(base_dir=tmp_path)
        for i in range(3):
            adapter.push("q", {"i": i})

        files = sorted((tmp_path / "q").glob("*.json"))
        assert len(files) == 3

    def test_push_sanitises_queue_name(self, tmp_path: Path) -> None:
        adapter = FSAdapter(base_dir=tmp_path)
        adapter.push("inbox:sheets:agent-01", {"ok": True})

        # colons replaced with underscores
        dirs = [d.name for d in tmp_path.iterdir() if d.is_dir()]
        assert "inbox_sheets_agent-01" in dirs


class TestPop:
    """Verify pop returns oldest item and removes the file."""

    def test_pop_returns_oldest(self, tmp_path: Path) -> None:
        adapter = FSAdapter(base_dir=tmp_path)
        adapter.push("q", {"order": 1})
        adapter.push("q", {"order": 2})

        first = adapter.pop("q", timeout=0)
        assert first is not None
        assert first["order"] == 1

    def test_pop_removes_file(self, tmp_path: Path) -> None:
        adapter = FSAdapter(base_dir=tmp_path)
        adapter.push("q", {"x": 1})

        adapter.pop("q", timeout=0)
        files = list((tmp_path / "q").glob("*.json"))
        assert len(files) == 0

    def test_pop_empty_returns_none(self, tmp_path: Path) -> None:
        adapter = FSAdapter(base_dir=tmp_path)
        result = adapter.pop("empty", timeout=0)
        assert result is None

    def test_pop_nonexistent_queue_returns_none(
        self, tmp_path: Path
    ) -> None:
        adapter = FSAdapter(base_dir=tmp_path)
        assert adapter.pop("nope", timeout=0) is None


class TestRoundTrip:
    """Push then pop — verify data integrity."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        adapter = FSAdapter(base_dir=tmp_path)
        original: dict[str, Any] = {
            "task_id": "rt-001",
            "values": [["a", "b"]],
            "unicode": "caffè",
        }
        adapter.push("q", original)
        result = adapter.pop("q", timeout=0)
        assert result == original


class TestProtocol:
    """Verify FSAdapter satisfies QueueAdapter protocol."""

    def test_is_queue_adapter(self, tmp_path: Path) -> None:
        from infra import QueueAdapter

        adapter = FSAdapter(base_dir=tmp_path)
        assert isinstance(adapter, QueueAdapter)
