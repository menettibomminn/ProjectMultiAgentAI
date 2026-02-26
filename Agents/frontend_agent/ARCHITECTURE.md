---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "frontend-team"
project: "ProjectMultiAgentAI"
---

# Frontend Agent — ARCHITECTURE

## Panoramica

Il frontend-agent genera componenti UI per la dashboard dei dipendenti. Non interagisce direttamente con Google Sheets API; riceve dati dal backend-agent e presenta interfacce per il workflow human-in-the-loop.

## Architettura Componenti

```
┌─────────────────────────────────────────────┐
│              Dashboard UI                    │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐ │
│  │ Sheets   │  │ Approval │  │ Audit Log  │ │
│  │ Status   │  │ Forms    │  │ Viewer     │ │
│  └────┬─────┘  └────┬─────┘  └────┬───────┘ │
│       │              │              │         │
│  ┌────▼──────────────▼──────────────▼───────┐ │
│  │         State Manager                     │ │
│  └────────────────┬──────────────────────────┘ │
└───────────────────┼─────────────────────────┘
                    │ REST API
                    ▼
            backend-agent
```

## Flusso Dati

1. **Dashboard load** → frontend-agent chiede al backend-agent lo stato corrente dei fogli.
2. **Candidate change received** → backend-agent notifica via inbox → frontend-agent renderizza form di approvazione.
3. **User approves** → frontend-agent invia approvazione al backend-agent → backend-agent crea direttiva per sheets-agent.
4. **Audit view** → frontend-agent legge `ops/audit/` (via backend-agent) e renderizza tabella con filtri.

## Comunicazione con Controller

Il frontend-agent scrive report nella inbox del controller:

**Path:** `controller/inbox/frontend-team/frontend-agent/{timestamp}_report.json`

**Schema report_v1.json:**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["agent", "timestamp", "task_id", "status", "summary", "metrics"],
  "properties": {
    "agent": {"type": "string", "const": "frontend-agent"},
    "timestamp": {"type": "string", "format": "date-time"},
    "task_id": {"type": "string", "pattern": "^fe-[0-9]+$"},
    "status": {"type": "string", "enum": ["success", "failure", "partial"]},
    "summary": {"type": "string", "maxLength": 500},
    "metrics": {
      "type": "object",
      "required": ["duration_ms", "tokens_in", "tokens_out", "cost_eur"],
      "properties": {
        "duration_ms": {"type": "number", "minimum": 0},
        "tokens_in": {"type": "integer", "minimum": 0},
        "tokens_out": {"type": "integer", "minimum": 0},
        "cost_eur": {"type": "number", "minimum": 0}
      }
    },
    "artifacts": {"type": "array", "items": {"type": "string"}},
    "next_actions": {"type": "array", "items": {"type": "string"}}
  }
}
```

## Dipendenze

| Componente | Tipo | Descrizione |
|---|---|---|
| backend-agent | Runtime | Fonte dati e destinazione approvazioni |
| auth-agent | Init | Fornisce OAuth flow UI (bottone connessione) |
| controller | Reporting | Destinazione report via inbox |

## Decisioni Tecniche

1. **Nessun accesso diretto a Sheets API** — il frontend-agent è un puro layer di presentazione.
2. **State manager locale** — lo stato UI è gestito localmente; la source of truth è `orchestrator/STATE.md`.
3. **Human-in-the-loop obbligatorio** — ogni candidate change richiede approvazione esplicita via UI.
