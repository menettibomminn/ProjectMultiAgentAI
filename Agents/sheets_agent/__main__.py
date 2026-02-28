"""Entry point for running the sheets agent as a module.

Usage:
    python -m Agents.sheets_agent --run-once
    python -m Agents.sheets_agent --loop
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from Agents.sheets_agent.config import SheetsAgentConfig
from Agents.sheets_agent.sheets_agent import SheetsAgent


def main() -> int:
    parser = argparse.ArgumentParser(description="Sheets Worker Agent")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Process a single task and exit",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run in continuous loop mode (poll inbox for tasks)",
    )
    parser.add_argument(
        "--agent-id",
        default=None,
        help="Override the agent ID (default: from env or config)",
    )
    args = parser.parse_args()

    config = SheetsAgentConfig.from_env()
    if args.agent_id:
        config = replace(config, agent_id=args.agent_id)

    if args.loop or config.loop_enabled:
        from Agents.sheets_agent.agent_loop import AgentLoop

        agent = SheetsAgent(config)
        loop = AgentLoop(agent=agent, config=config)
        loop.start()
        return 0

    if args.run_once:
        agent = SheetsAgent(config)
        success = agent.run_once()
        return 0 if success else 1

    parser.print_help()
    print("\nError: --run-once or --loop is required")
    return 1


if __name__ == "__main__":
    sys.exit(main())
