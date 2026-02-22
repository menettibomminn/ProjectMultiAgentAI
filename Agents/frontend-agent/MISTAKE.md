---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "frontend-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Frontend Agent — MISTAKE

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

## Classificazione Severità

| Severità | Descrizione | Azione |
|---|---|---|
| `critical` | Agente non operativo, HEALTH.md → `down` | Notifica immediata al controller |
| `high` | Task fallito con impatto su utente | Notifica controller, retry automatico |
| `medium` | Task degradato, output parziale | Log e retry al prossimo ciclo |
| `low` | Warning, nessun impatto funzionale | Solo log |

---

<!-- Append new error entries below this line -->
