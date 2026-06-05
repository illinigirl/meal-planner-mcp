"""Tests for library search + the planner's scoring primitives (overlap and
avoid-repeats)."""

from datetime import date

from mealplanner.core import (
    is_main_course,
    overlap_score,
    recent_recipe_ids,
    recipe_index,
    search_recipes,
    shopping_ingredients,
)
from mealplanner.models import HistoryEntry, Recipe


class TestIsMainCourse:
    def test_dinner_is_main(self):
        assert is_main_course(Recipe(id="x", title="X", servings=4, ingredients=[], course="Dinner"))

    def test_sauce_is_not_main(self):
        assert not is_main_course(Recipe(id="x", title="X", servings=1, ingredients=[], course="Sauces"))

    def test_unknown_course_defaults_to_main(self):
        # Source-independent: a recipe with no course (e.g. added conversationally
        # without one) is included rather than silently dropped.
        assert is_main_course(Recipe(id="x", title="X", servings=4, ingredients=[], course=None))


class TestSearch:
    def test_max_time(self, library):
        out = search_recipes(library, max_time=25)
        assert out  # some recipes qualify
        assert all((r.total_time_min or 0) <= 25 for r in out)

    def test_include_tags(self, library):
        out = search_recipes(library, include_tags=["vegetarian"])
        assert out
        assert all("vegetarian" in r.tags for r in out)

    def test_exclude_tags(self, library):
        out = search_recipes(library, exclude_tags=["beef"])
        assert all("beef" not in r.tags for r in out)

    def test_include_ingredient_canonical(self, library):
        # Searching "onions" should match recipes listing "yellow onion".
        out = search_recipes(library, include_ingredients=["garlic"])
        assert any(r.id == "chicken-stir-fry" for r in out)


class TestShoppingIngredients:
    def test_pantry_filtered(self, library):
        idx = recipe_index(library)
        stir = idx["chicken-stir-fry"]
        ings = shopping_ingredients(stir)
        assert "vegetable oil" not in ings   # pantry staple, ignored
        assert "chicken breast" in ings
        assert "yellow onion" in ings


class TestOverlap:
    def test_counts_shared_non_pantry(self, library):
        idx = recipe_index(library)
        stir = idx["chicken-stir-fry"]
        fajitas = idx["chicken-fajitas"]
        # share: chicken breast, bell pepper, yellow onion, garlic
        assert overlap_score(fajitas, [stir]) == 4

    def test_zero_for_first_pick(self, library):
        idx = recipe_index(library)
        assert overlap_score(idx["greek-salad"], []) == 0


class TestRecentIds:
    def test_within_window(self):
        history = [
            HistoryEntry(recipe_id="beef-tacos", date="2026-06-01"),
            HistoryEntry(recipe_id="old-one", date="2026-05-01"),
        ]
        recent = recent_recipe_ids(history, since_days=14, today=date(2026, 6, 4))
        assert "beef-tacos" in recent
        assert "old-one" not in recent

    def test_bad_date_ignored(self):
        history = [HistoryEntry(recipe_id="x", date="not-a-date")]
        recent = recent_recipe_ids(history, since_days=14, today=date(2026, 6, 4))
        assert recent == set()
