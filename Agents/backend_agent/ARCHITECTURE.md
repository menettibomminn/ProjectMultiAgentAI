---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "backend-team"
project: "ProjectMultiAgentAI"
---

# Backend Agent — ARCHITECTURE

## Panoramica

Il backend-agent è il layer di logica di business tra frontend-agent e sheets-agent. Valida richieste, calcola diff, gestisce lock e instrada direttive. Non accede direttamente a Google Sheets.

## Architettura

```
frontend-agent                     controller
     │                                 │
     │  (user approval)                │ (directives)
     ▼                                 ▼
┌──────────────────────────────────────────┐
│              backend-agent                │
│  ┌──────────┐  ┌─────────┐  ┌─────────┐ │
│  │ Validator │  │ Diff    │  │ Router  │ │
│  │          │  │ Engine  │  │         │ │
│  └────┬─────┘  └────┬────┘  └────┬────┘ │
│       │              │            │       │
│  ┌────▼──────────────▼────────────▼────┐ │
│  │         Lock Manager                │ │
│  └─────────────────┬───────────────────┘ │
└────────────────────┼─────────────────────┘
                     │
                     ▼
              sheets-agent
```

## Flusso Operativo

### Modifica Foglio (Happy Path)

1. frontend-agent invia richiesta approvata dall'utente.
2. backend-agent valida il payload (`validate_payload`).
3. backend-agent acquisisce lock su sheet (`locks/sheet_{sheetId}.lock`).
4. backend-agent calcola diff (`compute_diff`).
5. backend-agent crea `directive_v1` per sheets-agent.
6. backend-agent scrive direttiva in `controller/outbox/sheets-team/sheets-agent/`.
7. sheets-agent legge direttiva, esegue e conferma.
8. backend-agent rilascia lock e scrive `report_v1` in `controller/inbox/`.

### Lock Management

```
Lock file: locks/sheet_{sheetId}.lock
Contenuto: {"owner": "backend-agent", "ts": "ISO8601", "task_id": "be-042"}
Timeout: 120 secondi (lock considerato stale dopo timeout)
Backoff: exponential, base=1s, max=30s, max_retries=5
```

**Idempotency:**
- Ogni task ha un hash SHA256 dell'input.
- Hash registrato in `ops/logs/idempotency.log` dopo completamento.
- pre_hook verifica hash prima di procedere → skip se duplicato.

## Comunicazione

**Inbox (report):** `controller/inbox/backend-team/backend-agent/{ts}_report.json`
**Outbox (direttive per sheets-agent):** `controller/outbox/sheets-team/sheets-agent/{ts}_directive.json`

### Schema directive_v1.json

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["directive_id", "target_agent", "command", "parameters", "signature"],
  "properties": {
    "directive_id": {"type": "string", "pattern": "^dir-[a-z0-9-]+$"},
    "target_agent": {"type": "string"},
    "command": {"type": "string", "enum": ["write_range", "batch_update", "read_range"]},
    "parameters": {
      "type": "object",
      "properties": {
        "sheet_id": {"type": "string"},
        "range": {"type": "string"},
        "values": {"type": "array"},
        "auth_context": {"type": "object"}
      }
    },
    "signature": {"type": "string", "description": "SHA256 del payload per integrità"}
  }
}
```

## Dipendenze

| Componente | Tipo | Descrizione |
|---|---|---|
| frontend-agent | Upstream | Riceve richieste approvate |
| sheets-agent | Downstream | Destinazione direttive |
| auth-agent | Runtime | Fornisce token per auth_context |
| controller | Reporting | Inbox/outbox per comunicazione |

## Decisioni Tecniche

1. **Mai accesso diretto a Sheets** — backend-agent è un orchestratore, non un executor.
2. **Lock obbligatorio** — zero operazioni senza lock; prevent race conditions.
3. **Idempotency by default** — ogni operazione è idempotente via hash check.
4. **Validation-first** — ogni payload validato prima di qualsiasi logica.
