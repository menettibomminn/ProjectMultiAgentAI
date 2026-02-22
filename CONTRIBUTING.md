---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
---

# Contributing a ProjectMultiAgentAI

## Regole Generali

1. **Mai committare secrets:** chiavi, token, credenziali devono restare in `secrets/vault/` (gitignored).
2. **Frontmatter obbligatorio:** ogni file `.md` deve avere frontmatter YAML con `version`, `last_updated`, `owner`.
3. **Append-only:** `HEALTH.md`, `MISTAKE.md`, `CHANGELOG.md` e i report in `controller/inbox/` sono append-only.
4. **STATE.md è sacro:** solo il controller può modificare `orchestrator/STATE.md`.

## Struttura File

### CLAUDE.md (max 150 righe, escluso ARCHITECTURE.md)
- Ruolo sintetico (1 frase)
- Obiettivi misurabili (3–5)
- Skill disponibili (tabella)
- Prompt base (template)
- Settings consigliati
- Hooks (pre_hook, post_hook, error_hook)
- Esempio di chiamata e output JSON

### TODO.md
Formato checklist:
```
- [ ] ID — Title — Priority — Due Date — depends: [deps]
```
Priority: P0 (critical), P1 (high), P2 (medium), P3 (low).

### HEALTH.md (append-only)
Ogni entry segue `health_v1.json` schema:
```json
{
  "timestamp": "ISO8601",
  "status": "healthy | degraded | down",
  "last_task": "task_id",
  "last_metrics": {}
}
```

### MISTAKE.md (append-only)
Formato entry:
```markdown
## {timestamp} — Error in Task {task_id}
- Error: {message}
- Stack: {stack_trace}
- Remediation: {suggerimento}
```

### CHANGELOG.md (append-only)
Formato entry:
```markdown
## {timestamp} — Task {task_id}
- Status: {status}
- Summary: {descrizione}
```

## Workflow di Sviluppo

1. Creare branch feature da `main`.
2. Implementare le modifiche.
3. Verificare che i file `.md` rispettino le convenzioni.
4. Verificare che nessun secret sia incluso (controllare `.gitignore`).
5. Creare Pull Request con descrizione delle modifiche.
6. Review obbligatoria prima del merge.

## JSON Schema

Gli schema JSON di riferimento per report, direttive, health e team_report sono documentati in:
- `controller/ARCHITECTURE.md`
- `agents/backend-agent/ARCHITECTURE.md`
- `agents/frontend-agent/ARCHITECTURE.md`

## Sicurezza

- Token rotation: mensile.
- Scope: minimo necessario (`spreadsheets` + `drive.file`).
- Storage: local vault o OS keyring.
- Mai committare: `.env`, `*.pem`, `*.key`, `token.json`, `credentials.json`.

## Contatti

Per domande sul progetto, riferirsi al team `platform-team`.
