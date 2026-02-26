"""Shared fixtures for Orchestrator tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

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


@pytest.fixture()
def state_file(tmp_path: Path) -> Path:
    """Write sample STATE.md to a temp directory."""
    p = tmp_path / "STATE.md"
    p.write_text(SAMPLE_STATE, encoding="utf-8")
    return p


@pytest.fixture()
def orchestrator_dir(tmp_path: Path) -> Path:
    """Create a temp orchestrator directory with STATE.md and all supporting files."""
    orch = tmp_path / "Orchestrator"
    orch.mkdir()
    (orch / "STATE.md").write_text(SAMPLE_STATE, encoding="utf-8")
    (orch / ".backup").mkdir()
    (orch / "ops" / "logs").mkdir(parents=True)
    (orch / "HEALTH.md").write_text("# Health Log\n", encoding="utf-8")
    (orch / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (orch / "MISTAKE.md").write_text("# Mistake Log\n", encoding="utf-8")
    return orch


@pytest.fixture()
def sample_update_request() -> dict[str, Any]:
    """Return a valid StateUpdateRequest as a dict."""
    return {
        "origin": "controller",
        "reason": "Test update",
        "changes": [
            {
                "section": "agent_status",
                "field": "sheets-agent",
                "column": "Status",
                "old_value": "idle",
                "new_value": "active",
                "reason": "Task assigned",
                "triggered_by": "ctrl-test-001",
            },
        ],
    }
