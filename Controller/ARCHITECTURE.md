---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
---

# Controller — ARCHITECTURE

## Panoramica

Il Controller è il nodo centrale di comunicazione del sistema ProjectMultiAgentAI. Gestisce il pattern inbox/outbox per la comunicazione asincrona con tutti gli agenti e team, aggiorna la source of truth (`orchestrator/STATE.md`) e garantisce audit immutabile.

## Inbox / Outbox Pattern

### Inbox (OBBLIGATORIA)

La inbox è il canale principale attraverso cui gli agenti inviano report al controller.

**Path e Naming Convention:**
```
controller/inbox/{team}/{agent}/{timestamp}_report.json
controller/inbox/{team}/team_lead/{timestamp}_team_report.json

Esempi:
controller/inbox/sheets-team/sheets-agent/2026-02-22T103300Z_report.json
controller/inbox/sheets-team/team_lead/2026-02-22T110000Z_team_report.json
controller/inbox/frontend-team/frontend-agent/2026-02-22T103000Z_report.json
controller/inbox/backend-team/backend-agent/2026-02-22T103200Z_report.json
```

**Regole:**
- I report sono **append-only**: mai cancellati o modificati.
- Ogni report ha un hash SHA256 registrato in `ops/logs/audit.log`.
- Il controller verifica l'hash prima di processare (tamper detection).
- Il team-lead aggrega i report dei worker del proprio team prima di inviarli.

### Outbox (OPZIONALE — Abilitata per Team)

La outbox è il canale attraverso cui il controller invia direttive strutturate agli agenti.

**Path e Naming Convention:**
```
controller/outbox/{team}/{agent}/{timestamp}_directive.json

Esempi:
controller/outbox/sheets-team/sheets-agent/2026-02-22T110500Z_directive.json
controller/outbox/backend-team/backend-agent/2026-02-22T110500Z_directive.json
```

**Regole:**
- L'agente target legge dalla propria cartella outbox.
- Prima di applicare una direttiva, l'agente esegue `pre_hook` validation.
- Le direttive processate vengono marcate (`.processed` suffix) ma non cancellate.

## Flow delle Comunicazioni

```
┌─────────────┐     report_v1.json      ┌──────────────┐
│ Worker Agent ├────────────────────────►│  team inbox   │
└─────────────┘                          │ inbox/{team}/ │
                                         │  /workerX/    │
┌─────────────┐   legge + aggrega        └──────┬───────┘
│  Team Lead  │◄─────────────────────────────────┘
│             │
│  - merge    │   team_report_v1.json    ┌──────────────┐
│  - resolve  ├─────────────────────────►│ inbox/{team}/ │
│    conflicts│                          │  /team_lead/  │
└─────────────┘                          └──────┬───────┘
                                                │
                 ┌──────────────────────────────┘
                 ▼
         ┌──────────────┐
         │  CONTROLLER   │
         │               │
         │ 1. Legge inbox│
         │ 2. Verifica   │
         │    hash       │
         │ 3. Aggiorna   │
         │    STATE.md   │
         │ 4. Decide     │
         │    azioni     │
         └──────┬───────┘
                │
                │  directive_v1.json
                ▼
         ┌──────────────┐
         │    OUTBOX     │
         │ outbox/{team}/│
         │  /{agent}/    │
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │ Target Agent │
         │              │
         │ 1. Legge     │
         │    outbox    │
         │ 2. pre_hook  │
         │    validate  │
         │ 3. Esegue    │
         │ 4. post_hook │
         │    → inbox   │
         └──────────────┘
```

### Flusso Dettagliato

1. **Agent → Inbox:** l'agente completa un task e scrive `report_v1.json` nella propria inbox.
2. **Worker → Team Lead:** i worker agent scrivono in `inbox/{team}/workerX/{ts}.json`. Il team-lead legge periodicamente, aggrega i report, risolve conflitti locali e produce `team_report_v1.json`.
3. **Team Lead → Inbox:** il team-lead scrive il report aggregato in `inbox/{team}/team_lead/{ts}.json`.
4. **Controller legge Inbox:** il controller processa i team_report, verifica hash, aggiorna `orchestrator/STATE.md`.
5. **Controller → Outbox:** se necessario, il controller scrive direttive in `outbox/{team}/{agent}/{ts}_directive.json`.
6. **Agent legge Outbox:** l'agente target legge la direttiva, esegue `pre_hook` validation, applica e conferma via inbox.

## Locking e Idempotenza

### Lock per Foglio Google

```
Path: locks/sheet_{sheetId}.lock
Formato JSON:
{
  "owner": "sheets-agent",
  "ts": "2026-02-22T10:33:00Z",
  "task_id": "sh-042",
  "team": "sheets-team"
}
Timeout: 120 secondi
```

### Strategia di Backoff e Retry

```pseudo
FUNCTION acquire_with_backoff(sheet_id, owner, task_id):
    base_delay = 1  # secondi
    max_delay = 60  # secondi
    max_retries = 5

    FOR retry IN 0..max_retries:
        lock = TRY_ACQUIRE("locks/sheet_{sheet_id}.lock", owner, task_id)
        IF lock.acquired:
            RETURN success
        IF lock.stale (age > 120s):
            FORCE_ACQUIRE(lock)
            RETURN success
        delay = MIN(base_delay * (2 ^ retry) + random_jitter(0..1), max_delay)
        WAIT(delay)

    RETURN failure("Max retries exceeded, lock held by {lock.owner}")
```

### Idempotenza

Ogni operazione è resa idempotente tramite:

