"""Tests for Orchestrator.state_processor."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from Orchestrator.state_processor import (
    StateChange,
    StateDocument,
    apply_state_changes,
    backup_state,
    compute_state_checksum,
    parse_state,
    rebuild_state,
    render_state,
    verify_state,
    write_state,
)

# ---------------------------------------------------------------------------
# Sample STATE.md content
# ---------------------------------------------------------------------------

SAMPLE_STATE = """\
---
version: "1.0.0"
last_updated: "2026-02-24"
owner: "platform-team"
project: "ProjectMultiAgentAI"
priority: "HIGHEST — Single Source of Truth"
---

# Orchestrator — STATE.md

> **PRIORITA MASSIMA:** Questo file è la **Single Source of Truth** del sistema
> ProjectMultiAgentAI. Tutti gli agenti e il controller fanno riferimento a questo
> file per determinare lo stato corrente del sistema.

> **Regole:**
> - Solo il **controller** può aggiornare questo file.
> - Ogni aggiornamento deve essere loggato in `ops/logs/audit.log` con hash.
> - In caso di conflitto tra questo file e qualsiasi altro stato, questo file VINCE.
> - Gli agenti leggono questo file in read-only.

## Stato Corrente del Sistema

### Timestamp Ultimo Aggiornamento
```
2026-02-24T12:00:00Z
```

### Team Status

| Team | Status | Active Workers | Last Report | Pending Tasks |
|---|---|---|---|---|
| sheets-team | idle | 0 | — | 0 |
| backend-team | active | 1 | 2026-02-24T11:00:00Z | 2 |

### Agent Status

| Agent | Team | Status | Last Task | Health |
|---|---|---|---|---|
| sheets-agent | sheets-team | idle | — | healthy |
| backend-agent | backend-team | active | be-001 | healthy |

### Active Locks

| Sheet ID | Owner | Since | Task ID |
|---|---|---|---|
| (nessun lock attivo) | — | — | — |

### Pending Directives

| Directive ID | Target | Command | Created | Status |
|---|---|---|---|---|
| (nessuna direttiva pendente) | — | — | — | — |

### System Metrics (Last Cycle)

```json
{
  "cycle_timestamp": "2026-02-24T12:00:00Z",
  "total_tasks_completed": 5,
  "total_tasks_failed": 1,
  "total_cost_eur": 0.025,
  "total_tokens_consumed": 3000,
  "active_teams": 2,
  "active_agents": 2
}
```

### Candidate Changes (Awaiting Human Approval)

| Change ID | Team | Sheet | Description | Submitted | Status |
|---|---|---|---|---|---|
| (nessun cambio in attesa) | — | — | — | — | — |

### Change History

> Ultime 10 modifiche a questo file (append-only in questa sezione).

