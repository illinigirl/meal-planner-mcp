"""The MCP server — a thin adapter over the pure core.

Design split (same one Magic Monitor uses): all logic lives in core/planner/
exports/ingredients and is unit-tested without a runtime; this file only wires
those to MCP tools + persistence. The CLI (cli.py) is a second adapter over the
exact same functions.

Tool names are deliberately *planning*-flavored (plan_week, suggest_recipes,
generate_shopping_list) so they don't collide with a storage-style recipes
server you might also have connected — see CLAUDE.md 'Running alongside another
recipe MCP'.
"""

from __future__ import annotations

from datetime import date

from mcp.server.fastmcp import FastMCP

from . import core, store
from .exports import build_shopping_list, render_plan_markdown
from .ingredients import aggregate  # noqa: F401  (re-exported for parity/tests)
from .planner import plan_week as _plan_week

mcp = FastMCP("meal-planner")


def _ingredient_dict(ing) -> dict:
    return {"item": ing.item, "qty": ing.qty, "unit": ing.unit}


@mcp.tool()
def list_recipes(tag: str | None = None, max_time: int | None = None) -> dict:
    """List recipes in the library (bundled seed + your imported/added recipes).

    Args:
        tag: optional tag filter (e.g. "vegetarian", "quick").
        max_time: optional max total time in minutes.
    """
    lib = store.load_library()
    out = core.search_recipes(
        lib, max_time=max_time, include_tags=[tag] if tag else None
    )
    return {"count": len(out), "recipes": [
        {"id": r.id, "title": r.title, "servings": r.servings,
         "total_time_min": r.total_time_min, "tags": r.tags} for r in out
    ]}


@mcp.tool()
def get_recipe(recipe_id: str) -> dict:
    """Full detail for one recipe, including its ingredient list."""
    idx = core.recipe_index(store.load_library())
    r = idx.get(recipe_id)
    if not r:
        return {"error": "not found", "recipe_id": recipe_id}
    return {"id": r.id, "title": r.title, "servings": r.servings, "tags": r.tags,
            "cuisine": r.cuisine, "total_time_min": r.total_time_min,
            "ingredients": [_ingredient_dict(i) for i in r.ingredients],
            "directions": r.directions}


@mcp.tool()
def suggest_recipes(max_time: int | None = None, include_tags: list[str] | None = None,
                    exclude_tags: list[str] | None = None,
                    include_ingredients: list[str] | None = None) -> dict:
    """Candidate recipes matching constraints — the grounding step before you
    decide a week. Returns recipes from YOUR library (the thing base Claude
    can't see), filtered by time/tags/ingredients."""
    lib = store.load_library()
    out = core.search_recipes(lib, max_time=max_time, include_tags=include_tags,
                              exclude_tags=exclude_tags, include_ingredients=include_ingredients)
    return {"count": len(out), "recipes": [
        {"id": r.id, "title": r.title, "servings": r.servings,
         "total_time_min": r.total_time_min, "tags": r.tags} for r in out]}


@mcp.tool()
def plan_week(days: int = 7, household_size: int = 4, start_date: str | None = None,
              include_tags: list[str] | None = None, exclude_tags: list[str] | None = None,
              max_time: int | None = None, avoid_recent_days: int = 14,
              main_course_only: bool = True) -> dict:
    """Build and save a meal plan, optimizing ingredient overlap, reusing
    serving-surplus leftovers, and avoiding recently-cooked recipes.

    `main_course_only` (default true) keeps sauces/sides/desserts out of dinner
    slots. Saves as the current plan; tweak it with swap_meal / remove_meal, or
    re-call with new constraints. generate_shopping_list / export_plan use it.
    """
    sd = date.fromisoformat(start_date) if start_date else date.today()
    lib = store.load_library()
    plan = _plan_week(lib, days=days, start_date=sd, household_size=household_size,
                      history=store.history_entries(), avoid_recent_days=avoid_recent_days,
                      include_tags=include_tags, exclude_tags=exclude_tags, max_time=max_time,
                      main_course_only=main_course_only)
    store.save_plan(plan)
    idx = core.recipe_index(lib)
    return {"days": [
        {"date": d.date, "recipe": idx[d.recipe_id].title if d.recipe_id else None,
         "recipe_id": d.recipe_id, "leftover": bool(d.leftover_of)} for d in plan]}


@mcp.tool()
def get_current_plan() -> dict:
    """The currently saved plan, if any."""
    plan = store.load_plan()
    if not plan:
        return {"found": False}
    idx = core.recipe_index(store.load_library())
    return {"found": True, "days": [
        {"date": d.date, "recipe": idx[d.recipe_id].title if d.recipe_id and d.recipe_id in idx else None,
         "leftover": bool(d.leftover_of)} for d in plan]}


