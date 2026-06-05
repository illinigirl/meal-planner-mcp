"""Integration tests for the MCP tool layer — the surface a reviewer actually
drives. The pure logic is covered elsewhere; this pins the *tool contract*:
the happy-path round-trip, that edits flow through to export, error paths, and
graceful behavior at the edges. Tools are called in-process (they're plain
functions) against a sandboxed data dir, so no transport/runtime is needed.
"""

import pytest

pytest.importorskip("mcp")  # tool layer needs the MCP SDK; pure-core tests don't


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("MEAL_PLANNER_DATA_DIR", str(tmp_path))
    import mealplanner.server as server
    return server


def test_full_round_trip(srv):
    plan = srv.plan_week(days=7, start_date="2026-06-08", max_time=30)
    assert len(plan["days"]) == 7

    assert srv.get_current_plan()["found"] is True

    sw = srv.swap_meal(date="2026-06-10", recipe_id="lemon-herb-salmon")
    assert sw["updated"] is True
    assert any(d["date"] == "2026-06-10" and d["recipe_id"] == "lemon-herb-salmon"
               for d in sw["days"])

    rm = srv.remove_meal(date="2026-06-11")
    assert any(d["date"] == "2026-06-11" and d["recipe_id"] is None for d in rm["days"])

    assert srv.generate_shopping_list()["items"]

    exp = srv.export_plan()
    # export reflects every edit: start date, the swap, and the removed day
    assert "week of 2026-06-08" in exp["content"]
    assert "Lemon-Herb Salmon" in exp["content"]
    assert "2026-06-11" in exp["content"] and "unplanned" in exp["content"]


def test_export_honors_max_time(srv):
    srv.plan_week(days=7, start_date="2026-06-08", max_time=30)
    content = srv.export_plan()["content"]
    assert "40 min" not in content and "45 min" not in content


def test_text_format_is_plain(srv):
    srv.plan_week(days=5, start_date="2026-06-08")
    exp = srv.export_plan(format="text")
    assert exp["format"] == "text"
    assert "|" not in exp["content"] and "#" not in exp["content"]


def test_error_paths(srv):
    assert "error" in srv.export_plan()              # no current plan yet
    assert "error" in srv.generate_shopping_list()   # no current plan yet
    srv.plan_week(days=3, start_date="2026-06-08")
    assert "error" in srv.swap_meal(date="2026-06-08", recipe_id="does-not-exist")
    assert "error" in srv.import_recipes()           # neither path nor content
    assert "error" in srv.get_recipe("does-not-exist")


def test_add_recipe_and_set_course(srv):
    res = srv.add_recipe(title="Test Grain Bowl",
                         ingredients=["1 cup quinoa", "2 cloves garlic", "salt to taste"],
                         course="Dinner")
    assert res["added"] is True
    rid = res["recipe_id"]
    assert srv.get_recipe(rid)["title"] == "Test Grain Bowl"
    assert srv.set_course(rid, "Side")["updated"] is True
    # seed recipes are read-only
    assert srv.set_course("beef-tacos", "Side")["updated"] is False


def test_record_cooked_then_avoided(srv):
    srv.record_cooked("beef-tacos", "2026-06-07")
    plan = srv.plan_week(days=5, start_date="2026-06-08", avoid_recent_days=14)
    assert "beef-tacos" not in [d["recipe_id"] for d in plan["days"]]


def test_import_content_then_retrievable(srv):
    csv = ("Title,Ingredients,Servings,Total Time,Tags,Course\n"
           'Test Soup,"1 cup broth\n2 cloves garlic",4,20,soup,Dinner\n')
    assert srv.import_recipes(csv_content=csv)["imported"] == 1
    assert srv.get_recipe("test-soup")["title"] == "Test Soup"


def test_planner_truncates_gracefully_when_library_too_small(srv):
    # More days than the library can fill without repeating → returns what it
    # can (won't repeat a recipe within a plan), no crash, every day valid.
    plan = srv.plan_week(days=40, start_date="2026-06-08")
    assert 0 < len(plan["days"]) <= 40
    assert all(d["recipe"] is not None for d in plan["days"])
