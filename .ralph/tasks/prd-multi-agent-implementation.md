# PRD: Multi-Agent Enterprise Implementation

## Introduction

Implement all stub agents in `Agents/` as enterprise-grade, production-ready Python packages following the established reference pattern from `Agents/sheets/`. Each agent reads tasks from inbox, validates via JSON Schema, generates structured reports, writes audit logs, and updates health status. No agent directly modifies Google Sheets.

## Goals

- Implement 5 agents (auth, backend, frontend, metrics, sheets-team lead) following the 10-step pipeline from `Agents/sheets/`
- Each agent must be idempotent, restart-safe, and fully auditable
- 100% type-hinted code with structured JSON logging
- Unit tests with >80% coverage for each agent
- CI/CD pipeline covering all agents
- Updated documentation (.md files) reflecting implementation

## User Stories

### US-001: auth-agent — Python source modules
**Description:** As a developer, I need the auth-agent fully implemented as a Python package following the sheets worker pattern so that it can process authentication tasks from its inbox.

**Acceptance Criteria:**
- [ ] Create `Agents/auth_agent/__init__.py` with `__version__ = "1.0.0"`
- [ ] Create `Agents/auth_agent/__main__.py` with CLI (--run-once, --agent-id)
- [ ] Create `Agents/auth_agent/config.py` with frozen dataclass, env overrides, derived paths (inbox: `Controller/inbox/security-team/auth-agent/`, audit: `ops/audit/auth-agent/`)
- [ ] Create `Agents/auth_agent/logger.py` with structured JSON logging to stderr
- [ ] Create `Agents/auth_agent/lock_manager.py` using portalocker (copy pattern from Agents/sheets/)
- [ ] Create `Agents/auth_agent/auth_task_parser.py` with JSON Schema for auth tasks (issue_token, refresh_token, revoke_token, validate_scopes) plus semantic validation
- [ ] Create `Agents/auth_agent/auth_report_generator.py` generating report_v1 with proposed_changes, validation entries, risk assessment (scope_violation = high risk, token_refresh = low risk)
- [ ] Create `Agents/auth_agent/auth_audit_logger.py` with SHA-256 checksums, never logging actual token values
- [ ] Create `Agents/auth_agent/auth_agent.py` implementing the 10-step pipeline (locate task, parse, idempotency check, lock, generate report, atomic write, archive, audit, health update, release lock)
- [ ] Create `Agents/auth_agent/requirements.txt` (jsonschema>=4.20, portalocker>=2.8, pydantic>=2.5, pytest>=7.4, flake8>=6.0, mypy>=1.7)
- [ ] All modules have type hints and docstrings
- [ ] Typecheck passes (mypy)
- [ ] Lint passes (flake8 --max-line-length 100)

### US-002: auth-agent — Tests, examples, documentation
**Description:** As a developer, I need comprehensive tests and examples for auth-agent so the implementation is verifiable and documented.

**Acceptance Criteria:**
- [ ] Create `Agents/auth_agent/tests/__init__.py`
- [ ] Create `Agents/auth_agent/tests/conftest.py` with fixtures (SAMPLE_TASK for auth, tmp_project, test_config)
- [ ] Create `Agents/auth_agent/tests/test_auth_task_parser.py` (valid tasks for each op type, invalid schema, semantic violations)
- [ ] Create `Agents/auth_agent/tests/test_auth_report_generator.py` (risk per op type, validation entries, error report, atomic write)
- [ ] Create `Agents/auth_agent/tests/test_auth_audit_logger.py` (checksum determinism, audit entry creation, no token values in output)
- [ ] Create `Agents/auth_agent/tests/test_e2e.py` (full pipeline, empty inbox, invalid task, idempotency)
- [ ] Create `Agents/auth_agent/examples/task.json` (sample issue_token task)
- [ ] Create `Agents/auth_agent/examples/report.json` (sample success report)
- [ ] All tests pass: `python -m pytest Agents/auth_agent/tests/ -v`
- [ ] Update `Agents/auth-agent/ARCHITECTURE.md` with implementation notes referencing new Python modules
- [ ] Update `Agents/auth-agent/TODO.md` marking implemented items as done

### US-003: backend-agent — Python source modules
**Description:** As a developer, I need the backend-agent fully implemented as a Python package so that it can validate requests, compute diffs, and route directives.

**Acceptance Criteria:**
- [ ] Create `Agents/backend_agent/__init__.py` with `__version__ = "1.0.0"`
- [ ] Create `Agents/backend_agent/__main__.py` with CLI
- [ ] Create `Agents/backend_agent/config.py` (inbox: `Controller/inbox/backend-team/backend-agent/`, audit: `ops/audit/backend-agent/`)
- [ ] Create `Agents/backend_agent/logger.py` with structured JSON logging
- [ ] Create `Agents/backend_agent/lock_manager.py` using portalocker
- [ ] Create `Agents/backend_agent/backend_task_parser.py` with JSON Schema for backend tasks (process_sheet_request, validate_payload, aggregate_reports, route_directive, compute_diff) plus semantic validation
- [ ] Create `Agents/backend_agent/backend_report_generator.py` generating report_v1 with proposed_changes (validated payload, computed diff, routing decision), validation, risk assessment
- [ ] Create `Agents/backend_agent/backend_audit_logger.py` with SHA-256 checksums
- [ ] Create `Agents/backend_agent/backend_agent.py` implementing 10-step pipeline
- [ ] Create `Agents/backend_agent/requirements.txt`
- [ ] All modules have type hints and docstrings
- [ ] Typecheck passes
- [ ] Lint passes

