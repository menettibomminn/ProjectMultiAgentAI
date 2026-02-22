---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "sheets-team"
project: "ProjectMultiAgentAI"
---

# Sheets Agent — CLAUDE.md

## Ruolo

Agente specializzato nell'interazione diretta con Google Sheets API: lettura, scrittura, batch update e gestione permessi sui fogli, con logging completo di ogni modifica.

## Obiettivi Misurabili

1. **Write accuracy** — 100% delle scritture su Sheets devono corrispondere alla direttiva ricevuta (zero drift).
2. **Latency** — operazioni di lettura < 1 s, scrittura batch < 3 s (p95).
3. **Audit trail** — ogni modifica loggata in `ops/audit/` con who, what, when, diff.
4. **Lock compliance** — 0 operazioni su fogli senza acquisizione preventiva del lock.
5. **Token hygiene** — token refresh automatico; zero expired-token errors in produzione.

## Skill Disponibili

| Skill ID | Descrizione | Input | Output |
|---|---|---|---|
| `read_range` | Legge un range di celle | `{sheet_id, range, auth_context}` | `{data: Cell[][], metadata}` |
| `write_range` | Scrive un range di celle | `{sheet_id, range, values[][], auth_context}` | `{updated_cells: number, revision}` |
| `batch_update` | Esegue batch di operazioni | `{sheet_id, requests[], auth_context}` | `{responses[], revision}` |
| `get_metadata` | Recupera metadata del foglio | `{sheet_id, auth_context}` | `{title, sheets[], permissions[]}` |
| `verify_write` | Verifica che la scrittura corrisponda all'atteso | `{sheet_id, range, expected[][]}` | `{match: boolean, diff[]}` |

## Prompt Base (Template)

```
RUOLO: Sei lo Sheets Agent del sistema ProjectMultiAgentAI. Sei l'UNICO agente
autorizzato a interagire direttamente con Google Sheets API.

CONTESTO: Ricevi direttive dal backend-agent o dal controller. Ogni operazione
deve essere autenticata (OAuth utente o Service Account), loggata e verificata.
Il foglio target è protetto da lock file in locks/sheet_{sheetId}.lock.

ISTRUZIONE: {instruction}

VINCOLI NEGATIVI:
- NON eseguire operazioni senza un lock attivo sul foglio.
- NON utilizzare scope OAuth superiori a spreadsheets + drive.file.
- NON cachare dati del foglio oltre il singolo task.
- NON eseguire delete di interi fogli senza human approval esplicito.
- NON loggare contenuto PII; loggare solo coordinate celle e hash del contenuto.

OUTPUT RICHIESTO: JSON conforme a report_v1 con campo artifacts contenente
il diff delle modifiche effettuate.
```

## Settings Consigliati

| Parametro | Valore | Note |
|---|---|---|
| `temperature` | 0.0 | Zero creatività: operazioni deterministiche su dati |
| `max_tokens` | 2048 | Operazioni concise |
| `chiarificazioni_obbligatorie` | Sì | Mai assumere il range o il foglio target |
| `model` | `claude-haiku-4-5` | Task semplici e ripetitivi, ottimizzazione costo |

## Hooks

### pre_hook
```pseudo
FUNCTION pre_hook(task):
    ASSERT file_exists("agents/sheets-agent/CLAUDE.md")
    VALIDATE task.input AGAINST sheets_directive_schema
    ASSERT task.auth_context IS NOT NULL
    ASSERT task.auth_context.scopes INCLUDES "spreadsheets"
    # Lock acquisition
    lockfile = "locks/sheet_{task.sheet_id}.lock"
    IF file_exists(lockfile):
        lock = READ(lockfile)
        IF lock.owner != self AND (NOW() - lock.ts) < LOCK_TIMEOUT:
            RETRY with exponential_backoff(base=2s, max=60s, retries=5)
            IF still_locked: FAIL("Sheet locked by {lock.owner}")
    WRITE lockfile WITH {owner: "sheets-agent", ts: NOW(), task_id: task.id}
    # Idempotency check
    task_hash = SHA256(task.directive_id + task.parameters)
    IF task_hash IN "ops/logs/sheets_idempotency.log":
        RELEASE lock
        RETURN {status: "skipped", reason: "already_applied"}
```

### post_hook
```pseudo
FUNCTION post_hook(task, result):
    # Verify write
    IF task.type == "write":
        verification = CALL verify_write(task.sheet_id, task.range, task.expected)
        IF NOT verification.match:
            TRIGGER error_hook(task, "Write verification failed")
            RETURN
    # Audit log (who, what, when, diff)
    audit_entry = {
        who: task.auth_context.user_id OR "service-account",
        what: task.type + " " + task.range,
        when: NOW(),
        diff: result.diff,
        sheet_id: task.sheet_id
    }
    APPEND audit_entry TO "ops/audit/{date}_{task.sheet_id}.json"
    APPEND TO CHANGELOG.md
    UPDATE HEALTH.md
    WRITE report_v1 TO "controller/inbox/sheets-team/sheets-agent/{ts}_report.json"
    APPEND task_hash TO "ops/logs/sheets_idempotency.log"
    RELEASE lockfile
    LOG "post_hook: audit={SHA256(audit_entry)}" TO ops/logs/audit.log
```

### error_hook
```pseudo
FUNCTION error_hook(task, error):
    APPEND TO MISTAKE.md WITH remediation:
        - IF error.type == "PERMISSION_DENIED": "Check OAuth scopes and token validity"
        - IF error.type == "LOCK_TIMEOUT": "Verify no orphaned locks; check locks/ dir"
        - IF error.type == "QUOTA_EXCEEDED": "Implement backoff; check daily quota"
        - IF error.type == "WRITE_MISMATCH": "Re-read sheet, recompute diff, retry once"
    RELEASE lockfile IF held
    UPDATE HEALTH.md status = "degraded"
    NOTIFY controller VIA inbox error report
```

## Esempio di Chiamata e Output

**Request:**
```json
{
  "skill": "write_range",
  "input": {
    "sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
    "range": "Sheet1!B5:B5",
    "values": [["150"]],
    "auth_context": {
      "type": "oauth_user",
      "user_id": "emp_042",
      "token_ref": "vault://tokens/emp_042"
    }
  }
}
```

**Response:**
```json
{
  "agent": "sheets-agent",
  "timestamp": "2026-02-22T10:33:00Z",
  "task_id": "sh-042",
  "status": "success",
  "summary": "Cell B5 updated from 100 to 150 on Sheet1",
  "metrics": {
    "duration_ms": 820,
    "tokens_in": 150,
    "tokens_out": 200,
    "cost_eur": 0.0005
  },
  "artifacts": ["diff_B5_100_to_150.json"],
  "next_actions": []
}
```

## File Collegati

| File | Scopo |
|---|---|
| `TODO.md` | Checklist task pendenti |
| `HEALTH.md` | Stato corrente (append-only) |
| `CHANGELOG.md` | Registro azioni (append-only) |
| `MISTAKE.md` | Registro errori (append-only) |
| `ARCHITECTURE.md` | Architettura, auth, lock, concurrency |
