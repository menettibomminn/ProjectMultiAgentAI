---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "sheets-team"
project: "ProjectMultiAgentAI"
---

# Sheets Team — ARCHITECTURE

## Panoramica

Lo sheets-team è responsabile di tutte le operazioni su Google Sheets. Segue il modello multi-agent teams con un team-lead che aggrega, valida e comunica con il controller, e worker agents che eseguono operazioni atomiche sui fogli.

## Struttura

```
                    ┌──────────────┐
                    │  Controller  │
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         │
    ┌──────────────────┐               │
    │ sheets-team-lead │               │
    │                  │               │
    │ - aggregate      │               │
    │ - resolve        │               │
    │   conflicts      │               │
    │ - produce        │               │
    │   team_report    │               │
    │ - validate       │               │
    │   candidate      │               │
    │   changes        │               │
    └────────┬─────────┘               │
             │                         │
    ┌────────┴──────────┐              │
    │                   │              │
    ▼                   ▼              ▼
┌──────────┐    ┌──────────┐    ┌──────────┐
│ sheets-  │    │ sheets-  │    │  auth-   │
│ agent    │    │ agent    │    │  agent   │
│ (worker1)│    │ (worker2)│    │ (shared) │
│          │    │          │    │          │
│ - read   │    │ - read   │    │ - token  │
│ - write  │    │ - write  │    │ - refresh│
│ - lock   │    │ - lock   │    │ - scope  │
│ - audit  │    │ - audit  │    │   check  │
└─────┬────┘    └─────┬────┘    └──────────┘
      │               │
      ▼               ▼
  Google Sheets API (via OAuth / Service Account)
```

## Comunicazione Intra-Team

### Worker → Team Lead (via inbox)

Ogni worker scrive report nella propria sottocartella:

```
controller/inbox/sheets-team/worker1/{ts}_report.json   (report_v1 schema)
controller/inbox/sheets-team/worker2/{ts}_report.json   (report_v1 schema)
controller/inbox/sheets-team/sheets-agent/{ts}_report.json
```

### Team Lead → Controller (via inbox)

Il team-lead legge i report dei worker, li aggrega e produce:

```
controller/inbox/sheets-team/team_lead/{ts}_team_report.json  (team_report_v1 schema)
```

**Aggregazione:**
1. Leggere tutti i report non processati dai worker.
2. Aggregare metriche (sum duration, sum tokens, sum cost).
3. Identificare conflitti (overlapping cells tra worker diversi).
4. Tentare risoluzione automatica (non-overlapping → merge).
5. Se conflitto non risolvibile → escalation a controller.
6. Produrre `team_report_v1.json` con conflicts[] e resolution_log[].

### Controller → Team (via outbox)

```
controller/outbox/sheets-team/team_lead/{ts}_directive.json   (directive_v1 schema)
controller/outbox/sheets-team/sheets-agent/{ts}_directive.json
```

## Concurrency Model

### Lock a Livello Sheet

Ogni foglio Google ha un lock dedicato:

```
locks/sheet_{sheetId}.lock
{"owner": "sheets-agent-worker1", "ts": "ISO8601", "task_id": "sh-042"}
```

**Regole:**
- Un solo agente per volta può avere il lock su un foglio.
- Timeout: 120 secondi (lock stale).
- Backoff: exponential (base=2s, max=60s, 5 retries).

### Optimistic Concurrency + 3-Way Merge

Per gestire modifiche concorrenti quando due worker operano sullo stesso foglio (in tempi diversi grazie al lock, ma con stato che può cambiare):

```
Scenario: Worker1 e Worker2 devono modificare Sheet1

1. Worker1 acquisisce lock, legge stato corrente → "base1"
2. Worker1 applica modifiche → "local1"
3. Worker1 scrive, verifica, rilascia lock
4. Worker2 acquisisce lock, legge stato corrente → "base2"
   (base2 potrebbe essere diverso da base1 se Worker1 ha scritto)
5. Worker2 confronta il suo piano originale vs "base2"
6. Se non ci sono conflitti: applica
7. Se ci sono conflitti:
   a. 3-way merge: base_originale vs local_worker2 vs remote_attuale
   b. Se auto-mergeable (celle non sovrapposte): merge automatico
   c. Se conflitto reale (stesse celle):
      → Worker2 segnala conflitto nel report
      → Team-lead decide risoluzione
```

### Diagramma 3-Way Merge

```
    base (snapshot al momento del planning)
       /                    \
      /                      \
   local                   remote
  (worker changes)    (current sheet state)
      \                      /
       \                    /
        ── 3-way merge ──
              │
         merged result
         (or conflict)
```

## Human Approval Flow

```
1. Worker agents eseguono analisi e preparano modifiche.
2. Team-lead raccoglie tutte le modifiche proposte.
3. Team-lead crea "candidate change":
   {
     "change_id": "cc-001",
     "team": "sheets-team",
     "sheet_id": "...",
     "changes": [
       {"cell": "B5", "old": "100", "new": "150", "reason": "..."},
       {"cell": "C10", "old": "N/A", "new": "Done", "reason": "..."}
     ],
     "submitted_at": "2026-02-22T11:00:00Z"
   }
4. Candidate change inviata al controller → STATE.md (sezione Candidate Changes).
5. Frontend-agent presenta al dipendente la candidate change nella dashboard.
6. Dipendente approva o rifiuta:
   - Approva → controller emette direttiva di commit a sheets-agent.
   - Rifiuta → controller logga rifiuto, team-lead annulla il task.
7. Ogni approvazione/rifiuto loggata in ops/audit/.
```

## Metriche e SLO

| Metrica | SLO Target | Misurazione |
|---|---|---|
| Latency E2E (p95) | < 3000 ms | Dal ricevimento direttiva al completamento write |
| Error Rate | < 1% | Task falliti / task totali (rolling 7d) |
| Throughput | > 5 task/min | Task completati per minuto (rolling 1h) |
| Audit Completeness | 100% | Modifiche con audit entry / modifiche totali |
| Lock Wait Time (p95) | < 10s | Tempo attesa acquisizione lock |

Le metriche sono raccolte dal `metrics-agent` leggendo i team_report dal team-lead e i singoli report dai worker.

## Failover

### Team Lead → Controller

```
Timeout: 60s senza team_report dal team-lead
Retries: 3 (con backoff)
Failover: controller assume ruolo di aggregator temporaneo
Recovery: quando team-lead torna healthy, controller restituisce il ruolo
```

### Worker → Team Lead

```
Timeout: 30s senza report dal worker
Retries: 2 (con backoff)
Action: team-lead redistribuisce il task a un altro worker (se disponibile)
         oppure escalation a controller
```

## Sicurezza

- OAuth per-utente come default (tracciabilità).
- Service Account solo per job schedulati pre-approvati (allowlist in `infra/mcp_config.yml`).
- Token in vault locale cifrato (AES-256-GCM).
- Scope minimi: `spreadsheets` + `drive.file`.
- Nessun secret in git.
- Audit completo per ogni modifica (who, what, when, diff).