| Timestamp | Changed By | Field | Old Value | New Value |
|---|---|---|---|---|
| 2026-02-24T12:00:00Z | system | all | — | initial state |
"""


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    """Write sample STATE.md to a temp directory."""
    p = tmp_path / "STATE.md"
    p.write_text(SAMPLE_STATE, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Parse tests
# ---------------------------------------------------------------------------


class TestParseState:
    def test_parse_frontmatter(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        assert doc.frontmatter["version"] == "1.0.0"
        assert doc.frontmatter["owner"] == "platform-team"
        assert doc.frontmatter["project"] == "ProjectMultiAgentAI"

    def test_parse_timestamp(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        assert doc.last_updated == "2026-02-24T12:00:00Z"

    def test_parse_teams(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        assert len(doc.teams) == 2
        assert doc.teams[0]["Team"] == "sheets-team"
        assert doc.teams[1]["Status"] == "active"

    def test_parse_agents(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        assert len(doc.agents) == 2
        assert doc.agents[0]["Agent"] == "sheets-agent"
        assert doc.agents[1]["Last Task"] == "be-001"

    def test_parse_empty_locks(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        assert doc.active_locks == []

    def test_parse_system_metrics(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        assert doc.system_metrics["total_tasks_completed"] == 5
        assert doc.system_metrics["total_cost_eur"] == 0.025

    def test_parse_change_history(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        assert len(doc.change_history) == 1
        assert doc.change_history[0]["Changed By"] == "system"


# ---------------------------------------------------------------------------
# Render round-trip
# ---------------------------------------------------------------------------


class TestRenderState:
    def test_round_trip_preserves_data(self, state_file: Path) -> None:
        """Parse and render should produce a document that re-parses identically."""
        doc = parse_state(state_file)
        rendered = render_state(doc)

        # Write and re-parse
        p2 = state_file.parent / "STATE2.md"
        p2.write_text(rendered, encoding="utf-8")
        doc2 = parse_state(p2)

        assert doc2.frontmatter == doc.frontmatter
        assert doc2.teams == doc.teams
        assert doc2.agents == doc.agents
        assert doc2.system_metrics == doc.system_metrics
        assert len(doc2.change_history) == len(doc.change_history)


# ---------------------------------------------------------------------------
# Apply changes
# ---------------------------------------------------------------------------


class TestApplyStateChanges:
    def test_update_existing_agent(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        changes = [
            StateChange(
                section="agent_status",
                field="sheets-agent",
                column="Status",
                old_value="idle",
                new_value="active",
                reason="New task assigned",
                triggered_by="ctrl-001",
            ),
        ]
        apply_state_changes(doc, changes)
        assert doc.agents[0]["Status"] == "active"
        assert len(doc.change_history) == 2  # original + new

    def test_update_system_metrics(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        changes = [
            StateChange(
                section="system_metrics",
                field="",
                column="total_tasks_completed",
                old_value="5",
                new_value="10",
                reason="Cycle update",
                triggered_by="ctrl-002",
            ),
        ]
        apply_state_changes(doc, changes)
        assert doc.system_metrics["total_tasks_completed"] == 10

    def test_add_new_agent(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        changes = [
            StateChange(
                section="agent_status",
                field="metrics-agent",
                column="Status",
                old_value="—",
                new_value="idle",
                reason="Agent registered",
                triggered_by="ctrl-003",
            ),
        ]
        apply_state_changes(doc, changes)
        assert len(doc.agents) == 3
        assert doc.agents[2]["Agent"] == "metrics-agent"

    def test_history_capped_at_10(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        changes = [
            StateChange(
                section="agent_status",
                field="sheets-agent",
                column="Health",
                old_value="healthy",
                new_value=f"check-{i}",
                reason="test",
                triggered_by=f"test-{i}",
            )
            for i in range(15)
        ]
        apply_state_changes(doc, changes)
        assert len(doc.change_history) <= 10


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


class TestBackup:
    def test_backup_creates_file(self, state_file: Path) -> None:
        backup_path = backup_state(state_file)
        assert backup_path.exists()
        assert ".state_backup_" in backup_path.name

    def test_backup_content_matches(self, state_file: Path) -> None:
        backup_path = backup_state(state_file)
        assert backup_path.read_text(encoding="utf-8") == state_file.read_text(
            encoding="utf-8"
        )

    def test_cleanup_old_backups(self, state_file: Path) -> None:
        backup_dir = state_file.parent / "backups"
        backup_dir.mkdir()
        # Create 105 fake backups
        for i in range(105):
            (backup_dir / f".state_backup_{i:04d}.md").write_text(
                "old", encoding="utf-8"
            )
        backup_state(state_file, backup_dir)
        remaining = list(backup_dir.glob(".state_backup_*.md"))
        assert len(remaining) <= 101  # 100 kept + 1 new


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


class TestWriteState:
    def test_write_creates_file_and_hash(self, tmp_path: Path) -> None:
        doc = StateDocument(
            frontmatter={"version": "1.0.0", "last_updated": "2026-02-24",
                         "owner": "test", "project": "test"},
            last_updated="2026-02-24T12:00:00Z",
            system_metrics={"cycle_timestamp": "2026-02-24T12:00:00Z",
                            "total_tasks_completed": 0,
                            "total_tasks_failed": 0},
        )
        path = tmp_path / "STATE.md"
        result_path, checksum = write_state(doc, path, create_backup=False)
        assert result_path.exists()
        assert (tmp_path / "STATE.md.hash").exists()
        assert len(checksum) == 64  # SHA-256 hex

    def test_write_with_backup(self, state_file: Path) -> None:
        doc = parse_state(state_file)
        write_state(doc, state_file, create_backup=True)
        backups = list(state_file.parent.glob(".state_backup_*.md"))
        assert len(backups) == 1


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_verify_valid_state(self, state_file: Path) -> None:
        # Write hash first
        content = state_file.read_text(encoding="utf-8")
        checksum = compute_state_checksum(content)
        state_file.with_suffix(".md.hash").write_text(
            checksum, encoding="utf-8"
        )
        result = verify_state(state_file)
        assert result.ok

    def test_verify_missing_file(self, tmp_path: Path) -> None:
        result = verify_state(tmp_path / "MISSING.md")
        assert not result.ok
        assert "not found" in result.errors[0]

    def test_verify_checksum_mismatch(self, state_file: Path) -> None:
        state_file.with_suffix(".md.hash").write_text(
            "wrong_hash", encoding="utf-8"
        )
        result = verify_state(state_file)
        assert not result.ok
        assert "Checksum mismatch" in result.errors[0]

    def test_verify_no_hash_file_ok(self, state_file: Path) -> None:
        result = verify_state(state_file)
        assert result.ok  # No hash file = no checksum check


# ---------------------------------------------------------------------------
# Rebuild
# ---------------------------------------------------------------------------


class TestRebuild:
    def test_rebuild_from_empty_inbox(self, tmp_path: Path) -> None:
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        state_path = tmp_path / "STATE.md"
        doc, count = rebuild_state(inbox, state_path)
        assert count == 0
        assert doc.system_metrics["total_tasks_completed"] == 0

    def test_rebuild_from_reports(self, tmp_path: Path) -> None:
        inbox = tmp_path / "inbox"
        team_dir = inbox / "sheets-team" / "sheets-agent"
        team_dir.mkdir(parents=True)

        for i in range(3):
            report: dict[str, Any] = {
                "agent": "sheets-agent",
                "timestamp": f"2026-02-24T1{i}:00:00Z",
                "task_id": f"sh-{i:03d}",
                "status": "success",
                "summary": f"Task {i}",
                "metrics": {
                    "duration_ms": 100,
                    "tokens_in": 50,
                    "tokens_out": 100,
                    "cost_eur": 0.001,
                },
            }
            (team_dir / f"2026T1{i}0000Z_report.json").write_text(
                json.dumps(report), encoding="utf-8"
            )

        state_path = tmp_path / "STATE.md"
        doc, count = rebuild_state(inbox, state_path)
        assert count == 3
        assert doc.system_metrics["total_tasks_completed"] == 3
        assert doc.system_metrics["total_cost_eur"] == pytest.approx(0.003)

        # Agent should be tracked
        agent_names = [a["Agent"] for a in doc.agents]
        assert "sheets-agent" in agent_names

    def test_rebuild_skips_self_reports(self, tmp_path: Path) -> None:
        inbox = tmp_path / "inbox" / "controller"
        inbox.mkdir(parents=True)
        (inbox / "20260224T120000Z_self_report.json").write_text(
            '{"agent": "controller"}', encoding="utf-8"
        )
        state_path = tmp_path / "STATE.md"
        doc, count = rebuild_state(inbox.parent, state_path)
        assert count == 0
