---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Orchestrator — MISTAKE

> **Questo file è append-only.** Ogni errore riscontrato aggiunge una nuova entry in fondo.
> Non cancellare o modificare entry precedenti. Ogni entry deve includere una remediation suggerita.

## Formato Entry

```markdown
## {timestamp} — Error in Task {task_id}
- **Error code:** {code}
- **Error message:** {message}
- **STATE.md section affected:** {sezione coinvolta}
- **Stack/Context:** {stack trace o contesto dell'errore}
- **Impact:** {STATE.md inconsistente | aggiornamento perso | backup necessario}
- **Remediation:** {suggerimento per risolvere o prevenire in futuro}
- **Backup restored:** yes | no | not_needed
- **Resolved:** yes | no | pending
```

## Errori Comuni e Remediation

| Codice | Descrizione | Remediation Standard |
|---|---|---|
| `STATE_CORRUPTION` | STATE.md in stato inconsistente | Ripristinare da ultimo backup (.state_backup_{ts}.md) |
| `BACKUP_FAILED` | Impossibile creare backup prima di aggiornamento | Abortire aggiornamento; verificare spazio disco e permessi |
| `UNAUTHORIZED_CALLER` | Aggiornamento richiesto da non-controller | Rifiutare; loggare tentativo; alertare security |
| `VALIDATION_FAILED` | StateChange non conforme a schema | Rifiutare change; notificare controller con dettaglio |
| `REBUILD_INCOMPLETE` | Ricostruzione da inbox incompleta | Verificare integrità report in inbox; ricostruzione parziale |

---

<!-- Append new error entries below this line -->
