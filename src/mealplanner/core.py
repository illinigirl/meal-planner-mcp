"""Library access, search, and the scoring primitives the planner builds on.

Pure functions over in-memory Recipe lists + the history list. No I/O here
(that's store.py); no MCP runtime (that's server.py). The planner (planner.py)
composes `overlap_score` + `recent_recipe_ids` into a week selection.
"""

from __future__ import annotations

from datetime import date, timedelta

from .ingredients import canonical_item
from .models import HistoryEntry, Recipe

# Always-on-hand staples: sharing these between recipes isn't a real shopping
# win, so they're ignored when scoring ingredient overlap. (Tunable — a nice
# reviewer task is "make the pantry list configurable per user".)
PANTRY_STAPLES = {
    "salt", "pepper", "black pepper", "water", "oil", "olive oil",
    "vegetable oil", "butter", "sugar", "flour", "garlic powder",
    "baking soda", "baking powder",
}


# Courses that aren't a dinner anchor — excluded from planning by default so a
# sauce or side never gets planned as the main meal.
#
# Deliberately NOT keyword-on-title (which misclassifies "Noodles with Sesame
# Sauce" as a sauce). `course` is OUR normalized field, populated by whatever
# ingest path created the recipe: Plan to Eat import maps its Course, add_recipe
# takes one from the LLM (which knows a sauce from a main), set_course fixes
# stragglers. A recipe with NO course is treated as a main — better to include a
# real dinner than silently drop it; curate with set_course if needed.
NON_MAIN_COURSES = {
    "sauce", "sauces", "dessert", "desserts", "side", "side dish", "sides",
    "breakfast", "brunch", "drink", "drinks", "beverage", "beverages",
    "condiment", "condiments", "dressing", "dressings", "snack", "snacks",
    "appetizer", "appetizers",
}


def is_main_course(recipe: Recipe) -> bool:
    """True if a recipe is a plausible dinner anchor (a main, or uncategorized)."""
    return (recipe.course or "").strip().lower() not in NON_MAIN_COURSES


def recipe_index(library: list[Recipe]) -> dict[str, Recipe]:
    return {r.id: r for r in library}


def shopping_ingredients(recipe: Recipe) -> set[str]:
    """Canonical, non-pantry ingredient names for a recipe — the set that
    matters for overlap (i.e. the stuff you'd actually have to buy)."""
    out: set[str] = set()
    for ing in recipe.ingredients:
        c = canonical_item(ing.item)
        if c and c not in PANTRY_STAPLES:
            out.add(c)
    return out


def search_recipes(
    library: list[Recipe],
    *,
    max_time: int | None = None,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    include_ingredients: list[str] | None = None,
) -> list[Recipe]:
    """Filter the library by the common constraints. All filters AND together;
    tag/ingredient matching is canonical + case-insensitive."""
    inc_tags = {t.lower() for t in (include_tags or [])}
    exc_tags = {t.lower() for t in (exclude_tags or [])}
    inc_ings = {canonical_item(i) for i in (include_ingredients or [])}

    out = []
    for r in library:
        if max_time is not None and (r.total_time_min or 0) > max_time:
            continue
        tags = {t.lower() for t in r.tags}
        if inc_tags and not inc_tags <= tags:
            continue
        if exc_tags and (exc_tags & tags):
            continue
        if inc_ings and not inc_ings <= shopping_ingredients(r):
            continue
        out.append(r)
    return out


def recent_recipe_ids(
    history: list[HistoryEntry], *, since_days: int, today: date | None = None
) -> set[str]:
    """Recipe ids cooked within the last `since_days` — the avoid-repeats set.
    This is the cross-session memory (#1) doing real work."""
    today = today or date.today()
    cutoff = today - timedelta(days=since_days)
    out: set[str] = set()
    for h in history:
        try:
            d = date.fromisoformat(h.date)
        except ValueError:
            continue
        if d >= cutoff:
            out.add(h.recipe_id)
    return out


def overlap_score(recipe: Recipe, chosen: list[Recipe]) -> int:
    """How many non-pantry ingredients this recipe shares with already-chosen
    recipes. Higher = more shared shopping = less waste. The planner greedily
    maximizes the running total of this across the week."""
    if not chosen:
        return 0
    mine = shopping_ingredients(recipe)
    theirs: set[str] = set()
    for r in chosen:
        theirs |= shopping_ingredients(r)
    return len(mine & theirs)
