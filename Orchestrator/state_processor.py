"""Orchestrator STATE.md processor — read, update, backup, verify, rebuild.

STATE.md is the Single Source of Truth for the entire ProjectMultiAgentAI system.
Only the Controller writes to STATE.md via this processor.

Operations:
    parse_state()    — Parse STATE.md into a structured StateDocument
    render_state()   — Render StateDocument back to markdown
    update_state()   — Apply state_changes and write with backup
    backup_state()   — Copy STATE.md to a timestamped backup file
    verify_state()   — Check consistency between STATE.md and actual state
    rebuild_state()  — Reconstruct STATE.md from Controller inbox reports
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

_EMPTY_MARKERS = frozenset({
    "(nessun lock attivo)",
    "(nessuna direttiva pendente)",
    "(nessun cambio in attesa)",
})


@dataclass
class StateDocument:
    """Parsed representation of STATE.md."""

    frontmatter: dict[str, str] = field(default_factory=dict)
    last_updated: str = ""
    teams: list[dict[str, str]] = field(default_factory=list)
    agents: list[dict[str, str]] = field(default_factory=list)
    active_locks: list[dict[str, str]] = field(default_factory=list)
    pending_directives: list[dict[str, str]] = field(default_factory=list)
    system_metrics: dict[str, Any] = field(default_factory=dict)
    candidate_changes: list[dict[str, str]] = field(default_factory=list)
    change_history: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class StateChange:
    """A single change to be applied to STATE.md."""

    section: str  # team_status | agent_status | active_locks | ...
    field: str    # the key field value (e.g. agent name, team name)
    column: str   # which column to update
    old_value: str
    new_value: str
    reason: str
    triggered_by: str  # report_id or directive_id


@dataclass(frozen=True)
class VerifyResult:
    """Result of a state verification check."""

    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Markdown table parsing / rendering
# ---------------------------------------------------------------------------


def _parse_table(lines: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Parse a markdown table into (headers, rows).

    Returns the column headers and a list of dicts keyed by header name.
    Empty placeholder rows (e.g. ``(nessun lock attivo)``) are skipped.
    """
    if len(lines) < 2:
        return [], []

    # Header row
    headers = [h.strip() for h in lines[0].split("|") if h.strip()]

    # Skip separator row (|---|---|...)
    data_lines = lines[2:] if len(lines) > 2 else []

    rows: list[dict[str, str]] = []
    for line in data_lines:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if not cells:
            continue
        # Skip empty placeholder rows
        if any(marker in cells[0] for marker in _EMPTY_MARKERS):
            continue
        row = {}
        for i, header in enumerate(headers):
            row[header] = cells[i] if i < len(cells) else "—"
        rows.append(row)
    return headers, rows


def _render_table(
    headers: list[str],
    rows: list[dict[str, str]],
    empty_placeholder: str = "",
) -> str:
    """Render a list of dicts as a markdown table.

    Args:
        headers: Column header names.
        rows: List of dicts keyed by header name.
        empty_placeholder: Text for the first cell when no rows exist.
    """
    lines: list[str] = []

    # Header
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")

    if not rows and empty_placeholder:
        cells = [empty_placeholder] + ["—"] * (len(headers) - 1)
        lines.append("| " + " | ".join(cells) + " |")
    else:
        for row in rows:
            cells = [row.get(h, "—") for h in headers]
            lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parse STATE.md
# ---------------------------------------------------------------------------

_SECTION_MAP: dict[str, str] = {
    "team status": "teams",
    "agent status": "agents",
    "active locks": "active_locks",
    "pending directives": "pending_directives",
    "candidate changes (awaiting human approval)": "candidate_changes",
    "change history": "change_history",
}


