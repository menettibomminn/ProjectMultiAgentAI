"""Tests for build_context."""

from __future__ import annotations

import json

from llm.context_builder import build_context


class TestBuildContext:
    def test_system_prompt_only(self) -> None:
        msgs = build_context("You are helpful.", {"task_id": "t1"})
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are helpful."
        assert msgs[1]["role"] == "user"

    def test_with_previous_result(self) -> None:
        prev = {"status": "success", "summary": "all good", "debug": "noise"}
        msgs = build_context("sys", {"task_id": "t2"}, previous_result=prev)
        assert len(msgs) == 3
        # Previous result summary (second message)
        assert "success" in msgs[1]["content"]
        assert "all good" in msgs[1]["content"]
        # Debug noise must NOT leak
        assert "noise" not in msgs[1]["content"]

    def test_empty_prompt_omitted(self) -> None:
        msgs = build_context("", {"task_id": "t3"})
        assert msgs[0]["role"] == "user"  # no system message

    def test_none_previous_result(self) -> None:
        msgs = build_context("sys", {"task_id": "t4"}, previous_result=None)
        assert len(msgs) == 2  # system + task

    def test_excludes_metadata_noise(self) -> None:
        task = {
            "task_id": "t5",
            "type": "sheets",
            "metadata": {"timestamp": "2026-01-01T00:00:00Z"},
            "internal_id": "xyz",
            "debug_log": "verbose stuff",
        }
        msgs = build_context("sys", task)
        task_content = json.loads(msgs[1]["content"])
        assert "task_id" in task_content
        assert "type" in task_content
        assert "metadata" not in task_content
        assert "internal_id" not in task_content
        assert "debug_log" not in task_content

    def test_excludes_debug_from_previous(self) -> None:
        prev = {"status": "ok", "debug": "trace", "stack": "deep"}
        msgs = build_context("sys", {"task_id": "t6"}, previous_result=prev)
        assert "trace" not in msgs[1]["content"]
        assert "deep" not in msgs[1]["content"]
