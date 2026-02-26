---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Controller — CHANGELOG

> **Questo file è append-only.** Ogni azione completata aggiunge una nuova entry in fondo.
> Non cancellare o modificare entry precedenti.

## Formato Entry

```markdown
## {timestamp} — Task {task_id}
- Status: success | failure | partial
- Summary: descrizione sintetica dell'azione completata
- Directives emitted: [lista directive_id]
- State changes: [lista campi aggiornati in STATE.md]
- Metrics: duration_ms={ms}, tokens_in={n}, tokens_out={n}, cost_eur={n}
```

---

## 2026-02-22T12:00:00Z — Task ctrl-init

- Status: success
- Summary: Inizializzazione controller. Creati CLAUDE.md, TODO.md, ARCHITECTURE.md, HEALTH.md, CHANGELOG.md. Struttura inbox/outbox pronta.
- Directives emitted: []
- State changes: [initial_state]
- Metrics: duration_ms=0, tokens_in=0, tokens_out=0, cost_eur=0.0

## 2026-02-24T10:00:00Z — Task ctrl-impl

- Status: success
- Summary: Implementazione completa Controller come pacchetto Python. Creati 8 moduli sorgente (config, logger, controller_task_parser, controller_report_generator, controller_audit_logger, lock_manager, controller, __main__) + 4 file test + 2 esempi. Pipeline: inbox scan, SHA-256 hash verification (tamper detection), report_v1 validation, per-team locking, directive emission, atomic writes, audit logging, HEALTH.md updates. Skills implementate: process_inbox, emit_directive. Team-filtered processing supportato.
- Directives emitted: []
- State changes: [controller_package_created]
- Metrics: duration_ms=0, tokens_in=0, tokens_out=0, cost_eur=0.0
- Tests: 30+ test cases (parser, report_gen, audit, e2e)
- Note: Bash non disponibile (shared library error) — tests da verificare manualmente

## 2026-02-24T14:00:00Z — Task ctrl-health-retry

- Status: success
- Summary: Implementati Health Monitoring e Error Escalation & Retry. Nuovi moduli: health_monitor.py (HealthMonitor, AgentHealthSnapshot, SystemHealthSummary), retry_manager.py (RetryManager, TaskRetryEntry). Config estesa con parametri health/retry e env overrides. Controller integrato: error reports triggerano retry con backoff esponenziale; retries esauriti producono escalation in outbox/escalation/. Health check legge HEALTH.md di tutti gli agenti, classifica healthy/degraded/down, scrive system_health.json. Flag --check-health aggiunto al CLI. Skill check_health aggiunta al task parser.
- Directives emitted: [retry_task, escalate]
- State changes: [health_monitor_added, retry_manager_added, config_extended]
- Metrics: duration_ms=0, tokens_in=0, tokens_out=0, cost_eur=0.0
- Tests: 25+ new test cases (health_monitor, retry_manager, e2e retry/escalation/health)
- Files created: health_monitor.py, retry_manager.py, Controller/state/.gitkeep, test_health_monitor.py, test_retry_manager.py
- Files modified: config.py, controller.py, __main__.py, controller_task_parser.py, conftest.py, test_e2e.py, TODO.md

## 2026-02-26T10:00:00Z — Task ctrl-extended

- Status: success
- Summary: Estensione Controller con gestione lock resource-centric, resource state tracking, monitoraggio esteso, rilevamento conflitti/errori (zombie locks, stuck agents, missing reports), audit operativo semplificato, comunicazione strutturata con l'Orchestrator. Nuovi moduli: resource_state_manager.py, orchestrator_communicator.py, audit_logger.py (facade). Moduli estesi: config.py (nuove properties/campi), lock_manager.py (nuova API acquire_lock/release_lock/check_lock), health_monitor.py (check_all_extended, write_extended_health_report, scan_locks). Controller integrato: detection nel finally block, resource state tracking nel loop di processing.
- Directives emitted: []
- State changes: [resource_state_manager_added, orchestrator_communicator_added, audit_logger_added, config_extended, lock_manager_extended, health_monitor_extended, controller_integrated]
- Metrics: duration_ms=0, tokens_in=0, tokens_out=0, cost_eur=0.0
- Tests: 94+ new test cases (resource_state_manager: 18, orchestrator_communicator: 20, audit_logger: 12, lock_manager_new: 15, health_monitor extended: 10, e2e extended: 8, integration: 11)
- Files created: resource_state_manager.py, orchestrator_communicator.py, audit_logger.py, Controller/state/resource_state.json, Controller/audit/, Controller/health/, test_resource_state_manager.py, test_orchestrator_communicator.py, test_audit_logger_new.py, test_lock_manager_new.py
- Files modified: config.py, lock_manager.py, health_monitor.py, controller.py, test_health_monitor.py, test_e2e.py, ARCHITECTURE.md, CHANGELOG.md, TODO.md

<!-- Append new entries below this line -->
