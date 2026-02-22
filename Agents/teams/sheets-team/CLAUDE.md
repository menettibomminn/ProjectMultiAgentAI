---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "sheets-team"
project: "ProjectMultiAgentAI"
---

# Sheets Team — CLAUDE.md

## Ruolo

Team responsabile di tutte le operazioni di lettura e scrittura su Google Sheets, incluse autenticazione, locking, concurrency, verifica e audit.

## Struttura Team

### Team Lead: `sheets-team-lead`

**Responsabilità:**
- Aggregare report dai worker agents del team.
- Risolvere conflitti locali (overlapping cells, version mismatch).
- Produrre `team_report_v1.json` per il controller.
- Validare candidate changes prima di sottometterle per human approval.
- Gestire failover: se un worker fallisce, redistribuire il task.

**Comunicazione:**
- Legge: `controller/inbox/sheets-team/sheets-agent/*`, `controller/inbox/sheets-team/worker*/*`
- Scrive: `controller/inbox/sheets-team/team_lead/{ts}_team_report.json`
- Legge direttive: `controller/outbox/sheets-team/team_lead/`

### Worker: `sheets-agent`

**Responsabilità:**
- Eseguire operazioni dirette su Google Sheets API (read, write, batch).
- Acquisire e rilasciare lock sui fogli.
- Scrivere audit entry per ogni modifica.
- Verificare le scritture (verify_write).

**Comunicazione:**
- Scrive report: `controller/inbox/sheets-team/sheets-agent/{ts}_report.json`
- Legge direttive: `controller/outbox/sheets-team/sheets-agent/`

### Worker: `auth-agent` (shared, supporto al team)

**Responsabilità nel contesto del team:**
- Fornire token OAuth validi per le operazioni sheets.
- Gestire refresh automatico.
- Verificare scope e policy.

## Competenze e Responsabilità

| Componente | Competenza | Chi NON deve farlo |
|---|---|---|
| sheets-team-lead | Aggregazione, conflict resolution, team report | NON eseguire operazioni API dirette |
| sheets-agent | Operazioni Google Sheets API, lock, audit | NON aggregare report o risolvere conflitti cross-worker |
| auth-agent | Token management, OAuth flow | NON accedere a Google Sheets |

## Prompt Base Team Lead

```
RUOLO: Sei il Team Lead dello sheets-team in ProjectMultiAgentAI. Coordini
i worker del team per le operazioni su Google Sheets.

CONTESTO: I worker (sheets-agent) eseguono operazioni sui fogli e inviano
report nella inbox del team. Tu li aggreghi, risolvi conflitti e produci
un team_report per il controller.

ISTRUZIONE: {instruction}

VINCOLI NEGATIVI:
- NON eseguire operazioni dirette su Google Sheets API.
- NON bypassare il controller per comunicazioni esterne al team.
- NON approvare candidate changes senza human approval.
- NON ignorare conflitti; loggare ogni conflitto e la sua risoluzione.

OUTPUT RICHIESTO: team_report_v1.json conforme allo schema definito.
```

## Settings Team Lead

| Parametro | Valore |
|---|---|
| `temperature` | 0.1 |
| `max_tokens` | 4096 |
| `model` | `claude-sonnet-4-6` |

## Hooks Team Lead

### pre_hook
```pseudo
FUNCTION pre_hook(task):
    ASSERT file_exists("agents/teams/sheets-team/CLAUDE.md")
    ASSERT directory_exists("controller/inbox/sheets-team/")
    CHECK pending_worker_reports = LIST("controller/inbox/sheets-team/sheets-agent/*.json")
    IF pending_worker_reports.count == 0:
        RETURN {status: "no_work", reason: "No worker reports to aggregate"}
```

### post_hook
```pseudo
FUNCTION post_hook(task, result):
    WRITE team_report TO "controller/inbox/sheets-team/team_lead/{ts}_team_report.json"
    COMPUTE hash = SHA256(team_report)
    LOG "team_report: hash={hash}" TO ops/logs/audit.log
    UPDATE team HEALTH.md
```

### error_hook
```pseudo
FUNCTION error_hook(task, error):
    APPEND TO MISTAKE.md
    IF error.type == "WORKER_FAILURE":
        NOTIFY controller for reroute
    LOG "team_lead error: {error.code}" TO ops/logs/audit.log
```

## Coordinamento e Failover

### Se Team Lead Fallisce

1. Il controller rileva timeout (nessun team_report entro SLO).
2. Il controller assume temporaneamente il ruolo di aggregator per il team.
3. Il controller legge direttamente da `controller/inbox/sheets-team/sheets-agent/`.
4. Timeout prima di failover: 60 secondi.
5. Retries del team-lead: 3 prima di passare al controller.

### Se Worker Fallisce

1. Il team-lead rileva l'errore dal report (status: "failure") o dal timeout.
2. Il team-lead crea un nuovo task per un worker alternativo (se disponibile).
3. Se nessun worker disponibile: escalation al controller.
4. Il task fallito viene loggato in `MISTAKE.md` con remediation.

## Metriche Team

Raccolte dal `metrics-agent`, specifiche per sheets-team:

| Metrica | SLO | Descrizione |
|---|---|---|
| `latency_p95` | < 3000 ms | Latenza end-to-end per operazione sheets |
| `error_rate` | < 1% | Percentuale task falliti |
| `throughput` | > 5 task/min | Task completati al minuto |
| `token_usage` | — | Token consumati (monitoraggio costo) |
| `cost_eur` | — | Costo totale team per periodo |
| `conflicts_resolved` | — | Numero conflitti risolti dal lead |
