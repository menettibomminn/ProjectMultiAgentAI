# Agent Implementation Pattern

## Reference: Agents/sheets/ (fully implemented)

Every worker agent MUST follow this module structure:

```
Agents/{name}/
├── __init__.py           # Package + __version__
├── __main__.py           # CLI: python -m Agents.{name} --run-once
├── config.py             # Frozen dataclass, env overrides, derived paths
├── logger.py             # Structured JSON logging to stderr
├── {name}_agent.py       # Main orchestrator class with run_once()
├── {name}_task_parser.py # JSON Schema (Draft7) + semantic validation
├── {name}_report_generator.py  # task → report with proposed_changes
├── {name}_audit_logger.py      # SHA-256 checksums, structured audit/*.json
├── lock_manager.py       # portalocker, per-resource, stale detection
├── requirements.txt
├── examples/             # Sample task.json + report.json
├── tests/
│   ├── conftest.py       # Shared fixtures (tmp_path, sample_task, test_config)
│   ├── test_{name}_task_parser.py
│   ├── test_{name}_report_generator.py
│   ├── test_{name}_audit_logger.py
│   └── test_e2e.py
└── *.md                  # ARCHITECTURE, CHANGELOG, CLAUDE, HEALTH, MISTAKE, TODO
```

## Pipeline (10 steps)
1. Locate task in inbox
2. Parse & validate (JSON Schema + semantic)
3. Idempotency check (skip if report exists for same task_id)
4. Acquire lock (per-resource, portalocker)
5. Generate report (NO external API calls)
6. Write report (atomic: .tmp + rename)
7. Archive task (.done.json)
8. Write audit (SHA-256 checksum)
9. Update HEALTH.md (append)
10. Release lock (always, in finally)

## NEVER
- Call external APIs during report generation
- Include secrets in logs/reports
- Leave locks unreleased
- Write outside configured inbox/outbox/audit paths
