# ProjectMultiAgentAI — Specification

## Goal
Multi-agent AI system (Claude-based) for controlled, audited Google Sheets operations
performed by company employees for internal operational activities.

## Architecture
Orchestrator (STATE.md SSoT) → Controller (inbox/outbox) → Teams → Worker Agents → Google Sheets API

## Design Principles
1. Human-in-the-loop: every sensitive modification requires human approval via dashboard
2. Least privilege: OAuth scopes spreadsheets + drive.file only
3. Complete audit: every operation logged with who, what, when, diff (SHA-256)
4. Immutability: reports and logs are append-only
5. Security: secrets in encrypted vault, never in git

## Agent Types
- **Worker agents**: execute tasks, write reports, audit logs
- **Team leads**: aggregate worker reports, resolve conflicts, produce team_report
- **Controller**: process inbox reports, emit directives, update STATE.md
- **Orchestrator**: maintain STATE.md as single source of truth

## Communication
- Async via filesystem: inbox/ (reports IN), outbox/ (directives OUT)
- Lock files: per-spreadsheet, 120s timeout, exponential backoff
- Schema: report_v1, directive_v1 (JSON with SHA-256 signatures)

## Technology
- Python >= 3.10
- Libraries: jsonschema, portalocker, pydantic, pytest
- Models: claude-sonnet-4-6 (default), claude-haiku-4-5 (sheets agent)
- CI: GitHub Actions (Python 3.10/3.11, flake8, mypy, pytest)
