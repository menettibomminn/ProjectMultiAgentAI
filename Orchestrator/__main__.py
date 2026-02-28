"""Entry point for running the Orchestrator as a module.

Usage:
    python -m Orchestrator --run-once
    python -m Orchestrator --run-once --orchestrator-dir /app/Orchestrator
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from Orchestrator.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


def _default_orchestrator_dir() -> Path:
    """Return the Orchestrator package directory (sibling to this file)."""
    return Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Orchestrator — state management service"
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Validate state integrity once and exit",
    )
    parser.add_argument(
        "--orchestrator-dir",
        default=None,
        help="Path to the Orchestrator directory (default: auto-detect)",
    )
    args = parser.parse_args()

    if not args.run_once:
        parser.print_help()
        print(
            "\nError: --run-once is required"
            " (continuous mode not yet supported)"
        )
        return 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    orch_dir = (
        Path(args.orchestrator_dir)
        if args.orchestrator_dir
        else _default_orchestrator_dir()
    )
    orch = Orchestrator(orchestrator_dir=orch_dir)

    result = orch.verify_state_integrity()
    if result.valid:
        logger.info("State validation passed")
    else:
        logger.warning(
            "State validation found %d error(s)",
            len(result.errors),
        )
        for err in result.errors:
            logger.warning("  - %s", err)

    if result.warnings:
        for warn in result.warnings:
            logger.info("  warning: %s", warn)

    health = orch.health_check()
    logger.info("Health status: %s", health.status.value)

    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
