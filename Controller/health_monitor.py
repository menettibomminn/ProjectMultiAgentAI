"""Health monitoring for all agents in the system.

Reads HEALTH.md files from each agent, classifies their status
(healthy/degraded/down/unknown), and produces a system-level health summary.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Controller.config import ControllerConfig
from Controller.logger import get_logger


@dataclass
class AgentHealthSnapshot:
    """Parsed health state for a single agent."""

    agent_name: str
    last_run_timestamp: datetime | None = None
    last_status: str = "unknown"
    consecutive_failures: int = 0


@dataclass
class SystemHealthSummary:
    """Aggregated health state for the entire system."""

    timestamp: str = ""
    agents: dict[str, AgentHealthSnapshot] = field(default_factory=dict)
    healthy: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    down: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    overall_status: str = "unknown"


class HealthMonitor:
    """Monitor health of all registered agents by reading their HEALTH.md files."""

    def __init__(self, config: ControllerConfig) -> None:
        self.config = config
        self.log = get_logger(f"{config.controller_id}.health")

    def check_all(self) -> SystemHealthSummary:
        """Read all agent HEALTH.md files and produce a system health summary."""
        now = datetime.now(timezone.utc)
        summary = SystemHealthSummary(timestamp=now.isoformat())

        for agent_name, health_path_str in self.config.agent_health_paths.items():
            abs_path = self.config.project_root / health_path_str
            snapshot = self._parse_agent_health(agent_name, abs_path)
            classification = self._classify_agent(snapshot, now)
            summary.agents[agent_name] = snapshot

            if classification == "healthy":
                summary.healthy.append(agent_name)
            elif classification == "degraded":
                summary.degraded.append(agent_name)
            elif classification == "down":
                summary.down.append(agent_name)
            else:
                summary.unknown.append(agent_name)

        # Overall status: worst-case among all agents
        if summary.down:
            summary.overall_status = "down"
        elif summary.degraded:
            summary.overall_status = "degraded"
        elif summary.healthy:
            summary.overall_status = "healthy"
        else:
            summary.overall_status = "unknown"

        return summary

    def _parse_agent_health(self, name: str, path: Path) -> AgentHealthSnapshot:
        """Parse the last entry from an agent's HEALTH.md."""
        snapshot = AgentHealthSnapshot(agent_name=name)

        if not path.exists():
            self.log.warning("HEALTH.md not found for %s at %s", name, path)
            return snapshot

        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.log.error("Cannot read HEALTH.md for %s: %s", name, exc)
            return snapshot

        # Parse the last markdown table in the file
        last_values = self._extract_last_table_values(text)
        if not last_values:
            return snapshot

        # Extract fields
        ts_raw = last_values.get("last_run_timestamp", "")
        if ts_raw:
            snapshot.last_run_timestamp = self._parse_timestamp(ts_raw)

        snapshot.last_status = last_values.get("last_status", "unknown")

        failures_raw = last_values.get("consecutive_failures", "0")
        try:
            snapshot.consecutive_failures = int(failures_raw)
        except ValueError:
            snapshot.consecutive_failures = 0

        return snapshot

    def _classify_agent(
        self, snapshot: AgentHealthSnapshot, now: datetime
    ) -> str:
        """Classify agent as healthy/degraded/down/unknown."""
        # No timestamp means we have no data
        if snapshot.last_run_timestamp is None:
            return "unknown"

        silence_seconds = (now - snapshot.last_run_timestamp).total_seconds()
        failures = snapshot.consecutive_failures

        # Failure-based classification
        if failures >= self.config.health_down_failures:
            return "down"
        if failures >= self.config.health_degraded_failures:
            return "degraded"

        # Silence-based classification
        if silence_seconds >= self.config.health_down_timeout_seconds:
            return "down"
        if silence_seconds >= self.config.health_check_timeout_seconds:
            return "degraded"

        return "healthy"

    def write_system_health_report(self, summary: SystemHealthSummary) -> Path:
        """Write the system health summary as JSON to state dir."""
        out_path = self.config.system_health_file
        out_path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "timestamp": summary.timestamp,
            "overall_status": summary.overall_status,
            "healthy": summary.healthy,
            "degraded": summary.degraded,
            "down": summary.down,
            "unknown": summary.unknown,
            "agents": {
                name: {
                    "agent_name": s.agent_name,
                    "last_run_timestamp": (
                        s.last_run_timestamp.isoformat()
                        if s.last_run_timestamp
                        else None
                    ),
                    "last_status": s.last_status,
                    "consecutive_failures": s.consecutive_failures,
                }
                for name, s in summary.agents.items()
            },
        }

        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(out_path)
        self.log.info("System health report written to %s", out_path)
        return out_path

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_last_table_values(text: str) -> dict[str, str]:
        """Extract key-value pairs from the last markdown table in text.

        Expects rows like: | key | value |
        """
        values: dict[str, str] = {}
        # Find all table rows (lines matching | something | something |)
        row_pattern = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|", re.MULTILINE)

        # Track sections — each "###" header resets the current table
        current_table: dict[str, str] = {}
        in_table = False

        for line in text.splitlines():
            line_stripped = line.strip()
            if line_stripped.startswith("###"):
                # New section — save previous table and reset
                if current_table:
                    values = current_table
                current_table = {}
                in_table = False
                continue

            m = row_pattern.match(line_stripped)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                # Skip header and separator rows
                if key == "Field" or key.startswith("---"):
                    continue
                current_table[key] = val
                in_table = True
            elif in_table and not line_stripped.startswith("|"):
                in_table = False

        # Don't forget the last section
        if current_table:
            values = current_table

        return values

    @staticmethod
    def _parse_timestamp(raw: str) -> datetime | None:
        """Parse an ISO 8601 timestamp string."""
        raw = raw.strip()
        if not raw or raw == "none":
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            # Try with Z suffix
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return None
