#!/usr/bin/env python3
"""
benchmark.py — Performance benchmarks for ProjectMultiAgentAI agent pipelines.

Measures timing for each pipeline step and full E2E runs with synthetic data.
No external APIs are called — all benchmarks are local-only.

Usage:
    python ops/benchmark.py                     # Run all benchmarks
    python ops/benchmark.py --iterations 100    # Custom iteration count
    python ops/benchmark.py --component parser  # Single component
    python ops/benchmark.py --json              # JSON output

Components benchmarked:
    parser        — JSON Schema validation (Draft7)
    report        — Report generation (proposed_changes)
    audit         — Audit log writing (SHA-256 checksums)
    lock          — Lock acquire/release cycle
    rate_limiter  — Rate limiter try_acquire/remaining
    e2e           — Full SheetsAgent.run_once() pipeline
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is importable
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from Agents.sheets_agent.config import SheetsAgentConfig
from Agents.sheets_agent.sheets_task_parser import parse_task
from Agents.sheets_agent.sheets_report_generator import generate_report
from Agents.sheets_agent.sheets_audit_logger import write_audit_entry
from Agents.sheets_agent.lock_manager import LockManager
from Agents.sheets_agent.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Synthetic test data
# ---------------------------------------------------------------------------

def _make_task(num_changes: int = 1) -> dict[str, Any]:
    """Generate a valid synthetic task with *num_changes* requested changes."""
    changes = [
        {
            "op": "update",
            "range": f"A{i + 2}:C{i + 2}",
            "values": [[f"Name_{i}", f"Surname_{i}", str(i * 100)]],
        }
        for i in range(num_changes)
    ]
    return {
        "task_id": f"bench-{num_changes:04d}",
        "user_id": "bench@example.com",
        "team_id": "bench-team",
        "sheet": {
            "spreadsheet_id": "bench-spreadsheet-id",
            "sheet_name": "Foglio1",
        },
        "requested_changes": changes,
        "metadata": {
            "source": "api",
            "priority": "normal",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Benchmark runners
# ---------------------------------------------------------------------------

def _run_timed(fn: Any, iterations: int) -> dict[str, float]:
    """Run *fn()* for *iterations* and return timing stats in milliseconds."""
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        elapsed = (time.perf_counter() - t0) * 1000
        times.append(elapsed)
    return {
        "iterations": iterations,
        "mean_ms": round(statistics.mean(times), 3),
        "median_ms": round(statistics.median(times), 3),
        "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 3),
        "p99_ms": round(sorted(times)[int(len(times) * 0.99)], 3),
        "min_ms": round(min(times), 3),
        "max_ms": round(max(times), 3),
        "stdev_ms": round(statistics.stdev(times), 3) if len(times) > 1 else 0.0,
    }


def bench_parser(iterations: int) -> dict[str, Any]:
    """Benchmark JSON Schema validation (parse + validate)."""
    task = _make_task(5)
    raw = json.dumps(task)

    def run() -> None:
        parse_task(raw)

    return {"component": "parser", "description": "parse_task (5 changes)", **_run_timed(run, iterations)}


def bench_parser_large(iterations: int) -> dict[str, Any]:
    """Benchmark parser with 50 changes."""
    task = _make_task(50)
    raw = json.dumps(task)

    def run() -> None:
        parse_task(raw)

    return {"component": "parser_large", "description": "parse_task (50 changes)", **_run_timed(run, iterations)}


def bench_report(iterations: int) -> dict[str, Any]:
    """Benchmark report generation."""
    task = _make_task(5)

    def run() -> None:
        generate_report(task=task, agent_id="bench-agent", version=1)

    return {"component": "report", "description": "generate_report (5 changes)", **_run_timed(run, iterations)}


def bench_report_large(iterations: int) -> dict[str, Any]:
    """Benchmark report generation with 50 changes."""
    task = _make_task(50)

    def run() -> None:
        generate_report(task=task, agent_id="bench-agent", version=1)

    return {"component": "report_large", "description": "generate_report (50 changes)", **_run_timed(run, iterations)}


def bench_audit(iterations: int) -> dict[str, Any]:
    """Benchmark audit log writing (includes SHA-256 hashing)."""
    tmp = Path(tempfile.mkdtemp())
    audit_dir = tmp / "audit"
    audit_dir.mkdir()
    task = _make_task(5)
    report = generate_report(task=task, agent_id="bench-agent", version=1)

    counter = [0]

    def run() -> None:
        counter[0] += 1
        write_audit_entry(
            audit_dir=audit_dir,
            task_id=f"bench-{counter[0]:06d}",
            agent_id="bench-agent",
            user_id="bench@example.com",
            team_id="bench-team",
            config_version=1,
            op_steps=[{"step": "benchmark", "ts": datetime.now(timezone.utc).isoformat()}],
            report=report,
            error=None,
            duration_ms=1.0,
        )

    result = {"component": "audit", "description": "write_audit_entry (SHA-256)", **_run_timed(run, iterations)}
    shutil.rmtree(tmp, ignore_errors=True)
    return result


def bench_lock(iterations: int) -> dict[str, Any]:
    """Benchmark lock acquire/release cycle."""
    tmp = Path(tempfile.mkdtemp())
    locks_dir = tmp / "locks"
    locks_dir.mkdir()
    mgr = LockManager(
        locks_dir=locks_dir,
        owner="bench-agent",
        timeout_seconds=10,
        max_retries=0,
        backoff_base=0.01,
    )

    def run() -> None:
        mgr.acquire("bench-sheet", "bench-task")
        mgr.release("bench-sheet")

    result = {"component": "lock", "description": "acquire + release cycle", **_run_timed(run, iterations)}
    shutil.rmtree(tmp, ignore_errors=True)
    return result


def bench_rate_limiter(iterations: int) -> dict[str, Any]:
    """Benchmark rate limiter try_acquire (file I/O + window check)."""
    tmp = Path(tempfile.mkdtemp())
    limiter = RateLimiter(
        state_dir=tmp,
        name="bench",
        requests_per_minute=999_999,
        requests_per_day=999_999,
        jitter=False,
    )

    def run() -> None:
        limiter.try_acquire()

    result = {"component": "rate_limiter", "description": "try_acquire (file I/O)", **_run_timed(run, iterations)}
    shutil.rmtree(tmp, ignore_errors=True)
    return result


def bench_e2e(iterations: int) -> dict[str, Any]:
    """Benchmark full SheetsAgent.run_once() pipeline."""
    from Agents.sheets_agent.sheets_agent import SheetsAgent

    results_times: list[float] = []

    for i in range(iterations):
        tmp = Path(tempfile.mkdtemp())
        agent_id = "bench-agent"
        inbox = tmp / "inbox" / "sheets" / agent_id
        inbox.mkdir(parents=True)
        (tmp / "audit" / "sheets" / agent_id).mkdir(parents=True)
        (tmp / "locks").mkdir()
        health = tmp / "HEALTH.md"
        health.write_text("# HEALTH\n", encoding="utf-8")

        task = _make_task(5)
        (inbox / "task.json").write_text(json.dumps(task), encoding="utf-8")

        config = SheetsAgentConfig(
            agent_id=agent_id,
            team_id="bench-team",
            project_root=tmp,
            health_file_override=health,
            rate_requests_per_minute=999_999,
            rate_requests_per_day=999_999,
            rate_jitter=False,
        )
        agent = SheetsAgent(config)

        t0 = time.perf_counter()
        agent.run_once()
        elapsed = (time.perf_counter() - t0) * 1000
        results_times.append(elapsed)

        shutil.rmtree(tmp, ignore_errors=True)

    return {
        "component": "e2e",
        "description": "SheetsAgent.run_once() full pipeline",
        "iterations": iterations,
        "mean_ms": round(statistics.mean(results_times), 3),
        "median_ms": round(statistics.median(results_times), 3),
        "p95_ms": round(sorted(results_times)[int(len(results_times) * 0.95)], 3),
        "p99_ms": round(sorted(results_times)[int(len(results_times) * 0.99)], 3),
        "min_ms": round(min(results_times), 3),
        "max_ms": round(max(results_times), 3),
        "stdev_ms": round(statistics.stdev(results_times), 3) if len(results_times) > 1 else 0.0,
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BENCHMARKS: dict[str, Any] = {
    "parser": bench_parser,
    "parser_large": bench_parser_large,
    "report": bench_report,
    "report_large": bench_report_large,
    "audit": bench_audit,
    "lock": bench_lock,
    "rate_limiter": bench_rate_limiter,
    "e2e": bench_e2e,
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Performance benchmarks for ProjectMultiAgentAI"
    )
    parser.add_argument(
        "--iterations", "-n", type=int, default=50,
        help="Number of iterations per benchmark (default: 50)",
    )
    parser.add_argument(
        "--component", "-c", choices=list(BENCHMARKS.keys()),
        help="Run a single component benchmark",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON (default: human-readable table)",
    )
    args = parser.parse_args()

    if args.component:
        targets = {args.component: BENCHMARKS[args.component]}
    else:
        targets = BENCHMARKS

    results: list[dict[str, Any]] = []
    for name, fn in targets.items():
        if not args.json:
            print(f"  Running {name}...", end=" ", flush=True)
        result = fn(args.iterations)
        results.append(result)
        if not args.json:
            print(f"{result['mean_ms']:.1f}ms (p95: {result['p95_ms']:.1f}ms)")

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("\n" + "=" * 72)
        print(f"{'Component':<20} {'Mean':>8} {'Median':>8} {'P95':>8} {'P99':>8} {'StdDev':>8}")
        print("-" * 72)
        for r in results:
            print(
                f"{r['component']:<20} "
                f"{r['mean_ms']:>7.1f}ms "
                f"{r['median_ms']:>7.1f}ms "
                f"{r['p95_ms']:>7.1f}ms "
                f"{r['p99_ms']:>7.1f}ms "
                f"{r['stdev_ms']:>7.1f}ms"
            )
        print("=" * 72)

        # Throughput estimate
        e2e_results = [r for r in results if r["component"] == "e2e"]
        if e2e_results:
            mean_ms = e2e_results[0]["mean_ms"]
            tasks_per_sec = 1000 / mean_ms if mean_ms > 0 else float("inf")
            tasks_per_min = tasks_per_sec * 60
            print(f"\nThroughput estimate: {tasks_per_min:.1f} tasks/min "
                  f"({tasks_per_sec:.1f} tasks/sec)")
            slo_target = 5  # tasks/min from mcp_config.yml
            status = "PASS" if tasks_per_min >= slo_target else "FAIL"
            print(f"SLO target: {slo_target} tasks/min — {status}")


if __name__ == "__main__":
    main()
