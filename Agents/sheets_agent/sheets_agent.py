"""Sheets Worker Agent — main orchestrator.

Single-run entrypoint: reads one task from inbox, validates it, generates a
proposal report, writes audit log, updates HEALTH.md, and exits.

Usage:
    python -m Agents.sheets_agent --run-once

When GOOGLE_SHEETS_ENABLED=true, the agent also executes validated changes
against the live Google Sheets API via utils.sheets_client.SheetsClient.
Otherwise it produces proposed_changes only (default behaviour).
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
from Agents.sheets_agent.sheets_task_parser import (
    parse_task_file,
    validate_task,
)


class SheetsAgent:
    """Worker agent that processes one task per invocation."""

    def __init__(self, config: SheetsAgentConfig | None = None) -> None:
        self.config = config or SheetsAgentConfig.from_env()
        self.log = get_logger(self.config.agent_id)
        lock_backend: FileLockBackend | RedisLockBackend
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
        _from_queue = False
        _queue_adapter: Any = None

        try:
            # Step 1 — locate task
            self._step(op_steps, "locate_task")

            _queue_task: dict[str, Any] | None = None
            if self.config.redis_enabled:
                from infra.adapter_factory import get_queue_adapter
                _queue_adapter = get_queue_adapter()
                _queue_task = _queue_adapter.pop(
                    f"inbox:{self.config.team_id}"
                )
                if _queue_task is None:
                    self.log.info("No task in queue — nothing to do")
                    self._update_health(
                        task_id="none",
                        status="healthy",
                        error_count_delta=0,
                    )
                    return False
                _from_queue = True
            else:
                task_path = self.config.task_file
                if not task_path.exists():
                    self.log.info(
                        "No task found at %s — nothing to do", task_path
                    )
                    self._update_health(
                        task_id="none",
                        status="healthy",
                        error_count_delta=0,
                    )
                    return False

            # Step 2 — parse & validate
            self._step(op_steps, "parse_task")
            if _from_queue:
                assert _queue_task is not None
                result = validate_task(_queue_task)
            else:
                result = parse_task_file(self.config.task_file)

            if not result.ok or result.task is None:
                self.log.error("Task validation failed: %s", result.errors)
                if _from_queue and _queue_task is not None:
                    task_id = str(_queue_task.get("task_id", "unknown"))
                else:
                    task_id = self._extract_task_id(self.config.task_file)
                report = generate_error_report(
                    task_id=task_id,
                    agent_id=self.config.agent_id,
                    errors=result.errors,
                )
                self._write_output(report, _queue_adapter)
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

            # Step 6.5 — execute changes via Google Sheets API (if enabled)
            if self.config.google_sheets_enabled:
                self._step(op_steps, "execute_changes")
                exec_results = self._execute_changes(task)
                report["execution_results"] = exec_results
                failed = [r for r in exec_results if r["status"] == "error"]
                if failed:
                    report["status"] = "error"
                    for f in failed:
                        report["errors"].append(f["error_message"])
                    self.log.warning(
                        "Execution had %d failure(s) out of %d change(s)",
                        len(failed),
                        len(exec_results),
                    )
                else:
                    self.log.info(
                        "All %d change(s) executed successfully", len(exec_results)
                    )

            # Step 7 — write report
            self._step(op_steps, "write_report")
            self._write_output(report, _queue_adapter)

            # Step 8 — archive task (skip for queue-sourced tasks)
            if not _from_queue:
                self._step(op_steps, "archive_task")
                task_path = self.config.task_file
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
            self._write_output(report, _queue_adapter)
            return False

        except RateLimitError as exc:
            error = exc
            self.log.error("Rate limit exceeded: %s", exc)
            report = generate_error_report(
                task_id=task_id,
                agent_id=self.config.agent_id,
                errors=[f"Rate limit error: {exc}"],
            )
            self._write_output(report, _queue_adapter)
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
                self._write_output(report, _queue_adapter)
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

    def _write_output(
        self, report: dict[str, Any], queue_adapter: Any
    ) -> None:
        """Write report to queue adapter or filesystem.

        When the ``protocol`` package is available the raw *report* dict
        is wrapped in an :class:`AgentMessage` envelope before
        serialisation, producing a backward-compatible superset of the
        original format.
        """
        output = report
        try:
            from protocol.message import AgentMessage
            status = str(report.get("status", "error"))
            if status not in ("success", "error", "retry"):
                status = "error"
            msg = AgentMessage(
                status=status,
                agent=self.config.agent_id,
                action="process_task",
                data=report,
                error=str(report.get("errors", [""])[0])
                if report.get("errors") else "",
            )
            output = msg.to_dict()
        except ModuleNotFoundError:
            pass

        if queue_adapter is not None:
            queue_adapter.push(
                f"outbox:{self.config.team_id}", output
            )
            self.log.info(
                "Report pushed to outbox:%s", self.config.team_id
            )
        else:
            write_report(output, self.config.report_file)
            self.log.info(
                "Report written to %s", self.config.report_file
            )

    def _execute_changes(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute validated changes via Google Sheets API.

        Lazily imports ``utils.sheets_client`` so that the google libraries
        are only required when ``GOOGLE_SHEETS_ENABLED=true``.

        Returns a list of per-change result dicts compatible with the report
        schema (keys: op, range, status, data/updated_cells/cleared_range,
        error_code, error_message, retries_used).
        """
        from utils.sheets_client import (  # lazy import
            SheetsClient,
            SheetsClientError,
        )

        spreadsheet_id: str = task["sheet"]["spreadsheet_id"]
        results: list[dict[str, Any]] = []

        try:
            client = SheetsClient()  # uses GOOGLE_SERVICE_ACCOUNT_PATH
        except SheetsClientError as exc:
            self.log.error("Cannot initialise SheetsClient: %s", exc)
            for change in task["requested_changes"]:
                results.append({
                    "op": change["op"],
                    "range": change["range"],
                    "status": "error",
                    "error_code": exc.code,
                    "error_message": str(exc),
                    "retries_used": 0,
                })
            return results

        for change in task["requested_changes"]:
            op: str = change["op"]
            range_name: str = change["range"]
            entry: dict[str, Any] = {"op": op, "range": range_name}

            try:
                if op in ("update", "append_row"):
                    resp = client.write_range(
                        spreadsheet_id, range_name, change["values"]
                    )
                    entry["status"] = resp.status.value
                    entry["updated_cells"] = resp.updated_cells
                    entry["retries_used"] = resp.retries_used

                elif op in ("clear_range", "delete_row"):
                    resp = client.clear_range(spreadsheet_id, range_name)
                    entry["status"] = resp.status.value
                    entry["cleared_range"] = resp.cleared_range
                    entry["retries_used"] = resp.retries_used

                else:
                    entry["status"] = "error"
                    entry["error_code"] = 0
                    entry["error_message"] = f"Unsupported op: {op}"
                    entry["retries_used"] = 0

            except SheetsClientError as exc:
                entry["status"] = "error"
                entry["error_code"] = exc.code
                entry["error_message"] = str(exc)
                entry["retries_used"] = 0
                self.log.error(
                    "Sheets API error for %s %s: %s", op, range_name, exc
                )

            results.append(entry)

        return results

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
            result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return result
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _extract_task_id(task_path: Path) -> str:
        """Best-effort extraction of task_id from a potentially invalid file."""
        try:
            data = json.loads(task_path.read_text(encoding="utf-8"))
            return str(data.get("task_id", "unknown"))
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
