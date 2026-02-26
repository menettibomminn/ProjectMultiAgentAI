"""Tests for Controller.health_monitor."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


from Controller.config import ControllerConfig
from Controller.health_monitor import (
    AgentHealthSnapshot,
    HealthMonitor,
)


class TestParseAgentHealth:
    """Test _parse_agent_health with various HEALTH.md formats."""

    def _make_monitor(self, tmp_path: Path) -> HealthMonitor:
        config = ControllerConfig(
            controller_id="test",
            project_root=tmp_path,
            agent_health_paths={},
        )
        return HealthMonitor(config)

    def test_parse_standard_health(self, tmp_path: Path) -> None:
        """Parse a standard HEALTH.md with one entry."""
        monitor = self._make_monitor(tmp_path)
        health = tmp_path / "HEALTH.md"
        health.write_text(
            "# HEALTH\n\n"
            "### 2026-02-24T12:00:00+00:00 — Task t-001\n\n"
            "| Field | Value |\n"
            "|---|---|\n"
            "| last_run_timestamp | 2026-02-24T12:00:00+00:00 |\n"
            "| last_task_id | t-001 |\n"
            "| last_status | healthy |\n"
            "| consecutive_failures | 0 |\n",
            encoding="utf-8",
        )
        snap = monitor._parse_agent_health("test-agent", health)
        assert snap.agent_name == "test-agent"
        assert snap.last_status == "healthy"
        assert snap.consecutive_failures == 0
        assert snap.last_run_timestamp is not None

    def test_parse_multiple_entries_takes_last(self, tmp_path: Path) -> None:
        """When multiple entries exist, parse the last one."""
        monitor = self._make_monitor(tmp_path)
        health = tmp_path / "HEALTH.md"
        health.write_text(
            "# HEALTH\n\n"
            "### 2026-02-24T10:00:00+00:00 — Task t-001\n\n"
            "| Field | Value |\n"
            "|---|---|\n"
            "| last_run_timestamp | 2026-02-24T10:00:00+00:00 |\n"
            "| last_status | healthy |\n"
            "| consecutive_failures | 0 |\n\n"
            "### 2026-02-24T12:00:00+00:00 — Task t-002\n\n"
            "| Field | Value |\n"
            "|---|---|\n"
            "| last_run_timestamp | 2026-02-24T12:00:00+00:00 |\n"
            "| last_status | degraded |\n"
            "| consecutive_failures | 3 |\n",
            encoding="utf-8",
        )
        snap = monitor._parse_agent_health("test-agent", health)
        assert snap.last_status == "degraded"
        assert snap.consecutive_failures == 3

    def test_parse_missing_file(self, tmp_path: Path) -> None:
        """Missing HEALTH.md returns unknown snapshot."""
        monitor = self._make_monitor(tmp_path)
        snap = monitor._parse_agent_health(
            "ghost-agent", tmp_path / "nonexistent.md"
        )
        assert snap.agent_name == "ghost-agent"
        assert snap.last_run_timestamp is None
        assert snap.last_status == "unknown"

    def test_parse_empty_file(self, tmp_path: Path) -> None:
        """Empty HEALTH.md returns unknown snapshot."""
        monitor = self._make_monitor(tmp_path)
        health = tmp_path / "HEALTH.md"
        health.write_text("# HEALTH\n\nNo entries yet.\n", encoding="utf-8")
        snap = monitor._parse_agent_health("empty-agent", health)
        assert snap.last_run_timestamp is None

    def test_parse_z_suffix_timestamp(self, tmp_path: Path) -> None:
        """Timestamps with Z suffix are parsed correctly."""
        monitor = self._make_monitor(tmp_path)
        health = tmp_path / "HEALTH.md"
        health.write_text(
            "# HEALTH\n\n"
            "### 2026-02-24T12:00:00Z — Task t-001\n\n"
            "| Field | Value |\n"
            "|---|---|\n"
            "| last_run_timestamp | 2026-02-24T12:00:00Z |\n"
            "| last_status | healthy |\n"
            "| consecutive_failures | 0 |\n",
            encoding="utf-8",
        )
        snap = monitor._parse_agent_health("z-agent", health)
        assert snap.last_run_timestamp is not None


class TestClassifyAgent:
    """Test _classify_agent classification logic."""

    def _make_monitor(self, tmp_path: Path) -> HealthMonitor:
        config = ControllerConfig(
            controller_id="test",
            project_root=tmp_path,
            agent_health_paths={},
            health_check_timeout_seconds=600,
            health_down_timeout_seconds=1800,
            health_degraded_failures=3,
            health_down_failures=6,
        )
        return HealthMonitor(config)

    def test_healthy_agent(self, tmp_path: Path) -> None:
        now = datetime.now(timezone.utc)
        snap = AgentHealthSnapshot(
            agent_name="ok-agent",
            last_run_timestamp=now - timedelta(seconds=60),
            last_status="healthy",
            consecutive_failures=0,
        )
        monitor = self._make_monitor(tmp_path)
        assert monitor._classify_agent(snap, now) == "healthy"

    def test_degraded_by_failures(self, tmp_path: Path) -> None:
        now = datetime.now(timezone.utc)
        snap = AgentHealthSnapshot(
            agent_name="fail-agent",
            last_run_timestamp=now - timedelta(seconds=60),
            last_status="degraded",
            consecutive_failures=3,
        )
        monitor = self._make_monitor(tmp_path)
        assert monitor._classify_agent(snap, now) == "degraded"

    def test_down_by_failures(self, tmp_path: Path) -> None:
        now = datetime.now(timezone.utc)
        snap = AgentHealthSnapshot(
            agent_name="dead-agent",
            last_run_timestamp=now - timedelta(seconds=60),
            last_status="down",
            consecutive_failures=6,
        )
        monitor = self._make_monitor(tmp_path)
        assert monitor._classify_agent(snap, now) == "down"

    def test_degraded_by_silence(self, tmp_path: Path) -> None:
        now = datetime.now(timezone.utc)
        snap = AgentHealthSnapshot(
            agent_name="silent-agent",
            last_run_timestamp=now - timedelta(seconds=700),
            last_status="healthy",
            consecutive_failures=0,
        )
        monitor = self._make_monitor(tmp_path)
        assert monitor._classify_agent(snap, now) == "degraded"

    def test_down_by_silence(self, tmp_path: Path) -> None:
        now = datetime.now(timezone.utc)
        snap = AgentHealthSnapshot(
            agent_name="gone-agent",
            last_run_timestamp=now - timedelta(seconds=2000),
            last_status="healthy",
            consecutive_failures=0,
        )
        monitor = self._make_monitor(tmp_path)
        assert monitor._classify_agent(snap, now) == "down"

    def test_unknown_no_timestamp(self, tmp_path: Path) -> None:
        snap = AgentHealthSnapshot(agent_name="new-agent")
        monitor = self._make_monitor(tmp_path)
        now = datetime.now(timezone.utc)
        assert monitor._classify_agent(snap, now) == "unknown"


class TestCheckAll:
    """Test check_all with temporary HEALTH.md files."""

    def test_check_all_mixed(self, test_config_with_health: ControllerConfig) -> None:
        """check_all with a mix of healthy and degraded agents."""
        monitor = HealthMonitor(test_config_with_health)
        summary = monitor.check_all()

        # backend-agent has 4 failures → degraded
        assert "backend-agent" in summary.degraded
        # sheets-agent and auth-agent should be healthy or degraded depending
        # on how recently they ran (fixture uses a fixed timestamp)
        assert summary.overall_status in ("healthy", "degraded")
        assert len(summary.agents) == 3

    def test_write_system_health_report(
        self, test_config_with_health: ControllerConfig
    ) -> None:
        """write_system_health_report creates a valid JSON file."""
        monitor = HealthMonitor(test_config_with_health)
        summary = monitor.check_all()
        path = monitor.write_system_health_report(summary)

        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "overall_status" in data
        assert "agents" in data
        assert isinstance(data["healthy"], list)

    def test_overall_status_all_healthy(self, tmp_path: Path) -> None:
        """When all agents are healthy, overall_status is healthy."""
        now = datetime.now(timezone.utc)
        ts = now.isoformat()

        agents_dir = tmp_path / "Agents"
        for name in ("a1", "a2"):
            p = agents_dir / name / "HEALTH.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                f"# HEALTH\n\n### {ts} — Task t\n\n"
                f"| Field | Value |\n|---|---|\n"
                f"| last_run_timestamp | {ts} |\n"
                f"| last_status | healthy |\n"
                f"| consecutive_failures | 0 |\n",
                encoding="utf-8",
            )

        config = ControllerConfig(
            controller_id="test",
            project_root=tmp_path,
            agent_health_paths={
                "a1": "Agents/a1/HEALTH.md",
                "a2": "Agents/a2/HEALTH.md",
            },
        )
        monitor = HealthMonitor(config)
        summary = monitor.check_all()
        assert summary.overall_status == "healthy"
        assert len(summary.healthy) == 2


class TestCheckAllExtended:
    """Test check_all_extended extended monitoring."""

    def _make_config(self, tmp_path: Path) -> ControllerConfig:
        # Create required dirs
        (tmp_path / "Controller" / "inbox").mkdir(parents=True)
        (tmp_path / "Controller" / "outbox").mkdir(parents=True)
        (tmp_path / "audit" / "controller" / "test").mkdir(parents=True)
        (tmp_path / "locks").mkdir(parents=True)
        return ControllerConfig(
            controller_id="test",
            project_root=tmp_path,
            agent_health_paths={},
        )

    def test_returns_expected_keys(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        monitor = HealthMonitor(config)
        result = monitor.check_all_extended()
        assert "status" in result
        assert "active_agents" in result
        assert "active_locks" in result
        assert "errors" in result
        assert "timestamp" in result

    def test_no_errors_when_dirs_exist(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        monitor = HealthMonitor(config)
        result = monitor.check_all_extended()
        assert result["errors"] == []

    def test_missing_inbox_reported(self, tmp_path: Path) -> None:
        config = ControllerConfig(
            controller_id="test",
            project_root=tmp_path / "empty",
            agent_health_paths={},
        )
        (tmp_path / "empty" / "locks").mkdir(parents=True)
        monitor = HealthMonitor(config)
        result = monitor.check_all_extended()
        error_msgs = " ".join(result["errors"])
        assert "inbox_dir_missing" in error_msgs

    def test_scan_locks(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        locks_dir = tmp_path / "locks"
        (locks_dir / "test.lock").write_text(
            json.dumps({"owner": "ctrl", "ts": "2026-01-01"}),
            encoding="utf-8",
        )
        monitor = HealthMonitor(config)
        locks = monitor._scan_locks()
        assert len(locks) == 1
        assert locks[0]["_file"] == "test.lock"

    def test_scan_locks_empty(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        monitor = HealthMonitor(config)
        assert monitor._scan_locks() == []

    def test_scan_locks_corrupt_file(self, tmp_path: Path) -> None:
        config = self._make_config(tmp_path)
        (tmp_path / "locks" / "bad.lock").write_text(
            "NOT JSON", encoding="utf-8"
        )
        monitor = HealthMonitor(config)
        locks = monitor._scan_locks()
        assert len(locks) == 1
        assert "error" in locks[0]


class TestWriteExtendedHealthReport:
    """Test write_extended_health_report."""

    def test_writes_report(self, tmp_path: Path) -> None:
        config = ControllerConfig(
            controller_id="test",
            project_root=tmp_path,
            agent_health_paths={},
        )
        monitor = HealthMonitor(config)
        data = {"status": "healthy", "errors": [], "timestamp": "now"}
        path = monitor.write_extended_health_report(data)
        assert path.exists()
        written = json.loads(path.read_text(encoding="utf-8"))
        assert written["status"] == "healthy"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        config = ControllerConfig(
            controller_id="test",
            project_root=tmp_path,
            agent_health_paths={},
        )
        monitor = HealthMonitor(config)
        path = monitor.write_extended_health_report({"status": "ok"})
        assert path.parent.exists()

    def test_report_path(self, tmp_path: Path) -> None:
        config = ControllerConfig(
            controller_id="test",
            project_root=tmp_path,
            agent_health_paths={},
        )
        monitor = HealthMonitor(config)
        path = monitor.write_extended_health_report({"x": 1})
        assert path == tmp_path / "Controller" / "health" / "health_report.json"
