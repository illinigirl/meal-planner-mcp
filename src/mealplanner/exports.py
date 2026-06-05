"""Turn a plan into the two artifacts that justify side-effects (#2): a
consolidated shopping list and a Markdown meal-plan doc.

The shopping list is built only from *cook* days — a cook buys ingredients for
all its servings, so leftover nights add nothing to the list. That's the
ingredient-sharing + leftover-reuse payoff made concrete: fewer cooks + merged
ingredients = a shorter list.
"""

from __future__ import annotations

from .ingredients import aggregate
from .models import Ingredient, PlanDay, Recipe
from .planner import cook_days


def build_shopping_list(plan: list[PlanDay], recipe_idx: dict[str, Recipe]) -> list[Ingredient]:
    """Consolidated, deduped, scaled shopping list for the plan's cook days."""
    items: list[tuple[Ingredient, float]] = []
    for day in cook_days(plan):
        recipe = recipe_idx.get(day.recipe_id)
        if not recipe:
            continue
        # scale 1.0: cook the recipe as written (its surplus IS the leftovers).
        for ing in recipe.ingredients:
            items.append((ing, 1.0))
    return aggregate(items)


def _fmt_qty(q: float | None) -> str:
    if q is None:
        return ""
    return str(int(q)) if float(q).is_integer() else f"{q:g}"


def _fmt_ingredient(ing: Ingredient) -> str:
    parts = [p for p in (_fmt_qty(ing.qty), ing.unit, ing.item) if p]
    return " ".join(parts)


def render_plan_markdown(
    plan: list[PlanDay], recipe_idx: dict[str, Recipe], *, title: str = "Meal Plan"
) -> str:
    """The fridge-ready doc: the week, then the shopping list."""
    lines = [f"# {title}", ""]
    lines.append("## The week")
    lines.append("")
    lines.append("| Date | Meal | Notes |")
    lines.append("|---|---|---|")
    for day in plan:
        recipe = recipe_idx.get(day.recipe_id) if day.recipe_id else None
        name = recipe.title if recipe else "(unplanned)"
        if day.leftover_of:
            note = f"leftovers from {day.leftover_of}"
        elif recipe:
            note = f"cook · serves {recipe.servings}"
            if recipe.total_time_min:
                note += f" · {recipe.total_time_min} min"
        else:
            note = ""
        lines.append(f"| {day.date} | {name} | {note} |")

    shopping = build_shopping_list(plan, recipe_idx)
    lines += ["", "## Shopping list", ""]
    for ing in sorted(shopping, key=lambda i: i.item):
        lines.append(f"- [ ] {_fmt_ingredient(ing)}")
    lines.append("")
    return "\n".join(lines)
