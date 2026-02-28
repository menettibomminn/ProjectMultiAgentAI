"""Deterministic intent router for task-to-agent mapping."""

from __future__ import annotations

from .exceptions import OrchestratorError


class UnknownTaskTypeError(OrchestratorError):
    """Raised when a task type has no registered route."""

    def __init__(self, task_type: str) -> None:
        self.task_type = task_type
        super().__init__(f"No route registered for task type: {task_type!r}")


_DEFAULT_ROUTES: dict[str, str] = {
    "sheets": "sheets_agent",
    "analytics": "analytics_agent",
    "report": "report_agent",
}


class IntentRouter:
    """Map task types to agent identifiers deterministically.

    Parameters
    ----------
    routes:
        Optional custom routing table.  When *None*, the built-in default
        routes are used.  Any entries passed here are **merged** on top of
        the defaults.
    """

    def __init__(self, routes: dict[str, str] | None = None) -> None:
        self._routes: dict[str, str] = dict(_DEFAULT_ROUTES)
        if routes is not None:
            self._routes.update(routes)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, task: dict[str, object]) -> str:
        """Return the agent identifier for *task*.

        Raises
        ------
        UnknownTaskTypeError
            If ``task["type"]`` is missing, empty, or not in the table.
        """
        task_type = task.get("type")
        if not task_type or not isinstance(task_type, str):
            raise UnknownTaskTypeError(str(task_type) if task_type is not None else "")

        try:
            return self._routes[task_type]
        except KeyError:
            raise UnknownTaskTypeError(task_type) from None

    def register_route(self, task_type: str, agent_id: str) -> None:
        """Add or overwrite a route at runtime."""
        self._routes[task_type] = agent_id

    @property
    def routes(self) -> dict[str, str]:
        """Return an immutable *copy* of the routing table."""
        return dict(self._routes)
