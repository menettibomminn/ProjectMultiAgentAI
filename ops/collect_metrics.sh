#!/usr/bin/env bash
# =============================================================================
# collect_metrics.sh — Raccolta metriche dal sistema ProjectMultiAgentAI
# =============================================================================
# Legge i report JSON da Controller/inbox/ e aggrega le metriche principali
# (duration_ms, tokens_in, tokens_out, cost_eur) con breakdown per agent/status.
#
# Uso:
#   ./ops/collect_metrics.sh                              # tutti i report
#   ./ops/collect_metrics.sh --team sheets-team            # filtra per team
#   ./ops/collect_metrics.sh --period 2026-02-24           # filtra per data
#   ./ops/collect_metrics.sh --team sheets-team --period 2026-02-24
#   ./ops/collect_metrics.sh --include-processed           # include report elaborati
#   ./ops/collect_metrics.sh --health                      # aggiungi stato health
#
# Output: JSON aggregato su stdout
#
# Requisiti: jq >= 1.6
#
# Versione: 2.0.0
# Ultimo aggiornamento: 2026-02-24
# Owner: platform-team
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
PROJECT_ROOT="${PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
INBOX_DIR="${PROJECT_ROOT}/Controller/inbox"
STATE_DIR="${PROJECT_ROOT}/Controller/state"
TEAM_FILTER=""
PERIOD_FILTER=""
INCLUDE_PROCESSED=false
INCLUDE_HEALTH=false

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<'USAGE'
Usage: collect_metrics.sh [OPTIONS]

Options:
  --team <name>        Filter reports by team name
  --period <YYYY-MM-DD> Filter reports by date (matches timestamp field)
  --include-processed  Include already-processed reports (.processed.json)
  --health             Append system health summary to output
  -h, --help           Show this help message

Environment:
  PROJECT_ROOT         Override project root (default: git root)

Output:
  JSON object with aggregated metrics on stdout.
  Human-readable summary on stderr.
USAGE
    exit 0
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --team)
            TEAM_FILTER="$2"
            shift 2
            ;;
        --period)
            PERIOD_FILTER="$2"
            shift 2
            ;;
        --include-processed)
            INCLUDE_PROCESSED=true
            shift
            ;;
        --health)
            INCLUDE_HEALTH=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Error: unknown option '$1'" >&2
            usage
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
if ! command -v jq &>/dev/null; then
    echo '{"error": "jq is required but not installed. See https://jqlang.github.io/jq/"}' >&2
    exit 1
fi

if [[ ! -d "$INBOX_DIR" ]]; then
    echo '{"error": "Inbox directory not found", "path": "'"$INBOX_DIR"'"}' >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Collect report files
# ---------------------------------------------------------------------------
FIND_ARGS=()
if [[ "$INCLUDE_PROCESSED" == "true" ]]; then
    # Both .json and .processed.json
    FIND_ARGS=( "$INBOX_DIR" -type f \( -name "*_report.json" -o -name "*_report.processed.json" \) )
else
    # Only unprocessed
    FIND_ARGS=( "$INBOX_DIR" -type f -name "*_report.json" ! -name "*.processed.json" )
fi

# Exclude self-reports, examples, hash files
mapfile -t REPORT_FILES < <(
    find "${FIND_ARGS[@]}" 2>/dev/null \
        | grep -v "_self_report" \
        | grep -v "/example/" \
        | grep -v "\.hash$" \
        | sort
)

# Apply team filter (team is first directory component after inbox/)
if [[ -n "$TEAM_FILTER" ]]; then
    FILTERED=()
    for f in "${REPORT_FILES[@]}"; do
        rel="${f#"$INBOX_DIR/"}"
        team_part="${rel%%/*}"
        if [[ "$team_part" == "$TEAM_FILTER" ]]; then
            FILTERED+=("$f")
        fi
    done
    REPORT_FILES=("${FILTERED[@]+"${FILTERED[@]}"}")
fi