### US-004: backend-agent — Tests, examples, documentation
**Description:** As a developer, I need tests and examples for backend-agent.

**Acceptance Criteria:**
- [ ] Create `Agents/backend_agent/tests/` with conftest.py, test_backend_task_parser.py, test_backend_report_generator.py, test_backend_audit_logger.py, test_e2e.py
- [ ] Create `Agents/backend_agent/examples/task.json` and `report.json`
- [ ] All tests pass: `python -m pytest Agents/backend_agent/tests/ -v`
- [ ] Update `Agents/backend-agent/ARCHITECTURE.md` and `TODO.md`

### US-005: metrics-agent — Python source modules
**Description:** As a developer, I need the metrics-agent fully implemented to collect, aggregate, and report metrics from all agents.

**Acceptance Criteria:**
- [ ] Create `Agents/metrics_agent/__init__.py` with `__version__ = "1.0.0"`
- [ ] Create `Agents/metrics_agent/__main__.py` with CLI
- [ ] Create `Agents/metrics_agent/config.py` (inbox: `Controller/inbox/platform-team/metrics-agent/`, audit: `ops/audit/metrics-agent/`, reads from all team inboxes)
- [ ] Create `Agents/metrics_agent/logger.py`
- [ ] Create `Agents/metrics_agent/lock_manager.py`
- [ ] Create `Agents/metrics_agent/metrics_task_parser.py` with JSON Schema for metrics tasks (collect_agent_metrics, collect_team_metrics, compute_cost, check_slo, generate_report)
- [ ] Create `Agents/metrics_agent/metrics_report_generator.py` generating aggregated metrics (tasks_completed, tasks_failed, avg_duration_ms, p95_duration_ms, tokens_in_total, tokens_out_total, cost_eur_total, error_rate, slo_compliance)
- [ ] Create `Agents/metrics_agent/metrics_audit_logger.py`
- [ ] Create `Agents/metrics_agent/metrics_agent.py` implementing 10-step pipeline
- [ ] Create `Agents/metrics_agent/requirements.txt`
- [ ] Type hints, docstrings, typecheck, lint pass

### US-006: metrics-agent — Tests, examples, documentation
**Description:** As a developer, I need tests and examples for metrics-agent.

**Acceptance Criteria:**
- [ ] Create `Agents/metrics_agent/tests/` with conftest.py and all test files
- [ ] Create `Agents/metrics_agent/examples/task.json` and `report.json`
- [ ] All tests pass: `python -m pytest Agents/metrics_agent/tests/ -v`
- [ ] Update `Agents/metrics-agent/CHANGELOG.md` and `HEALTH.md`

### US-007: frontend-agent — Python source modules
**Description:** As a developer, I need the frontend-agent implemented to generate UI component proposals and handle approval workflow tasks.

**Acceptance Criteria:**
- [ ] Create `Agents/frontend_agent/__init__.py` with `__version__ = "1.0.0"`
- [ ] Create `Agents/frontend_agent/__main__.py` with CLI
- [ ] Create `Agents/frontend_agent/config.py` (inbox: `Controller/inbox/frontend-team/frontend-agent/`, audit: `ops/audit/frontend-agent/`)
- [ ] Create `Agents/frontend_agent/logger.py`
- [ ] Create `Agents/frontend_agent/lock_manager.py`
- [ ] Create `Agents/frontend_agent/frontend_task_parser.py` with JSON Schema for frontend tasks (render_dashboard, render_approval_form, render_audit_log, validate_input, format_error)
- [ ] Create `Agents/frontend_agent/frontend_report_generator.py` generating report_v1 with proposed_changes (component definitions, approval actions), validation, risk assessment
- [ ] Create `Agents/frontend_agent/frontend_audit_logger.py`
- [ ] Create `Agents/frontend_agent/frontend_agent.py` implementing 10-step pipeline
- [ ] Create `Agents/frontend_agent/requirements.txt`
- [ ] Type hints, docstrings, typecheck, lint pass

### US-008: frontend-agent — Tests, examples, documentation
**Description:** As a developer, I need tests and examples for frontend-agent.

**Acceptance Criteria:**
- [ ] Create `Agents/frontend_agent/tests/` with conftest.py and all test files
- [ ] Create `Agents/frontend_agent/examples/task.json` and `report.json`
- [ ] All tests pass: `python -m pytest Agents/frontend_agent/tests/ -v`
- [ ] Update `Agents/frontend-agent/ARCHITECTURE.md` and `TODO.md`

