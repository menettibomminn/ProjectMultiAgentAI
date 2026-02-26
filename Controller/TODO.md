---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "platform-team"
project: "ProjectMultiAgentAI"
---

# Controller — TODO

## Formato

`- [ ] ID — Title — Priority — Due Date — depends: [deps]`

Priority: P0 (critical), P1 (high), P2 (medium), P3 (low)

## Backlog

- [ ] CTRL-001 — Implementare inbox reader con file watcher — P0 — 2026-03-01 — depends: []
- [ ] CTRL-002 — Implementare outbox writer per direttive — P0 — 2026-03-01 — depends: []
- [ ] CTRL-003 — Implementare aggiornamento orchestrator/STATE.md — P0 — 2026-03-02 — depends: [CTRL-001]
- [ ] CTRL-004 — Implementare hash verification per report inbox — P0 — 2026-03-03 — depends: [CTRL-001]
- [x] CTRL-005 — Implementare reroute_task per failover team-lead — P1 — 2026-03-05 — depends: [CTRL-001, CTRL-002] — IN PROGRESS
- [ ] CTRL-006 — Implementare aggregazione report per team — P1 — 2026-03-05 — depends: [CTRL-001]
- [ ] CTRL-007 — Implementare audit logging immutabile — P0 — 2026-03-02 — depends: []
- [ ] CTRL-008 — Implementare team-level human approval workflow — P1 — 2026-03-07 — depends: [CTRL-002]
- [ ] CTRL-009 — Implementare metriche di processing (latenza, throughput) — P2 — 2026-03-10 — depends: [CTRL-001]
- [ ] CTRL-010 — Scrivere test end-to-end inbox→processing→outbox — P1 — 2026-03-12 — depends: [CTRL-001, CTRL-002, CTRL-003]
- [x] CTRL-011 — Implementare health monitoring (HealthMonitor, system_health.json) — P1 — 2026-02-24 — depends: [CTRL-001]
- [x] CTRL-012 — Implementare error escalation & retry (RetryManager, backoff, escalation) — P1 — 2026-02-24 — depends: [CTRL-001, CTRL-002]
- [x] CTRL-013 — Resource state tracking (ResourceStateManager) — P1 — 2026-02-26 — depends: [CTRL-001]
- [x] CTRL-014 — Orchestrator communication (OrchestratorCommunicator, alerts, conflicts) — P1 — 2026-02-26 — depends: [CTRL-002]
- [x] CTRL-015 — Simplified audit logging facade (AuditLogger) — P2 — 2026-02-26 — depends: [CTRL-007]
- [x] CTRL-016 — Resource-centric lock API (acquire_lock/release_lock/check_lock) — P1 — 2026-02-26 — depends: [CTRL-001]
- [x] CTRL-017 — Extended health monitoring (check_all_extended, scan_locks, inbox/outbox/audit checks) — P1 — 2026-02-26 — depends: [CTRL-011]
- [x] CTRL-018 — Detection pipeline (zombie locks, stuck agents, missing reports) — P1 — 2026-02-26 — depends: [CTRL-013, CTRL-014, CTRL-016, CTRL-017]
- [x] CTRL-019 — Controller integration (resource tracking in loop, detection in finally) — P0 — 2026-02-26 — depends: [CTRL-013, CTRL-014, CTRL-015, CTRL-018]
- [ ] CTRL-020 — Implementare WebSocket/realtime alerts per dashboard — P3 — TBD — depends: [CTRL-014]
- [ ] CTRL-021 — Implementare auto-remediation per zombie locks — P2 — TBD — depends: [CTRL-018]