1. **Hash dell'input:** `SHA256(directive_id + parameters)` → registrato in `ops/logs/idempotency.log`.
2. **Check pre-esecuzione:** prima di eseguire, verificare se hash già presente.
3. **File `.hash`:** per ogni report/direttiva, un file `.hash` companion con il checksum.

```
controller/inbox/sheets-team/sheets-agent/2026-02-22T103300Z_report.json
controller/inbox/sheets-team/sheets-agent/2026-02-22T103300Z_report.json.hash
```

## Auditing e Immutabilità

### Principi

- **Append-only:** tutti i report e log sono append-only. Mai cancellati.
- **Hash chain:** ogni entry in `ops/logs/audit.log` include l'hash del contenuto.
- **Signature:** ogni direttiva include un campo `signature` (SHA256 del payload).
- **Tamper detection:** il controller verifica l'hash di ogni report prima del processing.

### Formato Audit Log

```
ops/logs/audit.log (append-only)

[2026-02-22T10:33:00Z] REPORT agent=sheets-agent task=sh-042 hash=a1b2c3d4...
[2026-02-22T11:00:00Z] DIRECTIVE id=dir-ctrl-050-001 target=sheets-agent hash=e5f6g7h8...
[2026-02-22T11:05:00Z] STATE_UPDATE field=sheets-team.status value=idle hash=i9j0k1l2...
```

## Perché il Modello Teams Richiede Questa Architettura

### 1. Team-Lead Aggregator → Riduce Rumore nel Controller

Senza team-lead, il controller riceverebbe N report da N worker per ogni ciclo di lavoro. Con team-lead:
- I worker inviano report al team-lead (locale, veloce).
- Il team-lead aggrega, risolve conflitti locali e invia UN report al controller.
- **Risultato:** il controller processa 1 report per team invece di N → riduzione rumore, miglior batching, minor carico.

### 2. Per-Team Inbox → Isolamento e Throughput Parallelo

Ogni team ha la propria directory inbox:
- **Isolamento:** un team sovraccarico non impatta gli altri.
- **Parallelismo:** il controller può processare inbox di team diversi in parallelo.
- **Scalabilità:** aggiungere un nuovo team = creare una nuova directory.
- **Debugging:** facile isolare problemi a un singolo team.

### 3. Team-Level Metrics e SLO → Valutazioni Aggregate per Team

Metriche per singolo agente sono troppo granulari per decisioni operative. Le metriche per team permettono:
- SLO a livello team (es. "il sheets-team deve completare sync in < 10 s").
- Comparazione performance tra team.
- Decisioni di scaling per team (aggiungere worker al team sovraccarico).

### 4. Human Approval a Team Level

Ogni team produce una **candidate change** che il dipendente approva via UI prima del commit:
```
1. Worker agents calcolano le modifiche necessarie.
2. Team-lead aggrega in una "candidate change" coerente.
3. Frontend-agent presenta la candidate change all'utente.
4. Utente approva o rifiuta tramite dashboard.
5. Se approvato: team-lead emette direttiva di commit a sheets-agent.
6. Se rifiutato: team-lead logga e annulla il task.
```

Questo garantisce human-in-the-loop a livello team (non per ogni singola operazione, che sarebbe troppo granulare e lento).

## JSON Schema Referenze

### report_v1.json
Definito in `agents/frontend-agent/ARCHITECTURE.md` — valido per tutti gli agenti.

### directive_v1.json
Definito in `agents/backend-agent/ARCHITECTURE.md`.

### team_report_v1.json

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["team", "timestamp", "aggregated_metrics", "worker_reports", "conflicts", "resolution_log"],
  "properties": {
    "team": {"type": "string"},
    "timestamp": {"type": "string", "format": "date-time"},
    "task_id": {"type": "string"},
    "status": {"type": "string", "enum": ["success", "partial", "failure"]},
    "aggregated_metrics": {
      "type": "object",
      "properties": {
        "total_duration_ms": {"type": "number"},
        "total_tokens_in": {"type": "integer"},
        "total_tokens_out": {"type": "integer"},
        "total_cost_eur": {"type": "number"},
        "tasks_completed": {"type": "integer"},
        "tasks_failed": {"type": "integer"},
        "throughput_tasks_per_min": {"type": "number"}
      }
    },
    "worker_reports": {
      "type": "array",
      "items": {"$ref": "#/definitions/report_v1_ref"}
    },
    "conflicts": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "sheet_id": {"type": "string"},
          "range": {"type": "string"},
          "workers_involved": {"type": "array", "items": {"type": "string"}},
          "type": {"type": "string", "enum": ["overlapping_cells", "version_mismatch"]}
        }
      }
    },
    "resolution_log": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "conflict_ref": {"type": "string"},
          "resolution": {"type": "string", "enum": ["keep_local", "keep_remote", "manual_merge", "escalated"]},
          "resolved_by": {"type": "string"},
          "timestamp": {"type": "string", "format": "date-time"}
        }
      }
    }
  }
}
```

### health_v1.json

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["timestamp", "status", "last_task", "last_metrics"],
  "properties": {
    "timestamp": {"type": "string", "format": "date-time"},
    "status": {"type": "string", "enum": ["healthy", "degraded", "down"]},
    "last_task": {"type": "string"},
    "last_metrics": {
      "type": "object",
      "properties": {
        "duration_ms": {"type": "number"},
        "tokens_in": {"type": "integer"},
        "tokens_out": {"type": "integer"},
        "cost_eur": {"type": "number"}
      }
    },
    "uptime_seconds": {"type": "integer"},
    "error_count_24h": {"type": "integer"}
  }
}
```
