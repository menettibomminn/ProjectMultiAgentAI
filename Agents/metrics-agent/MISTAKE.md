---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Metrics Agent — MISTAKE

> **Questo file è append-only.** Ogni errore riscontrato aggiunge una nuova entry in fondo.
> Non cancellare o modificare entry precedenti. Ogni entry deve includere una remediation suggerita.

## Formato Entry

```markdown
## {timestamp} — Error in Task {task_id}
- **Error code:** {code}
- **Error message:** {message}
- **Stack/Context:** {stack trace o contesto dell'errore}
- **Impact:** {metriche mancanti | SLO non verificato | report incompleto}
- **Remediation:** {suggerimento per risolvere o prevenire in futuro}
- **Resolved:** yes | no | pending
```

## Errori Comuni e Remediation

| Codice | Descrizione | Remediation Standard |
|---|---|---|
| `INBOX_UNREADABLE` | Impossibile leggere report dalla inbox | Verificare permessi directory controller/inbox/ |
| `REPORT_MALFORMED` | Report non conforme a report_v1 schema | Loggare report malformato; notificare agente sorgente |
| `METRIC_MISSING` | Campo metrica assente nel report | Usare valore zero e flaggare come incompleto |
| `SLO_CHECK_FAILED` | Errore durante verifica SLO | Retry al prossimo ciclo; verificare slo config in mcp_config.yml |
| `AGGREGATION_ERROR` | Errore durante aggregazione metriche team | Verificare consistenza dati; retry con report individuali |

---

<!-- Append new error entries below this line -->
