---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "sheets-team"
project: "ProjectMultiAgentAI"
---

# Sheets Agent — ARCHITECTURE

## Panoramica

Lo sheets-agent è l'UNICO componente del sistema autorizzato a interagire con Google Sheets API. Tutte le letture e scritture sui fogli passano da questo agente, che garantisce locking, audit e verifica di ogni operazione.

## Architettura

```
controller/outbox/                    auth-agent
sheets-team/sheets-agent/             (token provider)
        │                                  │
        ▼                                  ▼
┌──────────────────────────────────────────────┐
│                 sheets-agent                  │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │ Directive │  │ Lock     │  │ Auth       │ │
│  │ Reader   │  │ Manager  │  │ Handler    │ │
│  └────┬─────┘  └────┬─────┘  └─────┬──────┘ │
│       │              │              │         │
│  ┌────▼──────────────▼──────────────▼───────┐ │
│  │       Google Sheets API Client            │ │
│  └────────────────┬──────────────────────────┘ │
│                   │                             │
│  ┌────────────────▼──────────────────────────┐ │
│  │       Audit & Verification                │ │
│  └───────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
  Google Sheets API    ops/audit/
```

## Autenticazione Google Sheets

### Opzione 1: OAuth per Utente (DEFAULT)

Ogni operazione eseguita per conto di un dipendente usa il suo token OAuth personale.

**Scope minimi richiesti:**
- `https://www.googleapis.com/auth/spreadsheets` — lettura e scrittura fogli
- `https://www.googleapis.com/auth/drive.file` — accesso ai file aperti/creati dall'app

**Flow:**
1. sheets-agent riceve `auth_context` nella direttiva.
2. Se `auth_context.type == "oauth_user"`:
   - Legge token reference da `auth_context.token_ref` (es. `vault://tokens/emp_042`).
   - auth-agent fornisce access_token dal vault locale.
   - Se token scaduto → auth-agent esegue refresh automatico.
   - Se refresh fallisce → errore, utente deve ri-autenticarsi.
3. Le modifiche appaiono come eseguite dall'utente nel revision history di Google.

**Dove salvare refresh tokens:**
```
secrets/vault/tokens/{user_id}.enc
├── Encryption: AES-256-GCM
├── Master key: OS keyring (Windows Credential Manager / macOS Keychain)
└── MAI in plaintext, MAI in git
```

### Opzione 2: Service Account + Domain-Wide Delegation

Per job schedulati pre-approvati (es. report notturni, sync automatici).

**Configurazione Google Workspace:**
1. Creare Service Account in Google Cloud Console.
2. Abilitare Domain-Wide Delegation nelle impostazioni del SA.
3. In Google Workspace Admin Console → Security → API Controls → Domain-Wide Delegation:
   - Aggiungere Client ID del service account.
   - Scope autorizzati: `spreadsheets` + `drive.file` (SOLO questi).
4. Salvare chiave SA: `secrets/vault/sa_key.enc` (cifrata, mai in git).

**Tradeoffs:**
| Aspetto | OAuth Utente | Service Account |
|---|---|---|
| Attribuzione | Utente specifico | Service account (generico) |
| Interazione | Richiede consenso utente | Nessuna interazione |
| Audit | Chi ha fatto cosa: chiaro | Chi ha autorizzato: meno chiaro |
| Revoca | Per-utente | Tutto-o-niente (SA) |
| Caso d'uso | Modifiche interattive | Batch job schedulati |

### Policy di Default

```
DEFAULT: OAuth per-utente + Service Account fallback per job autorizzati

1. Operazioni interattive → SEMPRE OAuth utente.
2. Job schedulati → Service Account CON impersonation (preserva audit).
3. Fallback automatico OAuth → SA: VIETATO.
   Se OAuth fallisce → notifica utente per ri-autenticazione.
4. SA allowlist in: infra/mcp_config.yml → service_account.allowed_jobs[]
```

## Locking e Concurrency

### Lock File

```
Path: locks/sheet_{sheetId}.lock
Formato: {"owner": "sheets-agent", "ts": "ISO8601", "task_id": "sh-042"}
Timeout: 120 secondi (lock stale dopo timeout → può essere acquisito)
```

### Acquisizione Lock

```pseudo
FUNCTION acquire_lock(sheet_id, task_id):
    lockfile = "locks/sheet_{sheet_id}.lock"
    retries = 0
    WHILE retries < MAX_RETRIES (5):
        IF NOT file_exists(lockfile):
            WRITE lockfile WITH {owner: self, ts: NOW(), task_id}
            RETURN success
        ELSE:
            lock = READ(lockfile)
            IF (NOW() - lock.ts) > LOCK_TIMEOUT:
                # Stale lock — safe to override
                LOG "Overriding stale lock from {lock.owner}"
                WRITE lockfile WITH {owner: self, ts: NOW(), task_id}
                RETURN success
            ELSE:
                # Active lock — backoff and retry
                WAIT exponential_backoff(base=2s, factor=2, retries)
                retries += 1
    RETURN failure("Lock held by {lock.owner}, max retries exceeded")
```

### Optimistic Concurrency + 3-Way Merge

Per gestire modifiche concorrenti sullo stesso foglio:

```
1. BEFORE write: read current state → "base" snapshot
2. Compute local changes (da direttiva) → "local"
3. Read current state again → "remote" (potrebbe essere cambiato)
4. IF base == remote: apply local changes (no conflict)
5. IF base != remote:
   a. Compute 3-way merge: base vs local vs remote
   b. IF auto-mergeable (non-overlapping cells): apply merged changes
   c. IF conflict (overlapping cells):
      - Log conflict in team_report.conflicts[]
      - Escalate to team-lead for resolution
      - Team-lead decides: keep local, keep remote, or manual merge
6. POST write: verify_write to confirm
```

## Audit e Logging

### Ogni Modifica — Audit Entry

```json
{
  "who": "emp_042 (via oauth)",
  "what": "write_range Sheet1!B5:B5 [100→150]",
  "when": "2026-02-22T10:33:00Z",
  "diff": {
    "sheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
    "range": "Sheet1!B5:B5",
    "before": [["100"]],
    "after": [["150"]]
  },
  "task_id": "sh-042",
  "directive_id": "dir-be042-001"
}
```

**Storage:** `ops/audit/{YYYY-MM-DD}_{sheetId}.json` (append-only)

### Permesso Minimo

| Risorsa | Permesso | Motivazione |
|---|---|---|
| Google Sheets | `spreadsheets` scope | Solo lettura/scrittura fogli |
| Google Drive | `drive.file` scope | Solo file aperti/creati dall'app |
| Lock files | read/write `locks/` | Gestione concurrency |
| Audit logs | append-only `ops/audit/` | Tracciamento immutabile |
| Inbox/Outbox | read outbox, write inbox | Comunicazione controller |

## Comunicazione

- **Legge direttive da:** `controller/outbox/sheets-team/sheets-agent/`
- **Scrive report a:** `controller/inbox/sheets-team/sheets-agent/{ts}_report.json`

## Schema report_v1.json

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
