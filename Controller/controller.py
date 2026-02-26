"""Controller — main inbox/outbox processor.

Single-run entrypoint: scans inbox for agent reports, verifies integrity,
processes them, emits directives to outbox, writes audit log, and updates
HEALTH.md.

Usage:
    python -m Controller --run-once
    python -m Controller --run-once --team sheets-team

The Controller NEVER modifies Google Sheets directly. It coordinates agents
by reading reports and emitting structured directives.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Controller.config import ControllerConfig
from Controller.health_monitor import HealthMonitor
from Controller.lock_manager import LockManager, LockError
from Controller.logger import get_logger
from Controller.retry_manager import RetryManager
from Controller.controller_audit_logger import (
    verify_report_checksum,
    write_audit_entry,
    write_hash_file,
)
from Controller.controller_report_generator import (
    generate_directive,
    generate_error_report,
    generate_processing_report,
    write_directive,
    write_report,
)
from Controller.controller_task_parser import (
    parse_report_file,
    parse_task_file,
)


class Controller:
    """Central controller that processes inbox reports and emits directives."""

    def __init__(self, config: ControllerConfig | None = None) -> None:
        self.config = config or ControllerConfig.from_env()
        self.log = get_logger(self.config.controller_id)
        self._lock_mgr = LockManager(
            locks_dir=self.config.locks_dir,
            owner=self.config.controller_id,
            timeout_seconds=self.config.lock_timeout_seconds,
            max_retries=self.config.lock_max_retries,
            backoff_base=self.config.lock_backoff_base,
        )
        self._health_monitor = HealthMonitor(self.config)
        self._retry_mgr = RetryManager(self.config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(self, team_filter: str | None = None) -> bool:
        """Process inbox reports once. Returns True on success, False on error/no work.

        Args:
            team_filter: If provided, only process reports for this team.
        """
        t0 = time.monotonic()
        op_steps: list[dict[str, Any]] = []
        task_id = f"ctrl-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        processed_reports: list[dict[str, Any]] = []
        directives_emitted: list[str] = []
        state_changes: list[dict[str, Any]] = []
        report: dict[str, Any] | None = None
        error: Exception | None = None
        locked_resources: list[str] = []

        try:
            # Step 1 — discover reports in inbox
            self._step(op_steps, "scan_inbox")
            report_files = self._scan_inbox(team_filter)

            if not report_files:
                self.log.info("No reports found in inbox — nothing to do")
                self._update_health(
                    task_id=task_id,
                    status="healthy",
                    error_count_delta=0,
                )
                return False

            self.log.info("Found %d report(s) to process", len(report_files))

            # Step 2 — process each report
            for report_path in report_files:
                team_id = self._extract_team_from_path(report_path)
                resource_id = f"inbox-{team_id}" if team_id else "inbox-global"

                # Step 2a — acquire lock for this team's inbox
                if resource_id not in locked_resources:
                    self._step(op_steps, f"acquire_lock_{resource_id}")
                    try:
                        self._lock_mgr.acquire(resource_id, task_id)
                        locked_resources.append(resource_id)
                    except LockError as exc:
                        self.log.warning(
                            "Cannot lock %s, skipping: %s", resource_id, exc
                        )
                        continue

                # Step 2b — verify report integrity
                self._step(op_steps, f"verify_{report_path.name}")
                is_valid, checksum = verify_report_checksum(report_path)
                if not is_valid:
                    self.log.warning(
                        "Report %s failed integrity check (hash: %s), skipping",
                        report_path,
                        checksum,
                    )
                    processed_reports.append({
                        "file": str(report_path.name),
                        "status": "tampered",
                        "checksum": checksum,
                    })
                    continue

                # Step 2c — parse and validate report
                self._step(op_steps, f"parse_{report_path.name}")
                result = parse_report_file(report_path)
                if not result.ok or result.data is None:
                    self.log.warning(
                        "Report %s validation failed: %s",
                        report_path,
                        result.errors,
                    )
                    processed_reports.append({
                        "file": str(report_path.name),
                        "status": "invalid",
                        "errors": result.errors,
                    })
                    continue

                report_data = result.data

                # Step 2d — process valid report
                self._step(op_steps, f"process_{report_path.name}")
                agent_name = report_data.get("agent", "unknown")
                report_task_id = report_data.get("task_id", "unknown")
                report_status = report_data.get("status", "unknown")

                processed_reports.append({
                    "file": str(report_path.name),
                    "agent": agent_name,
                    "task_id": report_task_id,
                    "status": report_status,
                    "checksum": checksum,
                })

                # Step 2d-retry — handle error/failure via RetryManager
                if report_status in ("error", "failure"):
                    report_team = team_id or "unknown"
                    if self._retry_mgr.should_retry(
                        report_task_id, agent_name
                    ):
                        entry = self._retry_mgr.record_failure(
                            report_task_id, agent_name, report_team
                        )
                        directive = self._retry_mgr.generate_retry_directive(
                            entry
                        )
                        d_path = self._retry_mgr.write_retry_directive(
                            directive, entry
                        )
                        directives_emitted.append(str(d_path.name))
                        self.log.info(
                            "Retry directive emitted for task %s (attempt %d/%d)",
                            report_task_id,
                            entry.retry_count,
                            entry.max_retries,
                        )
                    else:
                        entry = self._retry_mgr.record_failure(
                            report_task_id, agent_name, report_team
                        )
                        reason = (
                            f"Max retries ({entry.max_retries}) exhausted "
                            f"for task {report_task_id} on agent {agent_name}"
                        )
                        directive = (
                            self._retry_mgr.generate_escalation_directive(
                                entry, reason
                            )
                        )
                        d_path = self._retry_mgr.write_escalation_directive(
                            directive, entry
                        )
                        directives_emitted.append(str(d_path.name))
                        self.log.warning(
                            "Escalation emitted for task %s: %s",
                            report_task_id,
                            reason,
                        )
                elif report_status == "success":
                    self._retry_mgr.record_success(report_task_id)
                elif report_status == "needs_review":
                    # Route to candidate changes — requires human approval
                    self._handle_needs_review(
                        report_data, agent_name, report_task_id,
                        team_id or "unknown", state_changes,
                    )
                    self.log.info(
                        "Report %s from %s queued for human review",
                        report_task_id, agent_name,
                    )

                # Write hash companion file if not present
                hash_file = report_path.with_suffix(
                    report_path.suffix + ".hash"
                )
                if not hash_file.exists():
                    write_hash_file(report_path, checksum)

                # Step 2e — record state change
                state_changes.append({
                    "type": "report_processed",
                    "team": team_id or "unknown",
                    "agent": agent_name,
                    "task_id": report_task_id,
                    "status": report_status,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                # Step 2f — mark report as processed
                self._mark_processed(report_path)

                self.log.info(
                    "Processed report from %s (task %s, status=%s)",
                    agent_name,
                    report_task_id,
                    report_status,
                )

            # Step 3 — generate processing report
            self._step(op_steps, "generate_report")
            report = generate_processing_report(
                controller_id=self.config.controller_id,
                task_id=task_id,
                processed_reports=processed_reports,
                directives_emitted=directives_emitted,
                state_changes=state_changes,
                version=self.config.version,
            )

            # Step 4 — write self-report to inbox
            self._step(op_steps, "write_self_report")
            self_report_dir = (
                self.config.inbox_dir / "controller"
            )
            self_report_path = (
                self_report_dir
                / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_self_report.json"
            )
            write_report(report, self_report_path)
            self.log.info("Self-report written to %s", self_report_path)

            return len(processed_reports) > 0

        except Exception as exc:
            error = exc
            self.log.error("Unexpected error: %s", exc, exc_info=True)
            report = generate_error_report(
                task_id=task_id,
                controller_id=self.config.controller_id,
                errors=[f"Internal error: {exc}"],
            )
            return False

        finally:
            duration_ms = (time.monotonic() - t0) * 1000
            self._step(op_steps, "finalize")

            # Release all locks
            for rid in locked_resources:
                if self._lock_mgr.is_held(rid):
                    self._lock_mgr.release(rid)
                    self.log.info("Lock released for %s", rid)

            # Write audit
            try:
                audit_path = write_audit_entry(
                    audit_dir=self.config.audit_dir,
                    task_id=task_id,
                    controller_id=self.config.controller_id,
                    op_steps=op_steps,
                    processed_reports=processed_reports,
                    directives_emitted=directives_emitted,
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

            # System-wide health check
            try:
                summary = self._health_monitor.check_all()
                self._health_monitor.write_system_health_report(summary)

                # Escalate for any DOWN agents
                for down_agent in summary.down:
                    reason = f"Agent {down_agent} is DOWN"
                    from Controller.retry_manager import TaskRetryEntry
                    placeholder_entry = TaskRetryEntry(
                        task_id=f"health-{down_agent}",
                        agent=down_agent,
                        team="system",
                    )
                    esc_directive = (
                        self._retry_mgr.generate_escalation_directive(
                            placeholder_entry, reason
                        )
                    )
                    self._retry_mgr.write_escalation_directive(
                        esc_directive, placeholder_entry
                    )
                    self.log.warning(
                        "Escalation emitted: %s", reason
                    )
            except Exception as hc_exc:
                self.log.error(
                    "System health check failed: %s", hc_exc
                )

    def check_health(self) -> dict[str, Any]:
        """Run a standalone health check and return agent statuses.

        Returns a dict with overall_status and per-agent classification.
        """
        summary = self._health_monitor.check_all()
        self._health_monitor.write_system_health_report(summary)
        return {
            "overall_status": summary.overall_status,
            "healthy": summary.healthy,
            "degraded": summary.degraded,
            "down": summary.down,
            "unknown": summary.unknown,
        }

    # ------------------------------------------------------------------
    # Task-based processing
    # ------------------------------------------------------------------

    def process_task(self, task_path: Path) -> bool:
        """Process a controller task file (e.g. process_inbox command).

        Returns True on success.
        """
        result = parse_task_file(task_path)
        if not result.ok or result.data is None:
            self.log.error("Task validation failed: %s", result.errors)
            return False

        task = result.data
        skill = task["skill"]
        task_input = task.get("input", {})

        if skill == "process_inbox":
            return self.run_once(team_filter=task_input.get("team"))
        elif skill == "emit_directive":
            return self._emit_directive_from_task(task)
        elif skill == "check_health":
            health_result = self.check_health()
            self.log.info("Health check result: %s", health_result["overall_status"])
            return True
        elif skill == "review_candidate":
            return self._review_candidate(task)
        else:
            self.log.warning("Skill '%s' not yet implemented", skill)
            return False

    def _emit_directive_from_task(self, task: dict[str, Any]) -> bool:
        """Handle emit_directive skill."""
        task_input = task.get("input", {})
        directive_data = task_input.get("directive", {})

        directive = generate_directive(
            directive_id=directive_data.get(
                "directive_id",
                f"dir-{task['task_id']}",
            ),
            target_agent=directive_data.get("target_agent", "unknown"),
            command=directive_data.get("command", "noop"),
            parameters=directive_data.get("parameters", {}),
            controller_id=self.config.controller_id,
        )

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = directive["target_agent"]
        # Determine team from directive parameters or default
        team = directive_data.get("team", "default")
        directive_path = (
            self.config.outbox_dir / team / target / f"{ts}_directive.json"
        )

        write_directive(directive, directive_path)
        self.log.info("Directive written to %s", directive_path)
        return True

    # ------------------------------------------------------------------
    # Candidate review (needs_review support)
    # ------------------------------------------------------------------

    def _handle_needs_review(
        self,
        report_data: dict[str, Any],
        agent_name: str,
        task_id: str,
        team: str,
        state_changes: list[dict[str, Any]],
    ) -> None:
        """Route a needs_review report to the candidate changes queue.

        Writes a candidate change file to Controller/state/candidates/ and
        appends a state_change entry for STATE.md's Candidate Changes section.
        """
        now = datetime.now(timezone.utc)
        candidate_id = f"cand-{task_id}"

        candidate: dict[str, Any] = {
            "candidate_id": candidate_id,
            "task_id": task_id,
            "agent": agent_name,
            "team": team,
            "status": "pending_review",
            "submitted_at": now.isoformat(),
            "summary": report_data.get("summary", ""),
            "review_reasons": report_data.get("review_reasons", []),
            "risks": report_data.get("risks", []),
            "proposed_changes": report_data.get("proposed_changes", []),
        }

        # Write candidate file
        candidates_dir = self.config.state_dir / "candidates"
        candidates_dir.mkdir(parents=True, exist_ok=True)
        ts = now.strftime("%Y%m%dT%H%M%SZ")
        candidate_path = candidates_dir / f"{ts}_{candidate_id}.json"
        candidate_path.write_text(
            json.dumps(candidate, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Record state change for STATE.md
        state_changes.append({
            "type": "candidate_submitted",
            "candidate_id": candidate_id,
            "team": team,
            "agent": agent_name,
            "task_id": task_id,
            "status": "pending_review",
            "timestamp": now.isoformat(),
        })

    def _review_candidate(self, task: dict[str, Any]) -> bool:
        """Handle review_candidate skill — approve or reject a candidate change.

        Expected input:
            {
                "candidate_id": "cand-sh-001",
                "decision": "approve" | "reject",
                "reviewer": "operator-name",
                "notes": "optional review notes"
            }
        """
        task_input = task.get("input", {})
        candidate_id = task_input.get("candidate_id", "")
        decision = task_input.get("decision", "")
        reviewer = task_input.get("reviewer", "unknown")
        notes = task_input.get("notes", "")

        if not candidate_id or decision not in ("approve", "reject"):
            self.log.error(
                "review_candidate requires candidate_id and "
                "decision (approve|reject)"
            )
            return False

        # Find the candidate file
        candidates_dir = self.config.state_dir / "candidates"
        candidate_path: Path | None = None
        if candidates_dir.exists():
            for f in candidates_dir.glob(f"*_{candidate_id}.json"):
                candidate_path = f
                break

        if candidate_path is None or not candidate_path.exists():
            self.log.error("Candidate %s not found", candidate_id)
            return False

        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)

        # Update candidate status
        candidate["status"] = "approved" if decision == "approve" else "rejected"
        candidate["reviewed_at"] = now.isoformat()
        candidate["reviewer"] = reviewer
        candidate["review_notes"] = notes
        candidate_path.write_text(
            json.dumps(candidate, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if decision == "approve":
            # Emit execution directive to the original agent
            directive = generate_directive(
                directive_id=f"dir-{candidate_id}",
                target_agent=candidate.get("agent", "unknown"),
                command="execute_approved_change",
                parameters={
                    "original_task_id": candidate.get("task_id", ""),
                    "candidate_id": candidate_id,
                    "proposed_changes": candidate.get("proposed_changes", []),
                },
                controller_id=self.config.controller_id,
            )
            team = candidate.get("team", "default")
            target = candidate.get("agent", "unknown")
            ts = now.strftime("%Y%m%dT%H%M%SZ")
            d_path = (
                self.config.outbox_dir / team / target
                / f"{ts}_approved_directive.json"
            )
            write_directive(directive, d_path)
            self.log.info(
                "Candidate %s approved by %s — directive emitted to %s",
                candidate_id, reviewer, target,
            )
        else:
            self.log.info(
                "Candidate %s rejected by %s: %s",
                candidate_id, reviewer, notes,
            )

        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _scan_inbox(self, team_filter: str | None = None) -> list[Path]:
        """Find all unprocessed report JSON files in the inbox."""
        inbox = self.config.inbox_dir
        if not inbox.exists():
            return []

        report_files: list[Path] = []
        for json_file in sorted(inbox.rglob("*.json")):
            # Skip processed files, hash files, example files, self-reports
            name = json_file.name
            if name.endswith(".processed.json"):
                continue
            if name.endswith(".hash"):
                continue
            if "example" in str(json_file.relative_to(inbox)):
                continue
            if "_self_report" in name:
                continue

            # Apply team filter
            if team_filter:
                rel = json_file.relative_to(inbox)
                parts = rel.parts
                if len(parts) >= 1 and parts[0] != team_filter:
                    continue

            report_files.append(json_file)

        return report_files

    def _extract_team_from_path(self, report_path: Path) -> str | None:
        """Extract team name from inbox path structure."""
        try:
            rel = report_path.relative_to(self.config.inbox_dir)
            parts = rel.parts
            if len(parts) >= 1:
                return parts[0]
        except ValueError:
            pass
        return None

    @staticmethod
    def _mark_processed(report_path: Path) -> None:
        """Rename a report file to .processed.json (append-only — never delete)."""
        processed_name = report_path.stem + ".processed" + report_path.suffix
        processed_path = report_path.with_name(processed_name)
        report_path.rename(processed_path)

    @staticmethod
    def _step(steps: list[dict[str, Any]], name: str) -> None:
        """Append a timestamped operation step."""
        steps.append({
            "step": name,
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    def _update_health(
        self,
        task_id: str,
        status: str,
        error_count_delta: int,
    ) -> None:
        """Append a health entry to HEALTH.md."""
        health_path = self.config.health_file
        now = datetime.now(timezone.utc)

        consecutive = (
            self._read_consecutive_failures(health_path) + error_count_delta
        )
        if error_count_delta == 0:
            consecutive = 0

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
            f"| notes | auto-updated by controller.py |\n"
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
        """Count unprocessed JSON files in the inbox directory."""
        inbox = self.config.inbox_dir
        if not inbox.exists():
            return 0
        return sum(
            1
            for f in inbox.rglob("*.json")
            if not f.name.endswith(".processed.json")
            and not f.name.endswith(".hash")
            and "_self_report" not in f.name
            and "example" not in str(f)
        )
