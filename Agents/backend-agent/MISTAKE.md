---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "backend-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Backend Agent — MISTAKE

> **Questo file è append-only.** Ogni errore riscontrato aggiunge una nuova entry in fondo.
> Non cancellare o modificare entry precedenti. Ogni entry deve includere una remediation suggerita.

## Formato Entry

```markdown
## {timestamp} — Error in Task {task_id}
- **Error code:** {code}
- **Error message:** {message}
- **Stack/Context:** {stack trace o contesto dell'errore}
- **Impact:** {impatto: nessuna modifica applicata | modifica parziale | stato inconsistente}
- **Remediation:** {suggerimento per risolvere o prevenire in futuro}
- **Resolved:** yes | no | pending
```

## Errori Comuni e Remediation

| Codice | Descrizione | Remediation Standard |
|---|---|---|
| `VALIDATION_FAILED` | Payload non conforme a JSON Schema | Verificare schema e riinviare con payload corretto |
| `LOCK_TIMEOUT` | Impossibile acquisire lock sul foglio | Verificare locks/ per lock orfani; attendere e ritentare |
| `LOCK_CONTENTION` | Lock detenuto da altro agente oltre timeout | Controllare agente proprietario; possibile stale lock |
| `SHEETS_AGENT_UNREACHABLE` | Nessuna risposta da sheets-agent | Verificare HEALTH.md di sheets-agent; escalation a controller |
| `IDEMPOTENCY_DUPLICATE` | Task già eseguito (hash presente) | Nessuna azione necessaria; task skippato correttamente |
| `DIRECTIVE_DELIVERY_FAILED` | Impossibile scrivere direttiva in outbox | Verificare permessi directory outbox; ritentare |

---

<!-- Append new error entries below this line -->
