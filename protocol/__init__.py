"""Structured message protocol for inter-agent communication."""

from .message import AgentMessage, InvalidMessageStatusError

__all__ = [
    "AgentMessage",
    "InvalidMessageStatusError",
]
