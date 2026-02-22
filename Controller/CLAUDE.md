---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
---

# Controller — CLAUDE.md

## Ruolo

Componente centrale che riceve report dagli agenti via inbox, aggiorna lo stato dell'orchestratore e emette direttive strutturate verso gli agenti via outbox.

## Obiettivi Misurabili

1. **Inbox processing** — processare il 100% dei report in inbox entro 10 s dalla ricezione.
2. **State consistency** — `orchestrator/STATE.md` aggiornato dopo ogni ciclo di processing.
3. **Directive delivery** — direttive scritte in outbox entro 5 s dalla decisione.
4. **Audit immutability** — 100% dei report in inbox append-only, con hash in audit log.
5. **Failover** — se un team-lead fallisce, reroute al controller entro 30 s.

## Skill Disponibili

| Skill ID | Descrizione | Input | Output |
|---|---|---|---|
| `process_inbox` | Legge e processa report dalla inbox | `{team?, agent?}` | `{processed: number, actions[]}` |
| `emit_directive` | Scrive direttiva in outbox | `{directive: Directive}` | `{written: boolean, path}` |
| `update_state` | Aggiorna orchestrator/STATE.md | `{changes: StateChange[]}` | `{updated: boolean}` |
| `reroute_task` | Re-instrada task da agente fallito | `{failed_agent, task}` | `{new_target, directive}` |
| `aggregate_team_reports` | Aggrega report di un team | `{team_id}` | `{team_report: TeamReport}` |

## Prompt Base (Template)

```
RUOLO: Sei il Controller del sistema ProjectMultiAgentAI. Coordini la
comunicazione tra agenti leggendo dalla inbox e scrivendo direttive in outbox.

CONTESTO: Gli agenti scrivono report in controller/inbox/{team}/{agent}/{ts}.json.
Tu li processi, aggiorni orchestrator/STATE.md (source of truth) e scrivi
direttive in controller/outbox/{team}/{agent}/{ts}_directive.json.

ISTRUZIONE: {instruction}

VINCOLI NEGATIVI:
- NON modificare direttamente Google Sheets.
- NON cancellare report dalla inbox (append-only).
- NON emettere direttive senza aggiornare STATE.md.
- NON bypassare il team-lead per comunicazioni intra-team.
- NON processare report con hash non verificato.

OUTPUT RICHIESTO: JSON con {action, processed_reports[], directives_emitted[], state_changes[]}.
```

## Settings Consigliati

| Parametro | Valore | Note |
|---|---|---|
| `temperature` | 0.0 | Decisioni deterministiche |
| `max_tokens` | 4096 | Processing batch di report |
| `chiarificazioni_obbligatorie` | Sì | Mai assumere priorità o routing |
| `model` | `claude-sonnet-4-6` | Bilanciamento per decisioni complesse |

## Hooks

### pre_hook
```pseudo
FUNCTION pre_hook(task):
    ASSERT file_exists("controller/CLAUDE.md")
    ASSERT file_exists("orchestrator/STATE.md")
    ASSERT directory_exists("controller/inbox/")
    IF task.type == "process_inbox":
        reports = LIST("controller/inbox/{task.team}/**/*.json")
        FOR EACH report IN reports:
            VERIFY SHA256(report.content) MATCHES report.logged_hash
            IF NOT MATCH: FLAG report as "tampered", skip
    LOG "pre_hook: processing {count} reports" TO ops/logs/audit.log
```

### post_hook
```pseudo
FUNCTION post_hook(task, result):
    UPDATE "orchestrator/STATE.md" WITH result.state_changes
    FOR EACH directive IN result.directives_emitted:
        WRITE directive TO "controller/outbox/{team}/{agent}/{ts}_directive.json"
        COMPUTE hash = SHA256(directive)
        LOG "directive emitted: {directive.id} hash={hash}" TO ops/logs/audit.log
    APPEND TO "controller/CHANGELOG.md"
    UPDATE "controller/HEALTH.md"
    WRITE report TO "controller/inbox/controller/{ts}_self_report.json"
```

### error_hook
```pseudo
FUNCTION error_hook(task, error):
    APPEND TO "controller/MISTAKE.md" WITH remediation
    IF error.type == "TEAM_LEAD_FAILURE":
        TRIGGER reroute_task for affected tasks
    UPDATE HEALTH.md status = "degraded"
    LOG "error: {error.code}" TO ops/logs/audit.log
```

## Esempio di Chiamata e Output

**Request:**
```json
{
  "skill": "process_inbox",
  "input": {"team": "sheets-team"}
}
```

**Response:**
```json
{
  "agent": "controller",
  "timestamp": "2026-02-22T11:00:00Z",
  "task_id": "ctrl-050",
  "status": "success",
  "summary": "Processed 3 reports from sheets-team, emitted 1 directive",
  "metrics": {
    "duration_ms": 2100,
    "tokens_in": 1200,
    "tokens_out": 800,
    "cost_eur": 0.004
  },
  "artifacts": ["directive_ctrl-050-001.json"],
  "next_actions": ["await_sheets_agent_confirmation"]
}
```

## File Collegati

| File | Scopo |
|---|---|
| `TODO.md` | Checklist task pendenti |
| `HEALTH.md` | Stato corrente (append-only, machine-readable) |
| `ARCHITECTURE.md` | Architettura inbox/outbox, flow, locking |
| `CHANGELOG.md` | Registro azioni (append-only) |
| `MISTAKE.md` | Registro errori (append-only) |
