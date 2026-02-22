---
version: "1.0.0"
last_updated: "2026-02-22"
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
2026-02-22T12:00:00Z
```

### Team Status

| Team | Status | Active Workers | Last Report | Pending Tasks |
|---|---|---|---|---|
| sheets-team | idle | 0 | — | 0 |
| frontend-team | idle | 0 | — | 0 |
| backend-team | idle | 0 | — | 0 |

### Agent Status

| Agent | Team | Status | Last Task | Health |
|---|---|---|---|---|
| sheets-agent | sheets-team | idle | — | healthy |
| frontend-agent | frontend-team | idle | — | healthy |
| backend-agent | backend-team | idle | — | healthy |
| auth-agent | — | idle | — | healthy |
| metrics-agent | — | idle | — | healthy |
| controller | — | idle | — | healthy |

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
  "cycle_timestamp": "2026-02-22T12:00:00Z",
  "total_tasks_completed": 0,
  "total_tasks_failed": 0,
  "total_cost_eur": 0.0,
  "total_tokens_consumed": 0,
  "active_teams": 0,
  "active_agents": 0
}
```

### Candidate Changes (Awaiting Human Approval)

| Change ID | Team | Sheet | Description | Submitted | Status |
|---|---|---|---|---|---|
| (nessun cambio in attesa) | — | — | — | — | — |

## Change History

> Ultime 10 modifiche a questo file (append-only in questa sezione).

| Timestamp | Changed By | Field | Old Value | New Value |
|---|---|---|---|---|
| 2026-02-22T12:00:00Z | system | all | — | initial state |
