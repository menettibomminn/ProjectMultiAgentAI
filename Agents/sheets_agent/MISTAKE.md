---
version: "1.0.0"
last_updated: "2026-02-23"
owner: "sheets-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Sheets Worker Agent — MISTAKE

> **Questo file e append-only.** Ogni errore riscontrato aggiunge una nuova entry in fondo.
> Non cancellare o modificare entry precedenti. Ogni entry deve includere una remediation suggerita.

## Formato Entry

```markdown
## {timestamp} — Error in Task {task_id}
- **Error code:** {code}
- **Error message:** {message}
- **Context:** {what the agent was doing}
- **Impact:** nessuna modifica | report parziale | lock non rilasciato
- **Remediation:** {suggerimento}
- **Resolved:** yes | no | pending
```

## Known Error Patterns

| Code | Description | Remediation |
|---|---|---|
| `VALIDATION_ERROR` | Task JSON does not match schema | Fix the task file; check required fields |
| `LOCK_TIMEOUT` | Cannot acquire spreadsheet lock | Check `locks/` for stale lock files |
| `IO_ERROR` | Cannot read/write inbox or audit files | Check filesystem permissions |
| `INTERNAL_ERROR` | Unexpected exception in agent code | Check stack trace in audit log |

---

<!-- Append new error entries below this line -->
