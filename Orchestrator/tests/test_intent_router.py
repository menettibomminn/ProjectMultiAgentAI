"""Tests for IntentRouter."""

from __future__ import annotations

import pytest

from Orchestrator.intent_router import IntentRouter, UnknownTaskTypeError


# -----------------------------------------------------------------------
# Known-type routing
# -----------------------------------------------------------------------


class TestRouteKnownTypes:
    def test_route_sheets(self) -> None:
        router = IntentRouter()
        assert router.route({"type": "sheets"}) == "sheets_agent"

    def test_route_analytics(self) -> None:
        router = IntentRouter()
        assert router.route({"type": "analytics"}) == "analytics_agent"

    def test_route_report(self) -> None:
        router = IntentRouter()
        assert router.route({"type": "report"}) == "report_agent"


# -----------------------------------------------------------------------
# Unknown / missing type
# -----------------------------------------------------------------------


class TestRouteUnknownType:
    def test_unknown_type_raises(self) -> None:
        router = IntentRouter()
        with pytest.raises(UnknownTaskTypeError) as exc_info:
            router.route({"type": "nonexistent"})
        assert exc_info.value.task_type == "nonexistent"

    def test_missing_type_key_raises(self) -> None:
        router = IntentRouter()
        with pytest.raises(UnknownTaskTypeError):
            router.route({})

    def test_empty_type_raises(self) -> None:
        router = IntentRouter()
        with pytest.raises(UnknownTaskTypeError) as exc_info:
            router.route({"type": ""})
        assert exc_info.value.task_type == ""


# -----------------------------------------------------------------------
# Custom route registration
# -----------------------------------------------------------------------


class TestRegisterCustomRoute:
    def test_register_new_route(self) -> None:
        router = IntentRouter()
        router.register_route("billing", "billing_agent")
        assert router.route({"type": "billing"}) == "billing_agent"

    def test_override_existing_route(self) -> None:
        router = IntentRouter()
        router.register_route("sheets", "sheets_v2_agent")
        assert router.route({"type": "sheets"}) == "sheets_v2_agent"

    def test_init_with_custom_routes(self) -> None:
        router = IntentRouter(routes={"custom": "custom_agent"})
        # Custom route present
        assert router.route({"type": "custom"}) == "custom_agent"
        # Defaults still available
        assert router.route({"type": "sheets"}) == "sheets_agent"

    def test_routes_property_returns_copy(self) -> None:
        router = IntentRouter()
        routes = router.routes
        routes["injected"] = "hacked_agent"
        # Original must be unaffected
        with pytest.raises(UnknownTaskTypeError):
            router.route({"type": "injected"})
