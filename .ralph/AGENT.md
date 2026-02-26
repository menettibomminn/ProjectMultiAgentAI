# Ralph Agent Configuration — ProjectMultiAgentAI

## Prerequisites
- Python >= 3.10
- pip

## Build Instructions

```bash
# Install dependencies (sheets agent)
pip install -r Agents/sheets/requirements.txt
```

## Test Instructions

```bash
# Run all sheets agent tests (41 tests)
python -m pytest Agents/sheets/tests/ -v --tb=short

# Run with coverage
python -m pytest Agents/sheets/tests/ --cov=Agents.sheets --cov-report=term

# Lint
flake8 Agents/sheets/ --max-line-length=100 --exclude=__pycache__

# Type check
mypy Agents/sheets/ --ignore-missing-imports --exclude tests
```

## Run Instructions

```bash
# Run sheets worker agent (single task)
python -m Agents.sheets --run-once

# With custom agent ID
python -m Agents.sheets --run-once --agent-id sheets-worker-02

# Environment overrides
SHEETS_AGENT_ID=worker-03 SHEETS_PROJECT_ROOT=/app python -m Agents.sheets --run-once
```

## Project Architecture

| Layer | Status | Path |
|---|---|---|
| Orchestrator (STATE.md) | Design docs | `Orchestrator/` |
| Controller (inbox/outbox) | Design docs + examples | `Controller/` |
| Sheets Team Lead | Design docs | `Agents/teams/sheets-team/` |
| **Sheets Worker** | **IMPLEMENTED** | `Agents/sheets/` |
| Frontend Agent | Design docs | `Agents/frontend-agent/` |
| Backend Agent | Design docs | `Agents/backend-agent/` |
| Auth Agent | Design docs | `Agents/auth-agent/` |
| Metrics Agent | Design docs | `Agents/metrics-agent/` |

## Key Patterns (from Agents/sheets/)

- `config.py` — frozen dataclass + env overrides
- `*_task_parser.py` — JSON Schema (Draft7) + semantic validation
- `*_report_generator.py` — task → proposed_changes, atomic .tmp writes
- `*_audit_logger.py` — SHA-256 checksums, structured entries
- `lock_manager.py` — portalocker, per-resource, stale detection
- `logger.py` — JSON structured logging to stderr
- `tests/conftest.py` — shared fixtures with tmp_path isolation

## Notes
- All agents follow the same module pattern; extend from sheets/ reference
- CONTRIBUTING.md has full conventions (frontmatter, append-only, no secrets)
- mcp_config.yml has model selection, SLOs, team definitions
