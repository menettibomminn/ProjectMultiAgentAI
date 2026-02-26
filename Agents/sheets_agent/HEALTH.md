---
version: "1.0.0"
last_updated: "2026-02-23"
owner: "sheets-team"
project: "ProjectMultiAgentAI"
append_only: true
---

# Sheets Worker Agent — HEALTH

> **Questo file e append-only.** L'agente appende una entry dopo ogni task.
> L'ultima entry rappresenta lo stato corrente dell'agente.

## Fields

| Field | Description |
|---|---|
| `last_run_timestamp` | ISO 8601 UTC timestamp of last run |
| `last_task_id` | ID of the last processed task |
| `last_status` | `healthy` / `degraded` / `down` |
| `consecutive_failures` | Count of consecutive failed runs (resets on success) |
| `version` | Config version |
| `queue_length_estimate` | Number of pending .json files in inbox |
| `notes` | Maintenance notes |

## State Transitions

| From | To | Trigger |
|---|---|---|
| `healthy` | `degraded` | Any error during task processing |
| `healthy` | `down` | 3+ consecutive failures |
| `degraded` | `healthy` | Successful task processing |
| `down` | `healthy` | Restart + successful task processing |

## Status Log

### 2026-02-23T14:00:00Z — INIT

| Field | Value |
|---|---|
| last_run_timestamp | 2026-02-23T14:00:00Z |
| last_task_id | none |
| last_status | healthy |
| consecutive_failures | 0 |
| version | 1 |
| queue_length_estimate | 0 |
| notes | Initial deployment — agent ready |

<!-- Append new entries below this line -->

### 2026-02-23T14:36:50.018311+00:00 — Task a1b2c3d4-e5f6-7890-abcd-ef1234567890

| Field | Value |
|---|---|
| last_run_timestamp | 2026-02-23T14:36:50.018311+00:00 |
| last_task_id | a1b2c3d4-e5f6-7890-abcd-ef1234567890 |
| last_status | healthy |
| consecutive_failures | 0 |
| version | 1 |
| queue_length_estimate | 1 |
| notes | auto-updated by sheets_agent.py |
