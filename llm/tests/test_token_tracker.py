"""Tests for track_llm_call and TokenUsage."""

from __future__ import annotations

import json
from pathlib import Path

from llm.token_tracker import track_llm_call


class TestTokenTracker:
    def test_writes_jsonl(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        with track_llm_call("agent_a", "gpt-4", log_dir=log_dir) as usage:
            usage.record(100, 50)

        jsonl = log_dir / "token_usage.jsonl"
        assert jsonl.exists()
        entry = json.loads(jsonl.read_text(encoding="utf-8").strip())
        assert entry["agent"] == "agent_a"
        assert entry["model"] == "gpt-4"
        assert entry["input_tokens"] == 100
        assert entry["output_tokens"] == 50
        assert entry["total_tokens"] == 150

    def test_multiple_appends(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        for i in range(3):
            with track_llm_call(f"a{i}", "m", log_dir=log_dir) as u:
                u.record(i * 10, i * 5)

        lines = (log_dir / "token_usage.jsonl").read_text(
            encoding="utf-8"
        ).strip().splitlines()
        assert len(lines) == 3

    def test_ralph_progress_when_ralphrc_exists(self, tmp_path: Path) -> None:
        # Create .ralphrc marker
        (tmp_path / ".ralphrc").write_text("{}", encoding="utf-8")
        log_dir = tmp_path / "logs"

        with track_llm_call(
            "bot", "claude", log_dir=log_dir, project_root=tmp_path
        ) as u:
            u.record(200, 100)

        progress = tmp_path / ".ralph" / "progress.txt"
        assert progress.exists()
        text = progress.read_text(encoding="utf-8")
        assert "bot" in text
        assert "300 tokens" in text

    def test_no_ralph_progress_without_ralphrc(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        with track_llm_call(
            "bot", "claude", log_dir=log_dir, project_root=tmp_path
        ) as u:
            u.record(10, 5)

        progress = tmp_path / ".ralph" / "progress.txt"
        assert not progress.exists()

    def test_zero_tokens_default(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        with track_llm_call("x", "y", log_dir=log_dir):
            pass  # no record() call

        entry = json.loads(
            (log_dir / "token_usage.jsonl").read_text(
                encoding="utf-8"
            ).strip()
        )
        assert entry["input_tokens"] == 0
        assert entry["output_tokens"] == 0
        assert entry["total_tokens"] == 0

    def test_metadata_in_jsonl(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        with track_llm_call("bot", "gpt-4", log_dir=log_dir) as usage:
            usage.record(10, 5)
            usage.metadata["memory_keys_used"] = ["last_spreadsheet_used"]

        entry = json.loads(
            (log_dir / "token_usage.jsonl").read_text(
                encoding="utf-8"
            ).strip()
        )
        assert entry["metadata"] == {
            "memory_keys_used": ["last_spreadsheet_used"]
        }
