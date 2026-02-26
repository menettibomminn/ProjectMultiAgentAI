---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Metrics Agent — HEALTH

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
  "error_count_24h": 0,
  "agents_monitored": 0,
  "last_collection_cycle": "ISO8601"
}
```

## Transizioni di Stato

| Da | A | Trigger |
|---|---|---|
| `healthy` | `degraded` | INBOX_UNREADABLE o REPORT_MALFORMED su > 20% dei report |
| `healthy` | `down` | impossibile leggere inbox per > 2 cicli consecutivi |
| `degraded` | `healthy` | ciclo di raccolta completato senza errori |
| `degraded` | `down` | 3 cicli consecutivi con errori |
| `down` | `healthy` | restart + ciclo completato con successo |

## Note Specifiche

- `agents_monitored`: numero di agenti da cui si raccolgono metriche.
- `last_collection_cycle`: timestamp dell'ultimo ciclo di raccolta completato.
- Se `status == "degraded"`: le metriche potrebbero essere parziali; la dashboard lo segnalerà.

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
  "agents_monitored": 0,
  "last_collection_cycle": "none"
}
```

<!-- Append new entries below this line -->

### 2026-02-23T16:32:19.017820+00:00 — Task none

| Field | Value |
|---|---|
| last_run_timestamp | 2026-02-23T16:32:19.017820+00:00 |
| last_task_id | none |
| last_status | healthy |
| consecutive_failures | 0 |
| version | 1 |
| queue_length_estimate | 0 |
| notes | auto-updated by metrics_agent.py |

### 2026-02-23T16:32:19.020747+00:00 — Task unknown

| Field | Value |
|---|---|
| last_run_timestamp | 2026-02-23T16:32:19.020747+00:00 |
| last_task_id | unknown |
| last_status | healthy |
| consecutive_failures | 0 |
| version | 1 |
| queue_length_estimate | 0 |
| notes | auto-updated by metrics_agent.py |
