---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
---

# ProjectMultiAgentAI

Sistema multi-agent AI per la gestione controllata e auditata di Google Sheets, utilizzato dai dipendenti per attività operative interne.

## Obiettivo

Agenti AI (basati su Claude) che, in modo controllato e con log/audit completo, leggono e modificano fogli su Google Sheets per attività operative interne svolte dai dipendenti.

## Principi di Design

- **Human-in-the-loop:** ogni modifica sensibile richiede approvazione umana via dashboard.
- **Least privilege:** scope OAuth minimi (`spreadsheets` + `drive.file`), lock per foglio.
- **Audit completo:** ogni operazione loggata con who, what, when, diff.
- **Immutabilità:** report e log append-only con hash SHA256.
- **Sicurezza:** secrets in vault locale cifrato, mai in git.

## Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                     Orchestrator                             │
│                    (STATE.md — Source of Truth)              │
└────────────────────────┬────────────────────────────────────┘
                         │
                ┌────────┴────────┐
                │   Controller    │
                │  (inbox/outbox) │
                └───┬────────┬────┘
                    │        │
        ┌───────────┤        ├───────────┐
        │           │        │           │
   ┌────▼───┐ ┌────▼───┐ ┌──▼─────┐ ┌──▼──────┐
   │frontend│ │backend │ │sheets  │ │metrics  │
   │ team   │ │ team   │ │ team   │ │ agent   │
   └────────┘ └────────┘ └────────┘ └─────────┘
                              │
                              ▼
                      Google Sheets API
                    (OAuth / Service Account)
```

## Struttura Repository

```
ProjectMultiAgentAI/
├── agents/
│   ├── frontend-agent/      # UI dashboard agent
│   │   ├── CLAUDE.md        # Ruolo, skill, prompt, hooks
│   │   ├── TODO.md          # Task checklist
│   │   └── ARCHITECTURE.md  # Architettura componente
│   ├── backend-agent/       # Business logic agent
│   │   ├── CLAUDE.md
│   │   ├── TODO.md
│   │   └── ARCHITECTURE.md
│   ├── sheets-agent/        # Google Sheets API agent
│   │   ├── CLAUDE.md
│   │   ├── TODO.md
│   │   └── ARCHITECTURE.md
│   ├── auth-agent/          # Authentication & authorization
│   │   └── CLAUDE.md
│   ├── metrics-agent/       # Metrics collection & SLO
│   │   └── CLAUDE.md
│   └── teams/
│       └── sheets-team/     # Team-level coordination
│           ├── CLAUDE.md
│           └── ARCHITECTURE.md
├── controller/
│   ├── CLAUDE.md
│   ├── TODO.md
│   ├── ARCHITECTURE.md      # Inbox/outbox, locking, audit
│   ├── HEALTH.md
│   ├── inbox/               # Report dagli agenti (append-only)
│   │   └── {team}/{agent}/{ts}_report.json
│   └── outbox/              # Direttive verso agenti
│       └── {team}/{agent}/{ts}_directive.json
├── orchestrator/
│   ├── STATE.md             # Single Source of Truth
│   ├── CLAUDE.md
│   └── ARCHITECTURE.md
├── ops/
│   ├── collect_metrics.sh   # Script raccolta metriche
│   ├── cost_estimator.py    # Stima costi per modello
│   ├── logs/                # Log di sistema (gitignored)
│   │   └── audit.log
│   └── audit/               # Audit trail dettagliato (gitignored)
├── infra/
│   └── mcp_config.yml       # Configurazione MCP centrale
├── locks/                   # Lock files runtime (gitignored)
├── README.md
└── CONTRIBUTING.md
```

## Autenticazione Google Sheets

| Metodo | Uso | Default |
|---|---|---|
| **OAuth per-utente** | Modifiche interattive dei dipendenti | **SI (default)** |
| Service Account | Job schedulati pre-approvati | Fallback |

Scope minimi: `spreadsheets` + `drive.file`. Dettagli in `agents/auth-agent/CLAUDE.md`.

## Team Model

Ogni team ha:
- **Team Lead** — aggrega report, risolve conflitti, produce team_report.
- **Worker Agents** — eseguono subtask in parallelo.
- **Comunicazione** — via inbox/outbox nel controller.

Dettagli in `controller/ARCHITECTURE.md` e `agents/teams/sheets-team/ARCHITECTURE.md`.

## Quick Start

1. Clonare il repository.
2. Configurare secrets: `secrets/vault/` (vedi `agents/auth-agent/CLAUDE.md`).
3. Configurare `infra/mcp_config.yml` con i propri parametri Google Cloud.
4. Avviare il sistema (documentazione deployment TBD).

## Sicurezza

- Secrets in `secrets/vault/` (cifrati AES-256-GCM, gitignored).
- Token rotation mensile obbligatoria.
- Pre-commit hook per prevenire commit di credenziali.
- Audit trail immutabile in `ops/audit/` e `ops/logs/audit.log`.

## Contributing

Vedi [CONTRIBUTING.md](CONTRIBUTING.md).
