---
version: "1.0.0"
last_updated: "2026-02-22"
owner: "backend-team"
project: "ProjectMultiAgentAI"
---

# Backend Agent — TODO

## Formato

`- [ ] ID — Title — Priority — Due Date — depends: [deps]`

Priority: P0 (critical), P1 (high), P2 (medium), P3 (low)

## Backlog

- [ ] BE-001 — Implementare endpoint ricezione richieste modifica fogli — P0 — 2026-03-01 — depends: []
- [ ] BE-002 — Implementare validazione payload JSON Schema — P0 — 2026-03-01 — depends: []
- [ ] BE-003 — Implementare routing direttive verso sheets-agent — P0 — 2026-03-03 — depends: [BE-001]
- [ ] BE-004 — Implementare compute_diff tra stato corrente e proposto — P1 — 2026-03-05 — depends: [BE-001]
- [ ] BE-005 — Implementare aggregazione report da worker agents — P1 — 2026-03-07 — depends: [BE-001]
- [ ] BE-006 — Implementare lock file management per fogli — P0 — 2026-03-02 — depends: []
- [ ] BE-007 — Implementare idempotency guard con hash log — P1 — 2026-03-05 — depends: [BE-006]
- [ ] BE-008 — Implementare audit logging (who, what, when, diff) — P0 — 2026-03-03 — depends: []
- [ ] BE-009 — Implementare exponential backoff per lock contention — P2 — 2026-03-08 — depends: [BE-006]
- [ ] BE-010 — Scrivere test di integrazione con sheets-agent — P1 — 2026-03-10 — depends: [BE-003]
