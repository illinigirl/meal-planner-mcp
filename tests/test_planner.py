"""Tests for the week planner, leftover behavior, shopping-list build, and the
Plan to Eat CSV parser."""

from datetime import date

from mealplanner.core import recipe_index, recipe_proteins
from mealplanner.exports import build_shopping_list, render_plan_markdown
from mealplanner.models import HistoryEntry, Ingredient, Recipe
from mealplanner.planner import cook_days, nights_covered, plan_week
from mealplanner.store import parse_plantoeat_rows


def _r(rid, servings, time, ings, tags=None):
    return Recipe(id=rid, title=rid, servings=servings, total_time_min=time,
                  ingredients=[Ingredient(item=i) for i in ings], tags=tags or [])


class TestNightsCovered:
    def test_surplus_covers_multiple_nights(self):
        assert nights_covered(_r("chili", 8, 60, []), household_size=4) == 2

    def test_no_surplus_is_one_night(self):
        assert nights_covered(_r("pasta", 4, 30, []), household_size=4) == 1

    def test_partial_surplus_rounds_down(self):
        assert nights_covered(_r("roast", 6, 90, []), household_size=4) == 1


class TestPlanWeek:
    def test_fills_exact_days(self, library):
        plan = plan_week(library, days=7, start_date=date(2026, 6, 8))
        assert len(plan) == 7
        for d in plan:
            assert (d.recipe_id and not d.leftover_of) or d.leftover_of  # cook or leftover

    def test_serving_surplus_creates_leftover_day(self):
        # Big recipe (serves 8, fastest) gets picked first; its surplus fills day 2.
        lib = [
            _r("big", 8, 10, ["beef", "onion", "garlic"]),
            _r("a", 4, 30, ["chicken", "rice"]),
            _r("b", 4, 30, ["fish", "lemon"]),
        ]
        plan = plan_week(lib, days=3, start_date=date(2026, 6, 8), household_size=4)
        assert plan[0].recipe_id == "big" and plan[0].leftover_of is None
        assert plan[1].leftover_of == plan[0].date  # day 2 = leftovers of the cook

    def test_avoids_recently_cooked(self, library):
        history = [HistoryEntry(recipe_id="beef-tacos", date="2026-06-06")]
        plan = plan_week(library, days=5, start_date=date(2026, 6, 8),
                         history=history, avoid_recent_days=14)
        assert "beef-tacos" not in {d.recipe_id for d in cook_days(plan)}

    def test_respects_tag_filter(self, library):
        plan = plan_week(library, days=4, start_date=date(2026, 6, 8),
                         include_tags=["vegetarian"])
        idx = recipe_index(library)
        for d in cook_days(plan):
            assert "vegetarian" in idx[d.recipe_id].tags

    NON_MAINS = {"greek-salad", "quick-marinara", "chocolate-chip-cookies"}

    def test_main_course_only_excludes_sides_sauces_desserts(self, library):
        # Seed has a Side, a Sauce, and a Dessert — none should be cooked as a
        # dinner when main_course_only is on (the default).
        plan = plan_week(library, days=7, start_date=date(2026, 6, 8), main_course_only=True)
        cooked = {d.recipe_id for d in cook_days(plan)}
        assert not (cooked & self.NON_MAINS)

    def test_main_course_only_off_allows_them(self, library):
        # With the gate off, the non-main recipes become eligible again.
        plan = plan_week(library, days=14, start_date=date(2026, 6, 8), main_course_only=False)
        cooked = {d.recipe_id for d in cook_days(plan)}
        assert cooked & self.NON_MAINS


class TestDiversity:
    # Two chicken mains + two beef mains, all sharing onion/garlic so overlap is
    # comparable — isolates the protein-diversity knob.
    LIB = [
        _r("chick-a", 4, 30, ["chicken breast", "onion", "garlic", "rice"]),
        _r("chick-b", 4, 30, ["chicken breast", "onion", "garlic", "bell pepper"]),
        _r("beef-a", 4, 30, ["ground beef", "onion", "garlic", "rice"]),
        _r("beef-b", 4, 30, ["ground beef", "onion", "garlic", "bell pepper"]),
    ]

    def _cook_proteins(self, plan):
        idx = recipe_index(self.LIB)
        return [recipe_proteins(idx[d.recipe_id]) for d in cook_days(plan)]

    def test_weight_zero_clusters_same_protein(self):
        # Pure overlap (the default) rewards similar recipes → chicken back-to-back.
        plan = plan_week(self.LIB, days=4, start_date=date(2026, 6, 8),
                         household_size=4, diversity_weight=0.0, main_course_only=False)
        proteins = self._cook_proteins(plan)
        assert proteins[0] & proteins[1]   # first two cooks share a protein

    def test_high_weight_avoids_adjacent_repeats(self):
        # Turning the knob up trades waste for variety: no two consecutive cooks
        # share a protein.
        plan = plan_week(self.LIB, days=4, start_date=date(2026, 6, 8),
                         household_size=4, diversity_weight=5.0, main_course_only=False)
        proteins = self._cook_proteins(plan)
        for a, b in zip(proteins, proteins[1:]):
            assert not (a & b)


class TestShoppingList:
    def test_excludes_leftover_days(self):
        lib = [_r("big", 8, 10, ["beef", "onion", "garlic"]),
               _r("a", 4, 30, ["chicken", "rice"])]
        plan = plan_week(lib, days=3, start_date=date(2026, 6, 8), household_size=4)
        # 3 days, but the serves-8 cook covers 2 → fewer cooks than days.
        assert len(cook_days(plan)) < len(plan)
        shopping = build_shopping_list(plan, recipe_index(lib))
        items = {i.item for i in shopping}
        assert "beef" in items  # from the one cook, counted once

    def test_markdown_has_week_and_shopping(self, library):
        plan = plan_week(library, days=5, start_date=date(2026, 6, 8))
        md = render_plan_markdown(plan, recipe_index(library), title="Test Week")
        assert "# Test Week" in md
        assert "## The week" in md
        assert "## Shopping list" in md


class TestPlanToEatParse:
    def test_parses_free_text_ingredients(self):
        rows = [{
            "Title": "Easy Blender Hollandaise",
            "Cuisine": "French",
            "Course": "Sauces",
            "Servings": "Makes about 4-6 servings",
            "Total Time": "10.0",
            "Tags": "sauce, brunch",
            "Ingredients": "3 egg yolks\n1/2 cup butter\nsalt to taste",
        }]
        recipes = parse_plantoeat_rows(rows)
        assert len(recipes) == 1
        r = recipes[0]
        assert r.id == "easy-blender-hollandaise"
        assert r.servings == 4  # first number found
        assert r.total_time_min == 10
        assert r.tags == ["sauce", "brunch"]
        assert len(r.ingredients) == 3
        butter = next(i for i in r.ingredients if "butter" in i.item)
        assert butter.qty == 0.5 and butter.unit == "cup"
