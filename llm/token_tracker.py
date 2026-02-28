"""Token usage tracker — JSONL logger with optional Ralph integration."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

_DEFAULT_LOG_DIR: str = "llm"
_JSONL_FILENAME: str = "token_usage.jsonl"
_RALPH_RC: str = ".ralphrc"
_RALPH_PROGRESS: str = ".ralph/progress.txt"


@dataclass
class TokenUsage:
    """Mutable accumulator for token counts within a tracked call."""

    agent: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    _recorded: bool = field(default=False, repr=False)

    def record(self, input_tokens: int, output_tokens: int) -> None:
        """Record token counts (may be called once per context)."""
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self._recorded = True

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@contextmanager
def track_llm_call(
    agent: str,
    model: str,
    *,
    log_dir: Path | None = None,
    project_root: Path | None = None,
) -> Generator[TokenUsage, None, None]:
    """Context manager that logs token usage on exit.

    Parameters
    ----------
    agent:
        Identifier of the calling agent.
    model:
        LLM model identifier.
    log_dir:
        Directory for the JSONL file.  Defaults to ``llm/``.
    project_root:
        Project root for Ralph detection.  Defaults to cwd.
    """
    usage = TokenUsage(agent=agent, model=model)
    yield usage

    resolved_log_dir = log_dir or Path(_DEFAULT_LOG_DIR)
    resolved_root = project_root or Path.cwd()

    entry = {
        "agent": usage.agent,
        "model": usage.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Write JSONL
    try:
        resolved_log_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = resolved_log_dir / _JSONL_FILENAME
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Failed to write token JSONL: %s", exc)

    # Ralph integration
    ralph_rc = resolved_root / _RALPH_RC
    if ralph_rc.exists():
        try:
            progress_path = resolved_root / _RALPH_PROGRESS
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            line = (
                f"[{entry['timestamp']}] {agent} ({model}): "
                f"{usage.input_tokens}in/{usage.output_tokens}out "
                f"= {usage.total_tokens} tokens\n"
            )
            with open(progress_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as exc:
            logger.warning("Failed to write Ralph progress: %s", exc)
