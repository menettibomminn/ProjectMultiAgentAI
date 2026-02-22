---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
---

# Controller — HEALTH

> **Questo file è append-only.** Ogni aggiornamento aggiunge una nuova entry in fondo.
> Non cancellare o modificare entry precedenti.

## Formato Entry

Ogni entry segue il formato `health_v1.json` (machine-readable):

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
