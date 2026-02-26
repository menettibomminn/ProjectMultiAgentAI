---
version: "1.0.0"
last_updated: "2026-02-23"
owner: "sheets-team"
project: "ProjectMultiAgentAI"
---

# Sheets Worker Agent — ARCHITECTURE

## Overview

The `Agents/sheets_agent/` package implements a **read-only Worker Agent** that processes
task requests from `inbox/sheets/{agent_id}/task.json`, validates them, generates
proposed changes, and writes structured reports and audit logs.

**This agent NEVER modifies Google Sheets.** It produces proposals only.

## System Context

```
inbox/sheets/{agent_id}/task.json        locks/sheet_{spreadsheet_id}.lock
              │                                     │
              ▼                                     ▼
┌──────────────────────────────────────────────────────────────┐
│                     SheetsAgent (sheets_agent.py)            │
│                                                              │
│  ┌──────────────────┐  ┌────────────────────┐  ┌──────────┐│
│  │ sheets_task_      │  │ sheets_report_     │  │ lock_    ││
│  │ parser.py         │  │ generator.py       │  │ manager  ││
│  │ (JSON Schema      │  │ (task → proposed   │  │ .py      ││
│  │  validation)      │  │  changes)          │  │          ││
│  └────────┬─────────┘  └────────┬───────────┘  └──────────┘│
│           │                      │                           │
│  ┌────────▼──────────────────────▼──────────────────────────┐│
│  │              sheets_audit_logger.py                       ││
│  │         (SHA-256 checksums, structured logs)              ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
  report.json          audit/*.json           HEALTH.md
```

## Processing Pipeline

1. **Locate task** — check `inbox/sheets/{agent_id}/task.json`
2. **Parse & validate** — JSON Schema + semantic checks via `sheets_task_parser.py`
3. **Idempotency check** — if `report.json` already exists for same task_id, skip
4. **Acquire lock** — per-spreadsheet file lock via `lock_manager.py`
5. **Generate report** — produce `proposed_changes` via `sheets_report_generator.py`
6. **Write report** — atomic write to `inbox/sheets/{agent_id}/report.json`
7. **Archive task** — rename `task.json` → `task.done.json`
8. **Write audit** — structured entry to `audit/sheets/{agent_id}/{timestamp}.json`
9. **Update HEALTH.md** — append status entry
10. **Release lock** — always, even on error (in `finally` block)

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `config.py` | Paths, timeouts, lock backend selection, env overrides |
| `sheets_task_parser.py` | JSON Schema validation + semantic checks |
| `sheets_report_generator.py` | Task → proposed_changes transformation |
| `sheets_audit_logger.py` | Write audit entries with checksums |
| `lock_manager.py` | File-based per-spreadsheet locking (portalocker) |
| `logger.py` | Structured JSON logging to stderr |
| `sheets_agent.py` | Orchestrator: runs the full pipeline |
| `__main__.py` | CLI entry point (`python -m Agents.sheets_agent --run-once`) |

## Locking Strategy

- **Scope:** One lock per `spreadsheet_id`.
- **Path:** `locks/sheet_{spreadsheet_id}.lock`
- **Backend:** File-based with `portalocker` (cross-platform).
- **Stale detection:** Locks older than `lock_timeout_seconds` (default 120s) are overridden.
- **Contention:** Exponential backoff (base 2s, max 5 retries).
- **Pluggable:** Config supports `lock_backend = "redis"` for future Redis/etcd backends.

## Design Decisions

| Decision | Rationale |
|---|---|
| `old_values` is always `null` | The agent does not read from Google Sheets by design. Live values would require API calls. |
| `confidence` is operation-dependent | Simple ops (update/append) get 0.95; destructive ops (delete/clear) get 0.80-0.85. |
| Atomic writes via `.tmp` + `rename` | Prevents partial reads of report.json. |
| Task archived to `.done.json` | Enables replay/forensics without reprocessing. |
| HEALTH.md is append-only | Consistent with project conventions; last entry = current state. |
| No Google API calls | Worker only proposes changes; execution is a separate responsibility. |

## Security Considerations

- No secrets in logs or reports (user_id is an email, not a credential).
- Lock files contain only metadata (owner, timestamp, task_id).
- Audit checksums are SHA-256 of the full report.
- `additionalProperties: false` in JSON Schema prevents field injection.
- No network calls — entire pipeline is local filesystem I/O.

## File Layout

```
Agents/sheets_agent/
├── __init__.py                  # Package init, __version__
├── __main__.py                  # CLI: python -m Agents.sheets_agent --run-once
├── config.py                    # Configuration dataclass + env overrides
├── logger.py                    # Structured JSON logging
├── sheets_agent.py              # SheetsAgent orchestrator
├── sheets_task_parser.py        # JSON Schema + semantic validation
├── sheets_report_generator.py   # Task → report transformation
├── sheets_audit_logger.py       # Audit file writer
├── lock_manager.py              # Per-spreadsheet file locks
├── requirements.txt             # Python dependencies
├── examples/
│   ├── task.json                # Example input task
│   └── report.json              # Example generated report
├── tests/
│   ├── conftest.py              # Shared fixtures
│   ├── test_task_parser.py      # Parser unit tests
│   ├── test_report_generator.py # Generator unit tests
│   ├── test_audit_logger.py     # Audit logger unit tests
│   └── test_e2e.py              # End-to-end test
├── ARCHITECTURE.md              # This file
├── CHANGELOG.md                 # Append-only change log
├── CLAUDE.md                    # Agent role, prompts, hooks
├── HEALTH.md                    # Append-only health status
├── MISTAKE.md                   # Append-only error registry
└── TODO.md                      # Task backlog
```
