---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Orchestrator — HEALTH

> **Questo file è append-only.** Aggiornato dopo ogni modifica a STATE.md.
> L'ultima entry rappresenta lo stato corrente dell'orchestratore.
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
  "state_md_hash": "SHA256",
  "backups_available": 0
}
```

## Transizioni di Stato

| Da | A | Trigger |
|---|---|---|
| `healthy` | `degraded` | STATE_UPDATE_FAILED con rollback riuscito |
| `healthy` | `down` | STATE_CORRUPTION senza backup disponibile |
| `degraded` | `healthy` | aggiornamento STATE.md riuscito dopo errore |
| `degraded` | `down` | 3 aggiornamenti consecutivi falliti |
| `down` | `healthy` | rebuild_state completato con successo |

## Note Specifiche

- `state_md_hash`: hash SHA256 di STATE.md dopo l'ultimo aggiornamento, per verifica integrità.
- `backups_available`: numero di backup disponibili in `orchestrator/.state_backup_*.md`.
- Se `status == "down"`: il controller non può aggiornare lo stato → sistema in stallo.

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
  "state_md_hash": "initial",
  "backups_available": 0
}
```

<!-- Append new entries below this line -->
