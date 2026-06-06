"""Smoke test: the MCP server module imports and registers its tools. Skips
cleanly if the `mcp` SDK isn't installed (the pure-core tests don't need it).
This catches wiring/signature breakage without running a server or touching
any saved state."""

import pytest

mcp_sdk = pytest.importorskip("mcp")  # noqa: F841


def test_server_exposes_expected_tools():
    import mealplanner.server as server

    expected = {
        "list_recipes", "get_recipe", "suggest_recipes", "plan_week",
        "get_current_plan", "generate_shopping_list", "export_plan",
        "record_cooked", "add_recipe", "add_recipes", "set_course", "swap_meal",
        "remove_meal", "import_recipes",
    }
    missing = {name for name in expected if not hasattr(server, name)}
    assert not missing, f"server missing tools: {missing}"


def test_transport_defaults_to_stdio():
    from mealplanner.server import _resolve_transport

    assert _resolve_transport([])[0] == "stdio"


def test_http_flag_selects_streamable_http():
    from mealplanner.server import _resolve_transport

    transport, host, port = _resolve_transport(["--http", "--port", "8765"])
    assert transport == "streamable-http"
    assert host == "127.0.0.1"
    assert port == 8765


def test_http_env_var_selects_streamable_http(monkeypatch):
    from mealplanner.server import _resolve_transport

    monkeypatch.setenv("MEAL_PLANNER_HTTP", "1")
    assert _resolve_transport([])[0] == "streamable-http"