### US-009: sheets-team lead — Python source modules
**Description:** As a developer, I need the sheets-team lead implemented to aggregate worker reports, resolve conflicts, and produce team reports.

**Acceptance Criteria:**
- [ ] Create `Agents/sheets_team_lead/__init__.py` with `__version__ = "1.0.0"`
- [ ] Create `Agents/sheets_team_lead/__main__.py` with CLI
- [ ] Create `Agents/sheets_team_lead/config.py` (reads from: `Controller/inbox/sheets-team/sheets-agent/`, writes to: `Controller/inbox/sheets-team/team_lead/`, audit: `ops/audit/sheets-team-lead/`)
- [ ] Create `Agents/sheets_team_lead/logger.py`
- [ ] Create `Agents/sheets_team_lead/lock_manager.py`
- [ ] Create `Agents/sheets_team_lead/team_task_parser.py` with JSON Schema for team-lead tasks (aggregate_reports, resolve_conflict, produce_team_report, redistribute_task)
- [ ] Create `Agents/sheets_team_lead/team_report_generator.py` generating team_report_v1 with aggregated metrics, conflicts[], resolution_log[], candidate_changes[]
- [ ] Create `Agents/sheets_team_lead/team_audit_logger.py`
- [ ] Create `Agents/sheets_team_lead/team_agent.py` implementing 10-step pipeline adapted for team-lead role
- [ ] Create `Agents/sheets_team_lead/requirements.txt`
- [ ] Type hints, docstrings, typecheck, lint pass

### US-010: sheets-team lead — Tests, examples, documentation
**Description:** As a developer, I need tests and examples for sheets-team lead.

**Acceptance Criteria:**
- [ ] Create `Agents/sheets_team_lead/tests/` with conftest.py and all test files
- [ ] Create `Agents/sheets_team_lead/examples/task.json` and `report.json`
- [ ] All tests pass: `python -m pytest Agents/sheets_team_lead/tests/ -v`
- [ ] Update `Agents/teams/sheets-team/ARCHITECTURE.md` and `CHANGELOG.md`

### US-011: CI/CD pipeline for all agents
**Description:** As a developer, I need the CI workflow updated to test all agents, not just sheets.

**Acceptance Criteria:**
- [ ] Update `.github/workflows/ci.yml` to run tests for all 6 agents (sheets, auth_agent, backend_agent, frontend_agent, metrics_agent, sheets_team_lead)
- [ ] Each agent tested with flake8, mypy, pytest in matrix
- [ ] Workflow triggers on changes to any `Agents/**` path
- [ ] Typecheck passes
- [ ] All existing sheets tests still pass

### US-012: Root package init and agent registry update
**Description:** As a developer, I need the root Agents package and memory files updated to reflect all implementations.

**Acceptance Criteria:**
- [ ] Update `Agents/__init__.py` to list all available agents
- [ ] Verify all agents are importable: `python -c "import Agents.auth_agent; import Agents.backend_agent; import Agents.frontend_agent; import Agents.metrics_agent; import Agents.sheets_team_lead"`
- [ ] All agents runnable: `python -m Agents.<name> --run-once` (exits cleanly with no task)

## Functional Requirements

- FR-1: Each agent reads tasks from `Controller/inbox/{team}/{agent}/task.json`
- FR-2: Each agent validates tasks against JSON Schema (Draft 7) plus semantic checks
- FR-3: Each agent generates `report.json` with proposed_changes, risks, validation, timestamps (UTC + local)
- FR-4: Each agent writes audit entries to `ops/audit/{agent}/{timestamp}.json` with SHA-256 checksums
- FR-5: Each agent updates its HEALTH.md with operational status after every task
- FR-6: Each agent manages locks on shared resources via portalocker
- FR-7: Each agent is idempotent (skips if report exists for same task_id)
- FR-8: Each agent uses atomic file writes (tmp + rename)
- FR-9: No agent directly modifies Google Sheets
- FR-10: All agents follow the 10-step pipeline from `Agents/sheets/`

## Non-Goals

- No actual Google Sheets API integration (read-only report generation)
- No real OAuth token management (simulated in report)
- No real UI rendering (frontend-agent generates component proposals)
- No real-time metrics collection (batch processing from inbox)
- No Redis lock backend (file-based only for now)
- No Docker containerization
- No deployment configuration

## Technical Considerations

- Reference implementation: `Agents/sheets/` (all 9 Python modules + tests)
- Pattern specification: `.ralph/specs/agent-pattern.md`
- Python >= 3.10 required
- Dependencies: jsonschema, portalocker, pydantic, pytest
- All agents use underscore naming for Python packages (e.g., `auth_agent/` not `auth-agent/`)
- Existing kebab-case dirs (`auth-agent/`) keep documentation only
- Configuration via environment variables with sensible defaults

## Success Metrics

- All 5 new agents pass unit tests
- CI pipeline green for all agents on Python 3.10 and 3.11
- Each agent runnable via `python -m Agents.<name> --run-once`
- Zero type errors (mypy strict)
- Zero lint errors (flake8)

## Open Questions

- None. Conservative choices documented in each agent's ARCHITECTURE.md.
