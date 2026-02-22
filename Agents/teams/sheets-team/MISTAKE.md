---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "sheets-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Sheets Team — MISTAKE

> **Questo file è append-only.** Ogni errore a livello team aggiunge una entry.
> Non cancellare o modificare entry precedenti. Ogni entry deve includere una remediation suggerita.

## Formato Entry

```markdown
## {timestamp} — Error in Task {task_id}
- **Error code:** {code}
- **Error message:** {message}
- **Origin:** team-lead | worker:{worker_id}
- **Workers affected:** [lista worker coinvolti]
- **Stack/Context:** {stack trace o contesto dell'errore}
- **Impact:** {aggregazione fallita | conflitto non risolto | escalation necessaria}
- **Remediation:** {suggerimento per risolvere o prevenire in futuro}
- **Escalated to:** controller | none
- **Resolved:** yes | no | pending
```

## Errori Comuni e Remediation

| Codice | Descrizione | Remediation Standard |
|---|---|---|
| `CONFLICT_UNRESOLVABLE` | 3-way merge fallito su celle sovrapposte | Escalation a controller; human review via dashboard |
| `WORKER_TIMEOUT` | Worker non ha inviato report entro SLO | Redistribuire task a worker alternativo o escalation |
| `AGGREGATION_INCONSISTENCY` | Report worker in conflitto logico | Team-lead verifica manualmente; loggare discrepanza |
| `TEAM_LEAD_FAILURE` | Team-lead non riesce a completare aggregazione | Controller assume ruolo di aggregator temporaneo |
| `CANDIDATE_REJECTED` | Utente ha rifiutato la candidate change | Loggare rifiuto; annullare task; analizzare motivo |

---

<!-- Append new error entries below this line -->
