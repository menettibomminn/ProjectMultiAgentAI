"""Entry point for running the sheets agent as a module.

Usage:
    python -m Agents.sheets_agent --run-once
"""
from __future__ import annotations

import argparse
import sys

from Agents.sheets_agent.sheets_agent import SheetsAgent
from Agents.sheets_agent.config import SheetsAgentConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Sheets Worker Agent")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Process a single task and exit",
    )
    parser.add_argument(
        "--agent-id",
        default=None,
        help="Override the agent ID (default: from env or config)",
    )
    args = parser.parse_args()

    if not args.run_once:
        parser.print_help()
        print("\nError: --run-once is required (continuous mode not yet supported)")
        return 1

    config = SheetsAgentConfig.from_env()
    if args.agent_id:
        config = SheetsAgentConfig(
            agent_id=args.agent_id,
            team_id=config.team_id,
            project_root=config.project_root,
            lock_backend=config.lock_backend,
            lock_timeout_seconds=config.lock_timeout_seconds,
            lock_max_retries=config.lock_max_retries,
            task_timeout_seconds=config.task_timeout_seconds,
        )

    agent = SheetsAgent(config)
    success = agent.run_once()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