def parse_state(state_path: Path) -> StateDocument:
    """Parse STATE.md into a :class:`StateDocument`.

    Args:
        state_path: Path to STATE.md.

    Returns:
        Parsed StateDocument with all sections populated.
    """
    text = state_path.read_text(encoding="utf-8")
    doc = StateDocument()

    # --- Frontmatter ---
    fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                doc.frontmatter[key.strip()] = value.strip().strip('"')

    # --- Timestamp ---
    ts_match = re.search(
        r"### Timestamp Ultimo Aggiornamento\s*\n```\n(.*?)\n```",
        text,
        re.DOTALL,
    )
    if ts_match:
        doc.last_updated = ts_match.group(1).strip()

    # --- Markdown table sections ---
    # Split by ### headers
    section_pattern = re.compile(r"^### (.+)$", re.MULTILINE)
    sections = section_pattern.split(text)

    # sections alternates: [text_before, header1, body1, header2, body2, ...]
    for i in range(1, len(sections) - 1, 2):
        header = sections[i].strip().lower()
        body = sections[i + 1]

        attr_name = _SECTION_MAP.get(header)
        if attr_name:
            # Find table lines (lines starting with |)
            table_lines = [
                ln for ln in body.splitlines()
                if ln.strip().startswith("|")
            ]
            if table_lines:
                _, rows = _parse_table(table_lines)
                setattr(doc, attr_name, rows)

    # --- System Metrics (JSON block) ---
    metrics_match = re.search(
        r"### System Metrics.*?\n```json\n(.*?)\n```",
        text,
        re.DOTALL,
    )
    if metrics_match:
        try:
            doc.system_metrics = json.loads(metrics_match.group(1))
        except json.JSONDecodeError:
            doc.system_metrics = {}

    return doc


# ---------------------------------------------------------------------------
# Render STATE.md
# ---------------------------------------------------------------------------

_TEAM_HEADERS = ["Team", "Status", "Active Workers", "Last Report", "Pending Tasks"]
_AGENT_HEADERS = ["Agent", "Team", "Status", "Last Task", "Health"]
_LOCK_HEADERS = ["Sheet ID", "Owner", "Since", "Task ID"]
_DIRECTIVE_HEADERS = ["Directive ID", "Target", "Command", "Created", "Status"]
_CANDIDATE_HEADERS = [
    "Change ID", "Team", "Sheet", "Description", "Submitted", "Status",
]
_HISTORY_HEADERS = ["Timestamp", "Changed By", "Field", "Old Value", "New Value"]


def render_state(doc: StateDocument) -> str:
    """Render a :class:`StateDocument` back to STATE.md markdown.

    Args:
        doc: Parsed StateDocument.

    Returns:
        Complete STATE.md content as a string.
    """
    parts: list[str] = []

    # Frontmatter
    parts.append("---")
    for key, value in doc.frontmatter.items():
        parts.append(f'{key}: "{value}"')
    parts.append("---")
    parts.append("")

    # Title and rules
    parts.append("# Orchestrator — STATE.md")
    parts.append("")
    parts.append(
        "> **PRIORITA MASSIMA:** Questo file è la **Single Source of Truth** del sistema"
    )
    parts.append(
        "> ProjectMultiAgentAI. Tutti gli agenti e il controller fanno riferimento a questo"
    )
    parts.append("> file per determinare lo stato corrente del sistema.")
    parts.append("")
    parts.append("> **Regole:**")
    parts.append("> - Solo il **controller** può aggiornare questo file.")
    parts.append(
        "> - Ogni aggiornamento deve essere loggato in `ops/logs/audit.log` con hash."
    )
    parts.append(
        "> - In caso di conflitto tra questo file e qualsiasi altro stato, "
        "questo file VINCE."
    )
    parts.append("> - Gli agenti leggono questo file in read-only.")
    parts.append("")

    # Stato Corrente
    parts.append("## Stato Corrente del Sistema")
    parts.append("")

    # Timestamp
    parts.append("### Timestamp Ultimo Aggiornamento")
    parts.append("```")
    parts.append(doc.last_updated)
    parts.append("```")
    parts.append("")

    # Team Status
    parts.append("### Team Status")
    parts.append("")
    parts.append(_render_table(
        _TEAM_HEADERS, doc.teams, "(nessun team registrato)",
    ))
    parts.append("")

    # Agent Status
    parts.append("### Agent Status")
    parts.append("")
    parts.append(_render_table(
        _AGENT_HEADERS, doc.agents, "(nessun agente registrato)",
    ))
    parts.append("")

    # Active Locks
    parts.append("### Active Locks")
    parts.append("")
    parts.append(_render_table(
        _LOCK_HEADERS, doc.active_locks, "(nessun lock attivo)",
    ))
    parts.append("")

    # Pending Directives
    parts.append("### Pending Directives")
    parts.append("")
    parts.append(_render_table(
        _DIRECTIVE_HEADERS, doc.pending_directives,
        "(nessuna direttiva pendente)",
    ))
    parts.append("")

    # System Metrics
    parts.append("### System Metrics (Last Cycle)")
    parts.append("")
    parts.append("```json")
    parts.append(json.dumps(doc.system_metrics, indent=2, ensure_ascii=False))
    parts.append("```")
    parts.append("")

    # Candidate Changes
    parts.append("### Candidate Changes (Awaiting Human Approval)")
    parts.append("")
    parts.append(_render_table(
        _CANDIDATE_HEADERS, doc.candidate_changes,
        "(nessun cambio in attesa)",
    ))
    parts.append("")

    # Change History
    parts.append("### Change History")
    parts.append("")
    parts.append(
        "> Ultime 10 modifiche a questo file (append-only in questa sezione)."
    )
    parts.append("")
    parts.append(_render_table(_HISTORY_HEADERS, doc.change_history))
    parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

