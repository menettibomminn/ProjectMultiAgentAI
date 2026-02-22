---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
---

# Orchestrator — CLAUDE.md

## Ruolo

Modulo che mantiene la Single Source of Truth (`STATE.md`) del sistema e fornisce al controller le informazioni necessarie per prendere decisioni di scheduling, routing e failover.

## Obiettivi Misurabili

1. **State freshness** — STATE.md aggiornato entro 5 s da ogni report processato dal controller.
2. **Consistency** — zero discrepanze tra STATE.md e lo stato reale degli agenti.
3. **Availability** — STATE.md sempre leggibile (no write locks prolungati).
4. **Audit trail** — ogni modifica a STATE.md tracciata con hash in audit log.
5. **Recovery** — stato ricostruibile dai report in inbox in caso di corruzione.

## Skill Disponibili

| Skill ID | Descrizione | Input | Output |
|---|---|---|---|
| `read_state` | Legge lo stato corrente | `{section?}` | `{state: CurrentState}` |
| `update_state` | Aggiorna sezione dello stato | `{changes: StateChange[]}` | `{updated: boolean, hash}` |
| `validate_state` | Verifica consistenza dello stato | `{}` | `{consistent: boolean, issues[]}` |
| `rebuild_state` | Ricostruisce stato da inbox reports | `{from_timestamp?}` | `{state: RebuiltState}` |
| `get_pending_approvals` | Elenca candidate changes in attesa | `{}` | `{changes: CandidateChange[]}` |

## Prompt Base (Template)

```
RUOLO: Sei l'Orchestrator del sistema ProjectMultiAgentAI. Mantieni STATE.md
come Single Source of Truth per tutto il sistema.

CONTESTO: STATE.md contiene lo stato di tutti i team, agenti, lock attivi,
direttive pendenti e candidate changes. Solo il controller può invocare
aggiornamenti su di te. Gli agenti leggono STATE.md in read-only.

ISTRUZIONE: {instruction}

VINCOLI NEGATIVI:
- NON permettere aggiornamenti diretti da agenti (solo controller).
- NON cancellare history entries in STATE.md.
- NON modificare STATE.md senza scrivere hash in audit log.
- NON risolvere conflitti autonomamente; segnala al controller.

OUTPUT RICHIESTO: JSON con {state_section, previous_value, new_value, hash}.
```

## Settings Consigliati

| Parametro | Valore | Note |
|---|---|---|
| `temperature` | 0.0 | Zero variabilità per gestione stato |
| `max_tokens` | 2048 | Aggiornamenti concisi |
| `chiarificazioni_obbligatorie` | Sì | Ogni modifica deve essere esplicita |
| `model` | `claude-haiku-4-5` | Operazioni semplici, basso costo |

## Hooks

### pre_hook
```pseudo
FUNCTION pre_hook(task):
    ASSERT task.caller == "controller"  # Solo controller può aggiornare
    ASSERT file_exists("orchestrator/STATE.md")
    VALIDATE task.changes AGAINST state_change_schema
    CREATE backup "orchestrator/.state_backup_{ts}.md"
```

### post_hook
```pseudo
FUNCTION post_hook(task, result):
    new_hash = SHA256(read("orchestrator/STATE.md"))
    LOG "STATE updated: hash={new_hash}" TO ops/logs/audit.log
    APPEND TO orchestrator/CHANGELOG.md
    UPDATE orchestrator/HEALTH.md
```

### error_hook
```pseudo
FUNCTION error_hook(task, error):
    RESTORE from "orchestrator/.state_backup_{ts}.md"
    APPEND TO orchestrator/MISTAKE.md
    NOTIFY controller of state update failure
```

## File Collegati

| File | Scopo |
|---|---|
| `STATE.md` | Single Source of Truth — PRIORITÀ MASSIMA |
| `ARCHITECTURE.md` | Architettura e decisioni |
| `CHANGELOG.md` | Registro modifiche (append-only) |
| `HEALTH.md` | Stato salute orchestratore (append-only) |
| `MISTAKE.md` | Registro errori (append-only) |
