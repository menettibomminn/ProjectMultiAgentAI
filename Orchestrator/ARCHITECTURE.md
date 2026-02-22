---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
---

# Orchestrator — ARCHITECTURE

## Panoramica

L'Orchestrator mantiene `STATE.md` come Single Source of Truth per l'intero sistema. Il controller è l'unico componente autorizzato a scrivere su `STATE.md`; tutti gli altri agenti leggono in read-only.

## Architettura

```
┌─────────────────────────────────────────────┐
│              Orchestrator                    │
│                                              │
│  ┌─────────────────────────────────────────┐ │
│  │           STATE.md                       │ │
│  │  (Single Source of Truth)               │ │
│  │                                          │ │
│  │  - Team Status                          │ │
│  │  - Agent Status                         │ │
│  │  - Active Locks                         │ │
│  │  - Pending Directives                   │ │
│  │  - Candidate Changes                    │ │
│  │  - System Metrics                       │ │
│  └────────────────┬────────────────────────┘ │
│                   │                           │
│  ┌────────────────▼────────────────────────┐ │
│  │  State Manager                          │ │
│  │  - validate_state()                     │ │
│  │  - update_state()                       │ │
│  │  - rebuild_state()                      │ │
│  └─────────────────────────────────────────┘ │
└──────────────────┬──────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
   WRITE (solo)          READ (tutti)
        │                     │
   controller         tutti gli agenti
```

## Priorità STATE.md nel Sistema

```
Gerarchia di verità:
1. orchestrator/STATE.md          ← FONTE DI VERITÀ (priorità massima)
2. controller/inbox/ reports      ← dati grezzi
3. agent HEALTH.md                ← stato locale agente
4. ops/logs/audit.log             ← audit trail

In caso di discrepanza: STATE.md vince SEMPRE.
Ricostruzione: STATE.md può essere ricostruito dai report in inbox.
```

## Flow di Aggiornamento

```
1. Controller processa report da inbox
2. Controller chiama orchestrator.update_state(changes)
3. Orchestrator:
   a. Valida le changes
   b. Crea backup (.state_backup_{ts}.md)
   c. Applica le changes a STATE.md
   d. Calcola hash del nuovo STATE.md
   e. Logga hash in ops/logs/audit.log
4. Se errore: rollback da backup
```

## Comunicazione con Controller

L'orchestrator NON comunica via inbox/outbox. Il controller invoca direttamente le funzioni dell'orchestrator:

- `read_state()` — lettura sincrona.
- `update_state(changes)` — scrittura sincrona con lock interno.
- `validate_state()` — verifica consistenza (scheduled).
- `rebuild_state(from_timestamp)` — ricostruzione da inbox (disaster recovery).

## Recovery e Backup

### Backup Automatico

```
Ogni aggiornamento di STATE.md crea:
orchestrator/.state_backup_{timestamp}.md

Retention: ultimi 100 backup.
Cleanup: rimuovere backup più vecchi di 7 giorni.
```

### Disaster Recovery

```pseudo
FUNCTION rebuild_state():
    reports = SORT_BY_TIMESTAMP(READ_ALL("controller/inbox/**/*.json"))
    state = INITIAL_STATE()
    FOR EACH report IN reports:
        VERIFY hash(report) == logged_hash(report)
        state = APPLY_REPORT(state, report)
    WRITE state TO "orchestrator/STATE.md"
    LOG "State rebuilt from {count} reports" TO audit.log
```

## Schema State Change

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["section", "field", "new_value", "reason"],
  "properties": {
    "section": {
      "type": "string",
      "enum": ["team_status", "agent_status", "active_locks", "pending_directives", "candidate_changes", "system_metrics"]
    },
    "field": {"type": "string"},
    "old_value": {},
    "new_value": {},
    "reason": {"type": "string"},
    "triggered_by": {"type": "string", "description": "report_id or directive_id"}
  }
}
```
