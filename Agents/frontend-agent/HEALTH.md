---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "frontend-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Frontend Agent — HEALTH

> **Questo file è append-only.** Il `post_hook` aggiunge una entry dopo ogni task.
> L'ultima entry rappresenta lo stato corrente dell'agente.
> Non cancellare o modificare entry precedenti.

## Schema (health_v1)

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
  "error_count_24h": 0
}
```

## Transizioni di Stato

| Da | A | Trigger |
|---|---|---|
| `healthy` | `degraded` | error_hook invocato; task fallito ma agente operativo |
| `healthy` | `down` | errore critico; agente non può processare task |
| `degraded` | `healthy` | task completato con successo dopo errore |
| `degraded` | `down` | errori consecutivi > 3 |
| `down` | `healthy` | restart manuale + task completato con successo |

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
  "error_count_24h": 0
}
```

<!-- Append new entries below this line -->
