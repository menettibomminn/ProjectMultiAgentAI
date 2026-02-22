---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "sheets-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Sheets Team — HEALTH

> **Questo file è append-only.** Il team-lead aggiorna dopo ogni ciclo di aggregazione.
> L'ultima entry rappresenta lo stato corrente del team.
> Non cancellare o modificare entry precedenti.

## Schema (health_v1 — team variant)

```json
{
  "timestamp": "ISO8601",
  "status": "healthy | degraded | down",
  "last_task": "task_id",
  "last_metrics": {
    "duration_ms": 0,
    "tokens_in": 0,
    "tokens_out": 0,
    "cost_eur": 0.0
  },
  "uptime_seconds": 0,
  "error_count_24h": 0,
  "active_workers": 0,
  "workers_healthy": 0,
  "workers_degraded": 0,
  "workers_down": 0,
  "pending_conflicts": 0
}
```

## Transizioni di Stato

| Da | A | Trigger |
|---|---|---|
| `healthy` | `degraded` | ≥ 1 worker `degraded` o conflitto non risolto |
| `healthy` | `down` | team-lead failure o tutti i worker `down` |
| `degraded` | `healthy` | tutti i worker `healthy` e 0 conflitti pendenti |
| `degraded` | `down` | > 50% worker `down` o team-lead failure |
| `down` | `healthy` | team-lead ripristinato + ≥ 1 worker `healthy` |

## Note Specifiche

- Lo stato del team è determinato dallo stato aggregato dei suoi worker.
- `pending_conflicts`: conflitti di concurrency non ancora risolti dal team-lead.
- Se `status == "down"`: il controller assume il ruolo di aggregator (failover).

## Status Log

### 2026-02-22T12:00:00Z — INIT

```json
{
  "timestamp": "2026-02-22T12:00:00Z",
  "status": "healthy",
  "last_task": "none",
  "last_metrics": {
    "duration_ms": 0,
    "tokens_in": 0,
    "tokens_out": 0,
    "cost_eur": 0.0
  },
  "uptime_seconds": 0,
  "error_count_24h": 0,
  "active_workers": 0,
  "workers_healthy": 0,
  "workers_degraded": 0,
  "workers_down": 0,
  "pending_conflicts": 0
}
```

<!-- Append new entries below this line -->