@mcp.tool()
def generate_shopping_list() -> dict:
    """Consolidated shopping list for the current plan — ingredients merged and
    scaled across cook days (leftover nights add nothing). Deterministic math,
    not an LLM estimate."""
    plan = store.load_plan()
    if not plan:
        return {"error": "no current plan — call plan_week first"}
    idx = core.recipe_index(store.load_library())
    shopping = build_shopping_list(plan, idx)
    return {"items": [_ingredient_dict(i) for i in sorted(shopping, key=lambda x: x.item)]}


@mcp.tool()
def export_plan(path: str | None = None) -> dict:
    """Write the current plan + shopping list to a Markdown file (the fridge
    copy). Defaults to ./meal-plans/<start-date>.md."""
    plan = store.load_plan()
    if not plan:
        return {"error": "no current plan — call plan_week first"}
    idx = core.recipe_index(store.load_library())
    from pathlib import Path
    out = Path(path) if path else Path("meal-plans") / f"{plan[0].date}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_plan_markdown(plan, idx, title=f"Meal Plan — week of {plan[0].date}"))
    return {"written": str(out)}


@mcp.tool()
def record_cooked(recipe_id: str, on_date: str | None = None) -> dict:
    """Log that you actually cooked a recipe (defaults to today). This is the
    cross-session memory that powers avoid-repeats — what plain Claude can't do."""
    store.record_cooked(recipe_id, on_date or date.today().isoformat())
    return {"recorded": recipe_id, "date": on_date or date.today().isoformat()}


@mcp.tool()
def add_recipe(title: str, ingredients: list[str], servings: int = 4,
               tags: list[str] | None = None, total_time_min: int | None = None,
               cuisine: str | None = None, course: str | None = None,
               directions: str | None = None) -> dict:
    """Save one recipe to your library — the everyday way to seed it.

    No file or special format needed: paste or describe a recipe and let Claude
    fill these fields in. `ingredients` is a list of free-text lines
    ("1 cup flour", "2 cloves garlic", "salt to taste") — each is parsed into a
    structured amount so it can feed the shopping-list math.

    Set `course` ("Dinner", "Sauce", "Side", "Dessert", …) so the planner knows
    whether this is a dinner anchor — you know a sauce from a main; pass it
    along. Omit it and it's treated as a main.
    """
    from .ingredients import parse_ingredient
    from .models import Recipe

    rid = store.unique_id(title)
    parsed = [parse_ingredient(line) for line in ingredients]
    recipe = Recipe(id=rid, title=title, servings=servings, ingredients=parsed,
                    tags=tags or [], total_time_min=total_time_min, cuisine=cuisine,
                    course=course, directions=directions)
    store.add_custom_recipe(recipe)
    return {"added": True, "recipe_id": rid,
            "ingredients_parsed": [{"item": i.item, "qty": i.qty, "unit": i.unit} for i in parsed]}


@mcp.tool()
def set_course(recipe_id: str, course: str) -> dict:
    """Recategorize a recipe's course — curation for imports that came in
    uncategorized (e.g. mark a sauce as "Sauce" so it stops landing in dinner
    slots). Only your own/imported recipes are editable; seed recipes are
    read-only."""
    ok = store.set_recipe_course(recipe_id, course)
    return {"updated": ok, "recipe_id": recipe_id, "course": course} if ok else {
        "updated": False, "recipe_id": recipe_id,
        "note": "not found among editable (custom/imported) recipes"}


@mcp.tool()
def swap_meal(date: str, recipe_id: str) -> dict:
    """Replace one day of the current plan with a specific recipe — "put tacos on
    Tuesday instead." A literal per-day override (clears any leftover marking on
    that day). For "make Friday quicker", call suggest_recipes first, then swap."""
    idx = core.recipe_index(store.load_library())
    r = idx.get(recipe_id)
    if not r:
        return {"error": "recipe not found", "recipe_id": recipe_id}
    plan = store.swap_meal(date, recipe_id, r.servings)
    return {"updated": True, "day": date, "meal": r.title,
            "days": [{"date": d.date, "recipe_id": d.recipe_id, "leftover": bool(d.leftover_of)} for d in plan]}


@mcp.tool()
def remove_meal(date: str) -> dict:
    """Clear one day of the current plan (eating out, skipping). The date stays
    as an unplanned slot."""
    plan = store.remove_meal(date)
    return {"removed": date,
            "days": [{"date": d.date, "recipe_id": d.recipe_id, "leftover": bool(d.leftover_of)} for d in plan]}


@mcp.tool()
def import_recipes(csv_path: str) -> dict:
    """Optional bulk shortcut: import many recipes from a Plan to Eat CSV export.
    Most users seed with add_recipe instead — this is just a convenience for
    people who already have an export to migrate."""
    added = store.import_plantoeat_csv(csv_path)
    return {"imported": added}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