TOTAL_FILES=${#REPORT_FILES[@]}

if [[ "$TOTAL_FILES" -eq 0 ]]; then
    # No reports — emit empty summary
    jq -n '{
        collected_at: (now | todate),
        filters: {team: ($team // "all"), period: ($period // "all")},
        total_reports: 0,
        metrics: null,
        by_agent: {},
        by_status: {},
        note: "No report files found matching filters"
    }' \
        --arg team "$TEAM_FILTER" \
        --arg period "$PERIOD_FILTER"
    echo "No reports found." >&2
    exit 0
fi

# ---------------------------------------------------------------------------
# Merge all reports into a single JSON array, applying period filter via jq
# ---------------------------------------------------------------------------
MERGED=$(
    for f in "${REPORT_FILES[@]}"; do
        cat "$f"
    done | jq -s '.'
)

# Apply period filter (match date prefix in .timestamp field)
if [[ -n "$PERIOD_FILTER" ]]; then
    MERGED=$(echo "$MERGED" | jq --arg period "$PERIOD_FILTER" '
        [.[] | select(.timestamp // "" | startswith($period))]
    ')
fi

# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------
RESULT=$(echo "$MERGED" | jq --arg team "${TEAM_FILTER:-all}" --arg period "${PERIOD_FILTER:-all}" '
    # Helper: safe division
    def safe_div(a; b): if b == 0 then 0 else a / b end;

    # Extract metrics arrays (filter nulls)
    [.[] | .metrics // {}] as $metrics |
    [.[] | .metrics.duration_ms // 0] as $durations |
    [.[] | .metrics.tokens_in // 0] as $tokens_in |
    [.[] | .metrics.tokens_out // 0] as $tokens_out |
    [.[] | .metrics.cost_eur // 0] as $costs |

    # Group by agent
    (group_by(.agent) | map({
        key: (.[0].agent // "unknown"),
        value: {
            count: length,
            success: [.[] | select(.status == "success")] | length,
            error: [.[] | select(.status == "error" or .status == "failure")] | length,
            avg_duration_ms: (safe_div([.[] | .metrics.duration_ms // 0] | add; length) | round),
            total_cost_eur: ([.[] | .metrics.cost_eur // 0] | add),
            total_tokens_in: ([.[] | .metrics.tokens_in // 0] | add),
            total_tokens_out: ([.[] | .metrics.tokens_out // 0] | add)
        }
    }) | from_entries) as $by_agent |

    # Group by status
    (group_by(.status) | map({
        key: (.[0].status // "unknown"),
        value: length
    }) | from_entries) as $by_status |

    {
        collected_at: (now | todate),
        filters: {team: $team, period: $period},
        total_reports: length,
        metrics: {
            duration_ms: {
                total: ($durations | add),
                avg: (safe_div($durations | add; $durations | length) | round),
                min: ($durations | min),
                max: ($durations | max)
            },
            tokens: {
                total_in: ($tokens_in | add),
                total_out: ($tokens_out | add),
                avg_in: (safe_div($tokens_in | add; $tokens_in | length) | round),
                avg_out: (safe_div($tokens_out | add; $tokens_out | length) | round)
            },
            cost_eur: {
                total: ($costs | add),
                avg: (safe_div($costs | add; $costs | length)),
                min: ($costs | min),
                max: ($costs | max)
            }
        },
        by_agent: $by_agent,
        by_status: $by_status
    }
')

# ---------------------------------------------------------------------------
# Optionally append system health summary
# ---------------------------------------------------------------------------
if [[ "$INCLUDE_HEALTH" == "true" ]]; then
    HEALTH_FILE="${STATE_DIR}/system_health.json"
    if [[ -f "$HEALTH_FILE" ]]; then
        RESULT=$(echo "$RESULT" | jq --slurpfile health "$HEALTH_FILE" '
            . + {system_health: $health[0]}
        ')
    else
        RESULT=$(echo "$RESULT" | jq '. + {system_health: "not available"}')
    fi
fi

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
echo "$RESULT"

# Human-readable summary on stderr
echo "$RESULT" | jq -r '
    "=== ProjectMultiAgentAI — Metrics Summary ===",
    "Collected: \(.collected_at)",
    "Filters:   team=\(.filters.team) period=\(.filters.period)",
    "Reports:   \(.total_reports)",
    "",
    "Duration:  total=\(.metrics.duration_ms.total)ms avg=\(.metrics.duration_ms.avg)ms",
    "Tokens:    in=\(.metrics.tokens.total_in) out=\(.metrics.tokens.total_out)",
    "Cost:      EUR \(.metrics.cost_eur.total) (avg \(.metrics.cost_eur.avg))",
    "",
    "By status: \(.by_status | to_entries | map("\(.key)=\(.value)") | join(" "))",
    "By agent:  \(.by_agent | to_entries | map("\(.key)=\(.value.count)") | join(" "))"
' >&2
