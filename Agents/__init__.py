"""ProjectMultiAgentAI — Agent packages.

Available agents:
    - sheets_agent   : Google Sheets worker (read-only proposals)
    - auth_agent     : Authentication and token management
    - backend_agent  : Business logic, validation, routing
    - frontend_agent : UI component proposals and approval workflows
    - metrics_agent  : Metrics collection, aggregation, SLO monitoring
"""

AVAILABLE_AGENTS = [
    "sheets_agent",
    "auth_agent",
    "backend_agent",
    "frontend_agent",
    "metrics_agent",
]
