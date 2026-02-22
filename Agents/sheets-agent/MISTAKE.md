---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "sheets-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Sheets Agent — MISTAKE

> **Questo file è append-only.** Ogni errore riscontrato aggiunge una nuova entry in fondo.
> Non cancellare o modificare entry precedenti. Ogni entry deve includere una remediation suggerita.

## Formato Entry

```markdown
## {timestamp} — Error in Task {task_id}
- **Error code:** {code}
- **Error message:** {message}
- **Sheet ID:** {sheet_id coinvolto}
- **Stack/Context:** {stack trace o contesto dell'errore}
- **Impact:** {nessuna modifica | modifica parziale | write non verificato}
- **Remediation:** {suggerimento per risolvere o prevenire in futuro}
- **Resolved:** yes | no | pending
```

## Errori Comuni e Remediation

| Codice | Descrizione | Remediation Standard |
|---|---|---|
| `PERMISSION_DENIED` | Scope OAuth insufficienti o token revocato | Verificare scopes; trigger re-auth via auth-agent |
| `TOKEN_EXPIRED` | Access token scaduto, refresh fallito | Notificare utente per ri-autenticazione; NON usare SA come fallback automatico |
| `LOCK_TIMEOUT` | Impossibile acquisire lock sul foglio | Verificare locks/ per stale lock; backoff e retry |
| `QUOTA_EXCEEDED` | Quota Google Sheets API superata | Implementare backoff; verificare quota giornaliera in Google Console |
| `WRITE_MISMATCH` | verify_write fallito: dati scritti ≠ attesi | Re-leggere foglio, ricalcolare diff, ritentare una volta |
| `MERGE_CONFLICT` | 3-way merge fallito: celle sovrapposte | Escalation a team-lead per risoluzione manuale |
| `RANGE_INVALID` | Range specificato non valido per il foglio | Verificare metadata foglio con get_metadata; correggere range |
| `SHEET_NOT_FOUND` | Foglio con ID specificato non trovato | Verificare sheet_id; possibile foglio cancellato o non condiviso |

---

<!-- Append new error entries below this line -->
