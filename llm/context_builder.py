"""Context slicing — build minimal LLM context for agent calls."""

from __future__ import annotations

from typing import Any

# Only these task keys survive into the LLM context.
_TASK_ALLOWED_KEYS: frozenset[str] = frozenset({
    "task_id", "type", "user_id", "team_id",
    "sheet", "requested_changes", "description",
    "command", "parameters",
})


def build_context(
    system_prompt: str,
    task: dict[str, Any],
    previous_result: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build a minimal message list for an LLM call.

    Parameters
    ----------
    system_prompt:
        The system-level instruction.  Omitted from the output when empty.
    task:
        The current task dict.  Only essential fields are kept.
    previous_result:
        Optional result from a prior agent step.  Only ``status`` and
        ``summary`` are forwarded.

    Returns
    -------
    list[dict[str, str]]
        A list of ``{"role": ..., "content": ...}`` message dicts ready
        for any chat-completion API.
    """
    messages: list[dict[str, str]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if previous_result is not None:
        summary = _extract_summary(previous_result)
        if summary:
            messages.append({"role": "user", "content": summary})

    messages.append({"role": "user", "content": _format_task(task)})
    return messages


def _extract_summary(result: dict[str, Any]) -> str:
    """Extract only ``status`` and ``summary`` from a previous result."""
    parts: list[str] = []
    status = result.get("status")
    if status is not None:
        parts.append(f"Previous status: {status}")
    summary = result.get("summary")
    if summary is not None:
        parts.append(f"Summary: {summary}")
    return "\n".join(parts)


def _format_task(task: dict[str, Any]) -> str:
    """Serialise *task* keeping only allowed keys."""
    import json
    filtered = {k: v for k, v in task.items() if k in _TASK_ALLOWED_KEYS}
    return json.dumps(filtered, ensure_ascii=False, indent=2)
