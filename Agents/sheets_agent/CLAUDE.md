---
version: "1.0.0"
last_updated: "2026-02-23"
owner: "sheets-team"
project: "ProjectMultiAgentAI"
---

# Sheets Worker Agent — CLAUDE.md

## Role

Read-only Worker Agent that validates incoming task requests for Google Sheets
operations and produces structured proposals (`proposed_changes`) without ever
modifying the actual spreadsheet. Reports are written to `inbox/sheets/{agent_id}/report.json`.

## Constraints (NEVER violate)

1. **NEVER** call Google Sheets API or any external service.
2. **NEVER** write directly to Google Sheets.
3. **NEVER** read from directories outside the configured inbox/outbox/audit paths.
4. **NEVER** include secrets, tokens, or credentials in logs or reports.
5. **NEVER** process a task without acquiring the spreadsheet lock first.
6. **NEVER** leave a lock unreleased after processing (even on error).

## Running

```bash
# Single-run mode (process one task and exit)
python -m Agents.sheets_agent --run-once

# With custom agent ID
python -m Agents.sheets_agent --run-once --agent-id sheets-worker-02

# With environment overrides
SHEETS_AGENT_ID=sheets-worker-03 SHEETS_PROJECT_ROOT=/app python -m Agents.sheets_agent --run-once
```

## Configuration

All settings are in `config.py`, overridable via environment variables:

| Variable | Default | Description |
|---|---|---|
| `SHEETS_AGENT_ID` | `sheets-worker-01` | Agent identifier |
| `SHEETS_TEAM_ID` | `sheets-team` | Team identifier |
| `SHEETS_PROJECT_ROOT` | Auto-detected | Project root path |
| `SHEETS_LOCK_BACKEND` | `file` | Lock backend (`file` or `redis`) |
| `SHEETS_LOCK_TIMEOUT` | `120` | Lock timeout in seconds |
| `SHEETS_TASK_TIMEOUT` | `60` | Task processing timeout in seconds |

## Task Schema

Tasks are validated against a strict JSON Schema. See `sheets_task_parser.py` for
the full schema. Key fields:

- `task_id` (string, required) — UUID v4
- `user_id` (string, required) — user email
- `team_id` (string, required)
- `sheet.spreadsheet_id` (string, required)
- `sheet.sheet_name` (string, required)
- `requested_changes[]` (array, min 1 item)
  - `op`: `update` | `append_row` | `delete_row` | `clear_range`
  - `range`: cell range string (e.g., `A2:C2`)
  - `values`: 2D array of strings (required for `update`/`append_row`)
- `metadata.source`: `web-ui` | `email` | `api`
- `metadata.priority`: `low` | `normal` | `high`
- `metadata.timestamp`: ISO 8601 string

## Semantic Validations (beyond schema)

- `update` and `append_row` require non-empty `values`.
- `delete_row` must NOT include `values`.
- `additionalProperties: false` on all objects.

## Report Schema

Output report includes:

- `status`: `success` | `error` | `needs_review`
- `proposed_changes[]`: each with `op`, `sheet`, `range`, `old_values` (null),
  `new_values`, `explanation`, `confidence`, `estimated_risk`
- `validation[]`: per-field validation results
- `risks[]`: human-readable risk warnings
- `errors[]`: error messages (empty on success)

## Risk Heuristics

| Operation | Confidence | Risk | Rationale |
|---|---|---|---|
| `update` | 0.95 | low | Explicit values, reversible |
| `append_row` | 0.95 | low | Additive, no data loss |
| `delete_row` | 0.85 | medium | Potential data loss |
| `clear_range` | 0.80 | high | Irreversible data removal |

## Hooks

### Pre-processing
1. Validate task against JSON Schema.
2. Run semantic checks.
3. Check idempotency (existing report for same task_id).
4. Acquire per-spreadsheet lock.

### Post-processing
1. Write report.json (atomic via .tmp + rename).
2. Archive task.json → task.done.json.
3. Write audit entry with SHA-256 checksum.
4. Update HEALTH.md with latest status.
5. Release lock.

### Error handling
1. Generate error report with status `error`.
2. Write audit entry with error stack trace.
3. Update HEALTH.md with `degraded` status.
4. Always release lock in `finally` block.

## Testing

```bash
# Run all tests
python -m pytest Agents/sheets_agent/tests/ -v

# Run specific module
python -m pytest Agents/sheets_agent/tests/test_task_parser.py -v

# With coverage
python -m pytest Agents/sheets_agent/tests/ --cov=Agents.sheets_agent --cov-report=term
```

## Related Files

| File | Purpose |
|---|---|
| `ARCHITECTURE.md` | System design, pipeline, locking strategy |
| `TODO.md` | Task backlog |
| `HEALTH.md` | Append-only health status log |
| `CHANGELOG.md` | Append-only action log |
| `MISTAKE.md` | Append-only error registry |