MAX_BACKUPS = 100


def backup_state(state_path: Path, backup_dir: Path | None = None) -> Path:
    """Create a timestamped backup of STATE.md.

    Args:
        state_path: Path to the current STATE.md.
        backup_dir: Directory for backups. Defaults to state_path.parent.

    Returns:
        Path to the created backup file.
    """
    if backup_dir is None:
        backup_dir = state_path.parent
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f".state_backup_{ts}.md"
    shutil.copy2(state_path, backup_path)

    # Cleanup old backups (keep last MAX_BACKUPS)
    backups = sorted(backup_dir.glob(".state_backup_*.md"))
    if len(backups) > MAX_BACKUPS:
        for old in backups[: len(backups) - MAX_BACKUPS]:
            old.unlink()

    return backup_path


# ---------------------------------------------------------------------------
# Apply state changes
# ---------------------------------------------------------------------------

_SECTION_KEY: dict[str, str] = {
    "team_status": "Team",
    "agent_status": "Agent",
    "active_locks": "Sheet ID",
    "pending_directives": "Directive ID",
    "candidate_changes": "Change ID",
}

_SECTION_ATTR: dict[str, str] = {
    "team_status": "teams",
    "agent_status": "agents",
    "active_locks": "active_locks",
    "pending_directives": "pending_directives",
    "candidate_changes": "candidate_changes",
}


def apply_state_changes(
    doc: StateDocument,
    changes: list[StateChange],
) -> StateDocument:
    """Apply a list of state changes to a StateDocument (in-place mutation).

    Each change targets a section and a specific row (identified by the key
    field). If the row doesn't exist and the change is an update, it is added.

    Changes to ``system_metrics`` update the metrics dict directly.

    A change history entry is appended for each applied change (capped at 10).

    Args:
        doc: The state document to mutate.
        changes: List of StateChange instances to apply.

    Returns:
        The mutated StateDocument (same object).
    """
    now = datetime.now(timezone.utc).isoformat()

    for change in changes:
        # System metrics — update dict directly
        if change.section == "system_metrics":
            doc.system_metrics[change.column] = _coerce_metric(change.new_value)
            _append_history(doc, now, change)
            continue

        # Table-based sections
        attr_name = _SECTION_ATTR.get(change.section)
        key_col = _SECTION_KEY.get(change.section)
        if attr_name is None or key_col is None:
            continue

        rows: list[dict[str, str]] = getattr(doc, attr_name)

        # Find existing row
        target_row: dict[str, str] | None = None
        for row in rows:
            if row.get(key_col) == change.field:
                target_row = row
                break

        if target_row is not None:
            target_row[change.column] = change.new_value
        else:
            # Create new row with key field and the changed column
            new_row = {key_col: change.field, change.column: change.new_value}
            rows.append(new_row)

        _append_history(doc, now, change)

    # Update timestamp
    doc.last_updated = now
    doc.frontmatter["last_updated"] = now[:10]

    return doc


