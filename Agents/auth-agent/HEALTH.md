---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "security-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Auth Agent — HEALTH

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
  "vault_accessible": true,
  "tokens_managed": 0
}
```

## Transizioni di Stato

| Da | A | Trigger |
|---|---|---|
| `healthy` | `degraded` | TOKEN_REFRESH_FAILED per un utente; vault lento |
| `healthy` | `down` | VAULT_UNREACHABLE; ENCRYPTION_ERROR critico |
| `degraded` | `healthy` | vault ripristinato; refresh riuscito |
| `degraded` | `down` | vault inaccessibile per > 60s |
| `down` | `healthy` | vault accessibile + operazione token riuscita |

## Note Specifiche

- `vault_accessible`: indica se il vault locale è raggiungibile.
- `tokens_managed`: numero di token attivi gestiti dall'agente.
- Se `vault_accessible == false`: nessuna operazione auth possibile, tutti gli agenti dipendenti saranno bloccati.

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
  "vault_accessible": true,
  "tokens_managed": 0
}
```

<!-- Append new entries below this line -->
