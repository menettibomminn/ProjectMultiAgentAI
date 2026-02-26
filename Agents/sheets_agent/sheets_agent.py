"""Sheets Worker Agent — main orchestrator.

Single-run entrypoint: reads one task from inbox, validates it, generates a
proposal report, writes audit log, updates HEALTH.md, and exits.

Usage:
    python -m Agents.sheets_agent --run-once

This agent NEVER modifies Google Sheets. It produces proposed_changes only.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Agents.sheets_agent.config import SheetsAgentConfig
from Agents.sheets_agent.lock_manager import (
    FileLockBackend,
    LockError,
    LockManager,
    RedisLockBackend,
)
from Agents.sheets_agent.logger import get_logger
from Agents.sheets_agent.rate_limiter import RateLimiter, RateLimitError
from Agents.sheets_agent.sheets_audit_logger import write_audit_entry
from Agents.sheets_agent.sheets_report_generator import (
    generate_error_report,
    generate_report,
    write_report,
)
from Agents.sheets_agent.sheets_task_parser import parse_task_file


class SheetsAgent:
    """Worker agent that processes one task per invocation."""

    def __init__(self, config: SheetsAgentConfig | None = None) -> None:
        self.config = config or SheetsAgentConfig.from_env()
        self.log = get_logger(self.config.agent_id)
        lock_backend = None
        if self.config.lock_backend == "redis":
            lock_backend = RedisLockBackend(
                redis_url=self.config.redis_url,
            )
            self.log.info("Using Redis lock backend at %s", self.config.redis_url)
        else:
            lock_backend = FileLockBackend(self.config.locks_dir)
        self._lock_mgr = LockManager(
            locks_dir=self.config.locks_dir,
            owner=self.config.agent_id,
            timeout_seconds=self.config.lock_timeout_seconds,
            max_retries=self.config.lock_max_retries,
            backoff_base=self.config.lock_backoff_base,
            backend=lock_backend,
        )
        self._rate_limiter = RateLimiter(
            state_dir=self.config.rate_state_dir,
            name="sheets-api",
            requests_per_minute=self.config.rate_requests_per_minute,
            requests_per_day=self.config.rate_requests_per_day,
            burst_size=self.config.rate_burst_size,
            max_wait_seconds=self.config.rate_max_wait_seconds,
            jitter=self.config.rate_jitter,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(self) -> bool:
        """Process a single task. Returns True on success, False on error/no task."""
        t0 = time.monotonic()
        op_steps: list[dict[str, Any]] = []
        task_id = "unknown"
        user_id = "unknown"
        team_id = self.config.team_id
        spreadsheet_id: str | None = None
        report: dict[str, Any] | None = None
        error: Exception | None = None

        try:
            # Step 1 — locate task
            self._step(op_steps, "locate_task")
            task_path = self.config.task_file
            if not task_path.exists():
                self.log.info("No task found at %s — nothing to do", task_path)
                self._update_health(
                    task_id="none",
                    status="healthy",
                    error_count_delta=0,
                )
                return False

            # Step 2 — parse & validate
            self._step(op_steps, "parse_task")
            result = parse_task_file(task_path)
            if not result.ok or result.task is None:
                self.log.error("Task validation failed: %s", result.errors)
                task_id = self._extract_task_id(task_path)
                report = generate_error_report(
                    task_id=task_id,
                    agent_id=self.config.agent_id,
                    errors=result.errors,
                )
                write_report(report, self.config.report_file)
                self._step(op_steps, "write_error_report")
                return False

            task = result.task
            task_id = task["task_id"]
            user_id = task["user_id"]
            team_id = task.get("team_id", self.config.team_id)
            spreadsheet_id = task["sheet"]["spreadsheet_id"]

            # Update logger context
            self.log = get_logger(self.config.agent_id, task_id)
            self.log.info("Processing task %s", task_id)

            # Step 3 — idempotency check
            self._step(op_steps, "idempotency_check")
            if self.config.report_file.exists():
                existing = self._read_json(self.config.report_file)
                if existing and existing.get("task_id") == task_id:
                    self.log.info("Report already exists for task %s — skipping", task_id)
                    return True

            # Step 4 — acquire lock
            self._step(op_steps, "acquire_lock")
            self._lock_mgr.acquire(spreadsheet_id, task_id)
            self.log.info("Lock acquired for spreadsheet %s", spreadsheet_id)

            # Step 5 — rate limit check
            self._step(op_steps, "rate_limit_check")
            self._rate_limiter.acquire()
            self.log.info("Rate limit passed — slot acquired")

            # Step 6 — generate report
            self._step(op_steps, "generate_report")
            report = generate_report(
                task=task,
                agent_id=self.config.agent_id,
                version=self.config.version,
            )

            # Step 7 — write report
            self._step(op_steps, "write_report")
            write_report(report, self.config.report_file)
            self.log.info("Report written to %s", self.config.report_file)

            # Step 8 — archive task (rename to task.done.json)
            self._step(op_steps, "archive_task")
            done_path = task_path.with_suffix(".done.json")
            task_path.rename(done_path)

            self.log.info("Task %s completed successfully", task_id)
            return True

        except LockError as exc:
            error = exc
            self.log.error("Lock acquisition failed: %s", exc)
            report = generate_error_report(
                task_id=task_id,
                agent_id=self.config.agent_id,
                errors=[f"Lock error: {exc}"],
            )
            write_report(report, self.config.report_file)
            return False

        except RateLimitError as exc:
            error = exc
            self.log.error("Rate limit exceeded: %s", exc)
            report = generate_error_report(
                task_id=task_id,
                agent_id=self.config.agent_id,
                errors=[f"Rate limit error: {exc}"],
            )
            write_report(report, self.config.report_file)
            return False

        except Exception as exc:
            error = exc
            self.log.error("Unexpected error: %s", exc, exc_info=True)
            report = generate_error_report(
                task_id=task_id,
                agent_id=self.config.agent_id,
                errors=[f"Internal error: {exc}"],
            )
            try:
                write_report(report, self.config.report_file)
            except OSError:
                pass
            return False

        finally:
            duration_ms = (time.monotonic() - t0) * 1000
            self._step(op_steps, "finalize")

            # Release lock
            if spreadsheet_id and self._lock_mgr.is_held(spreadsheet_id):
                self._lock_mgr.release(spreadsheet_id)
                self.log.info("Lock released for %s", spreadsheet_id)

            # Write audit
            try:
                audit_path = write_audit_entry(
                    audit_dir=self.config.audit_dir,
                    task_id=task_id,
                    agent_id=self.config.agent_id,
                    user_id=user_id,
                    team_id=team_id,
                    config_version=self.config.version,
                    op_steps=op_steps,
                    report=report,
                    error=error,
                    duration_ms=duration_ms,
                )
                self.log.info("Audit written to %s", audit_path)
            except OSError as exc:
                self.log.error("Failed to write audit: %s", exc)

            # Update health
            self._update_health(
                task_id=task_id,
                status="healthy" if error is None else "degraded",
                error_count_delta=1 if error else 0,
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _step(steps: list[dict[str, Any]], name: str) -> None:
        """Append a timestamped operation step."""
        steps.append({
            "step": name,
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _extract_task_id(task_path: Path) -> str:
        """Best-effort extraction of task_id from a potentially invalid file."""
        try:
            data = json.loads(task_path.read_text(encoding="utf-8"))
            return data.get("task_id", "unknown")
        except Exception:
            return "unknown"

    def _update_health(
        self,
        task_id: str,
        status: str,
        error_count_delta: int,
    ) -> None:
        """Append a health entry to HEALTH.md."""
        health_path = self.config.health_file
        now = datetime.now(timezone.utc)

        # Read current consecutive failures
        consecutive = self._read_consecutive_failures(health_path) + error_count_delta
        if error_count_delta == 0:
            consecutive = 0

        # Estimate queue length
        queue_len = self._count_inbox_files()

        entry = (
            f"\n### {now.isoformat()} — Task {task_id}\n"
            f"\n"
            f"| Field | Value |\n"
            f"|---|---|\n"
            f"| last_run_timestamp | {now.isoformat()} |\n"
            f"| last_task_id | {task_id} |\n"
            f"| last_status | {status} |\n"
            f"| consecutive_failures | {consecutive} |\n"
            f"| version | {self.config.version} |\n"
            f"| queue_length_estimate | {queue_len} |\n"
            f"| notes | auto-updated by sheets_agent.py |\n"
        )

        try:
            with open(health_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except OSError as exc:
            self.log.error("Cannot update HEALTH.md: %s", exc)

    @staticmethod
    def _read_consecutive_failures(health_path: Path) -> int:
        """Parse the last consecutive_failures value from HEALTH.md."""
        if not health_path.exists():
            return 0
        try:
            text = health_path.read_text(encoding="utf-8")
            # Search from the end for the pattern
            for line in reversed(text.splitlines()):
                if "consecutive_failures" in line and "|" in line:
                    parts = line.split("|")
                    for part in parts:
                        stripped = part.strip()
                        if stripped.isdigit():
                            return int(stripped)
        except OSError:
            pass
        return 0

    def _count_inbox_files(self) -> int:
        """Count JSON files in the inbox directory."""
        inbox = self.config.inbox_dir
        if not inbox.exists():
            return 0
        return sum(
            1 for f in inbox.iterdir()
            if f.suffix == ".json" and f.name != "report.json"
        )
