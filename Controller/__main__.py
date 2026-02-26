"""Entry point for running the Controller as a module.

Usage:
    python -m Controller --run-once
    python -m Controller --run-once --team sheets-team
"""
from __future__ import annotations

import argparse
import sys

from Controller.controller import Controller
from Controller.config import ControllerConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Controller — inbox/outbox processor")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Process inbox once and exit",
    )
    parser.add_argument(
        "--team",
        default=None,
        help="Only process reports from this team",
    )
    parser.add_argument(
        "--task",
        default=None,
        help="Path to a controller task JSON file to process",
    )
    parser.add_argument(
        "--check-health",
        action="store_true",
        help="Run a standalone health check on all agents and exit",
    )
    args = parser.parse_args()

    if not args.run_once and not args.task and not args.check_health:
        parser.print_help()
        print("\nError: --run-once, --task, or --check-health is required")
        return 1

    config = ControllerConfig.from_env()
    ctrl = Controller(config)

    if args.check_health:
        import json
        result = ctrl.check_health()
        print(json.dumps(result, indent=2))
        success = result["overall_status"] != "down"
    elif args.task:
        from pathlib import Path
        success = ctrl.process_task(Path(args.task))
    else:
        success = ctrl.run_once(team_filter=args.team)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