def _coerce_metric(value: str) -> int | float | str:
    """Try to coerce a string to int or float for metrics."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _append_history(
    doc: StateDocument, timestamp: str, change: StateChange
) -> None:
    """Append a change history entry, keeping only the last 10."""
    entry = {
        "Timestamp": timestamp,
        "Changed By": change.triggered_by,
        "Field": f"{change.section}.{change.field}.{change.column}",
        "Old Value": change.old_value,
        "New Value": change.new_value,
    }
    doc.change_history.append(entry)
    # Keep last 10
    if len(doc.change_history) > 10:
        doc.change_history = doc.change_history[-10:]


# ---------------------------------------------------------------------------
# Write STATE.md (with backup and hash)
# ---------------------------------------------------------------------------


def compute_state_checksum(content: str) -> str:
    """SHA-256 hex digest of the STATE.md content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_state(
    doc: StateDocument,
    state_path: Path,
    *,
    create_backup: bool = True,
    backup_dir: Path | None = None,
) -> tuple[Path, str]:
    """Render and atomically write STATE.md with optional backup.

    Args:
        doc: The StateDocument to write.
        state_path: Path to STATE.md.
        create_backup: Whether to backup the current STATE.md first.
        backup_dir: Override backup directory.

    Returns:
        Tuple of (state_path, checksum).
    """
    # Backup existing state
    if create_backup and state_path.exists():
        backup_state(state_path, backup_dir)

    content = render_state(doc)
    checksum = compute_state_checksum(content)

    # Atomic write: write to .tmp then rename
    tmp_path = state_path.with_suffix(".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(state_path)

    # Write checksum companion
    hash_path = state_path.with_suffix(".md.hash")
    hash_path.write_text(checksum + "\n", encoding="utf-8")

    return state_path, checksum


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify_state(state_path: Path) -> VerifyResult:
    """Verify STATE.md consistency and integrity.

    Checks:
    1. File exists and is parseable.
    2. Checksum matches companion .hash file (if present).
    3. Frontmatter has required fields.
    4. All teams referenced by agents exist in team table.
    5. System metrics has required fields.

    Args:
        state_path: Path to STATE.md.

    Returns:
        VerifyResult with ok=True if all checks pass.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Check 1: file exists
    if not state_path.exists():
        return VerifyResult(ok=False, errors=["STATE.md not found"])

    # Check 2: parse
    try:
        doc = parse_state(state_path)
    except Exception as exc:
        return VerifyResult(ok=False, errors=[f"Parse error: {exc}"])

    # Check 3: checksum
    hash_path = state_path.with_suffix(".md.hash")
    if hash_path.exists():
        expected = hash_path.read_text(encoding="utf-8").strip()
        actual = compute_state_checksum(state_path.read_text(encoding="utf-8"))
        if actual != expected:
            errors.append(
                f"Checksum mismatch: expected {expected[:12]}... "
                f"got {actual[:12]}..."
            )

    # Check 4: frontmatter
    required_fm = {"version", "last_updated", "owner", "project"}
    missing_fm = required_fm - set(doc.frontmatter.keys())
    if missing_fm:
        errors.append(f"Missing frontmatter fields: {missing_fm}")

    # Check 5: agents reference valid teams
    team_names = {t.get("Team", "") for t in doc.teams}
    team_names.add("—")  # unassigned agents use "—"
    for agent in doc.agents:
        agent_team = agent.get("Team", "—")
        if agent_team not in team_names:
            warnings.append(
                f"Agent {agent.get('Agent', '?')} references unknown team "
                f"'{agent_team}'"
            )

    # Check 6: system metrics required fields
    required_metrics = {
        "cycle_timestamp", "total_tasks_completed", "total_tasks_failed",
    }
    if doc.system_metrics:
        missing_metrics = required_metrics - set(doc.system_metrics.keys())
        if missing_metrics:
            warnings.append(f"System metrics missing fields: {missing_metrics}")
    else:
        warnings.append("System metrics section is empty")

    return VerifyResult(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Rebuild from inbox reports
# ---------------------------------------------------------------------------


def rebuild_state(
    inbox_dir: Path,
    state_path: Path,
    *,
    initial_doc: StateDocument | None = None,
) -> tuple[StateDocument, int]:
    """Reconstruct STATE.md by replaying all processed reports from inbox.

    Scans all report JSON files (including .processed.json) in the inbox,
    sorts them by timestamp, and rebuilds the agent/team/metrics state.

    Args:
        inbox_dir: Path to Controller/inbox/.
        state_path: Path to STATE.md (for backup before overwrite).
        initial_doc: Base document to start from. Uses default if None.

    Returns:
        Tuple of (rebuilt StateDocument, number of reports applied).
    """
    if initial_doc is None:
        initial_doc = _make_initial_state()

    doc = initial_doc

    # Collect all report files
    report_files: list[Path] = []
    if inbox_dir.exists():
        for json_file in inbox_dir.rglob("*.json"):
            name = json_file.name
            # Include both processed and unprocessed reports
            if "_self_report" in name:
                continue
            if "example" in str(json_file):
                continue
            if name.endswith(".hash"):
                continue
            report_files.append(json_file)

    # Sort by filename (which starts with timestamp)
    report_files.sort(key=lambda p: p.name)

    count = 0
    for report_path in report_files:
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        agent = data.get("agent", "unknown")
        status = data.get("status", "unknown")
        task_id = data.get("task_id", "—")
        timestamp = data.get("timestamp", "—")

        # Update agent status
        _upsert_row(
            doc.agents,
            key_col="Agent",
            key_val=agent,
            updates={
                "Status": "idle" if status == "success" else "error",
                "Last Task": task_id,
                "Health": "healthy" if status == "success" else "degraded",
            },
        )

        # Update team status from inbox path
        try:
            rel = report_path.relative_to(inbox_dir)
            parts = rel.parts
            if len(parts) >= 1:
                team_name = parts[0]
                _upsert_row(
                    doc.teams,
                    key_col="Team",
                    key_val=team_name,
                    updates={
                        "Last Report": timestamp,
                        "Status": "idle",
                    },
                )
        except ValueError:
            pass

        # Update metrics
        metrics = data.get("metrics", {})
        cost = metrics.get("cost_eur", 0)
        if status == "success":
            doc.system_metrics["total_tasks_completed"] = (
                doc.system_metrics.get("total_tasks_completed", 0) + 1
            )
        else:
            doc.system_metrics["total_tasks_failed"] = (
                doc.system_metrics.get("total_tasks_failed", 0) + 1
            )
        doc.system_metrics["total_cost_eur"] = round(
            doc.system_metrics.get("total_cost_eur", 0.0) + cost, 6
        )
        tokens_in = metrics.get("tokens_in", 0)
        tokens_out = metrics.get("tokens_out", 0)
        doc.system_metrics["total_tokens_consumed"] = (
            doc.system_metrics.get("total_tokens_consumed", 0)
            + tokens_in + tokens_out
        )

        count += 1

    # Final timestamp
    doc.last_updated = datetime.now(timezone.utc).isoformat()
    doc.system_metrics["cycle_timestamp"] = doc.last_updated

    # Active teams/agents count
    doc.system_metrics["active_teams"] = len(doc.teams)
    doc.system_metrics["active_agents"] = len(doc.agents)

    return doc, count


def _upsert_row(
    rows: list[dict[str, str]],
    key_col: str,
    key_val: str,
    updates: dict[str, str],
) -> None:
    """Update a row matching key_col==key_val, or append a new one."""
    for row in rows:
        if row.get(key_col) == key_val:
            row.update(updates)
            return
    new_row = {key_col: key_val, **updates}
    rows.append(new_row)


def _make_initial_state() -> StateDocument:
    """Create a blank StateDocument with default structure."""
    return StateDocument(
        frontmatter={
            "version": "1.0.0",
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "owner": "platform-team",
            "project": "ProjectMultiAgentAI",
            "priority": "HIGHEST — Single Source of Truth",
        },
        last_updated=datetime.now(timezone.utc).isoformat(),
        system_metrics={
            "cycle_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_tasks_completed": 0,
            "total_tasks_failed": 0,
            "total_cost_eur": 0.0,
            "total_tokens_consumed": 0,
            "active_teams": 0,
            "active_agents": 0,
        },
    )
