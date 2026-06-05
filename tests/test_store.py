"""Tests for persistence + seeding paths (add one recipe, bulk CSV import,
history). State is redirected to a tmp dir so these never touch ~/.meal-planner."""

import pytest

from mealplanner import store
from mealplanner.models import Ingredient, PlanDay, Recipe


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MEAL_PLANNER_DATA_DIR", str(tmp_path))
    return tmp_path


def test_add_custom_recipe_shows_in_library(tmp_state):
    store.add_custom_recipe(
        Recipe(id="grandmas-chili", title="Grandma's Chili", servings=6,
               ingredients=[Ingredient(item="ground beef", qty=2, unit="pound")])
    )
    assert any(r.id == "grandmas-chili" for r in store.load_library())


def test_unique_id_avoids_seed_collision(tmp_state):
    # "Beef Tacos" is already in the bundled seed.
    assert store.unique_id("Beef Tacos") == "beef-tacos-2"


def test_record_cooked_persists_history(tmp_state):
    store.record_cooked("beef-tacos", "2026-06-04")
    hist = store.history_entries()
    assert hist and hist[0].recipe_id == "beef-tacos"


def test_csv_import_is_one_of_several_paths(tmp_state, tmp_path):
    csv_path = tmp_path / "export.csv"
    csv_path.write_text(
        "Title,Ingredients,Servings,Total Time,Tags,Cuisine,Course\n"
        'My Soup,"1 cup broth\n2 cloves garlic",4,20,soup,American,Dinner\n'
    )
    added = store.import_plantoeat_csv(str(csv_path))
    assert added == 1
    assert any(r.id == "my-soup" for r in store.load_library())


def test_set_course_updates_custom_recipe(tmp_state):
    store.add_custom_recipe(
        Recipe(id="mystery-jus", title="Mystery Jus", servings=1, ingredients=[], course=None)
    )
    assert store.set_recipe_course("mystery-jus", "Sauce") is True
    r = next(r for r in store.load_library() if r.id == "mystery-jus")
    assert r.course == "Sauce"


def test_set_course_on_seed_returns_false(tmp_state):
    # Seed recipes are read-only; only custom/imported are editable.
    assert store.set_recipe_course("beef-tacos", "Side") is False


def test_swap_meal_overrides_day(tmp_state):
    store.save_plan([
        PlanDay(date="2026-06-08", recipe_id="beef-tacos", servings=4),
        PlanDay(date="2026-06-09", recipe_id="greek-salad", servings=4),
    ])
    plan = store.swap_meal("2026-06-09", "chicken-stir-fry", 4)
    by_date = {d.date: d for d in plan}
    assert by_date["2026-06-09"].recipe_id == "chicken-stir-fry"
    assert by_date["2026-06-09"].leftover_of is None


def test_swap_meal_appends_missing_day(tmp_state):
    store.save_plan([PlanDay(date="2026-06-08", recipe_id="beef-tacos", servings=4)])
    plan = store.swap_meal("2026-06-10", "fried-rice", 4)
    assert any(d.date == "2026-06-10" and d.recipe_id == "fried-rice" for d in plan)


def test_remove_meal_clears_day(tmp_state):
    store.save_plan([PlanDay(date="2026-06-08", recipe_id="beef-tacos", servings=4)])
    plan = store.remove_meal("2026-06-08")
    assert plan[0].recipe_id is None
