"""The week planner — a greedy optimizer over the library.

Greedy, not optimal, on purpose: it's explainable ("at each step pick the recipe
that shares the most ingredients with what's already chosen, skipping anything
cooked recently"), testable, and fast. An optimal solver (ILP over the whole
week) is the documented upgrade seam — overkill at household scale.

Leftovers (mode A — serving-surplus): a cook that yields more servings than the
household eats in a night covers extra days automatically, so the week needs
fewer cooks. Mode B (cook-once-eat-twice chains via produces/uses tags) is the
next increment — the seed already carries `roast-chicken` + a `cooked chicken`
soup waiting for it.
"""

from __future__ import annotations

from datetime import date, timedelta

from .core import (
    is_main_course,
    overlap_score,
    recent_recipe_ids,
    recipe_proteins,
    search_recipes,
)
from .models import HistoryEntry, PlanDay, Recipe


def nights_covered(recipe: Recipe, household_size: int) -> int:
    """How many dinners one cook of this recipe covers via serving surplus.
    Conservative integer division (8 servings / 4 people = 2 nights; 6/4 = 1)."""
    if household_size <= 0:
        return 1
    return max(1, recipe.servings // household_size)


def plan_week(
    library: list[Recipe],
    *,
    days: int,
    start_date: date,
    household_size: int = 4,
    history: list[HistoryEntry] | None = None,
    avoid_recent_days: int = 14,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    max_time: int | None = None,
    main_course_only: bool = True,
    diversity_weight: float = 0.0,
) -> list[PlanDay]:
    """Produce a `days`-long plan, greedily maximizing ingredient overlap while
    skipping recently-cooked recipes and filling extra days with leftovers.

    `main_course_only` (default True) keeps sauces/sides/desserts out of the
    dinner slots — see core.is_main_course (course-based, source-independent;
    unknown course counts as a main).

    `diversity_weight` (default 0.0 = off) trades waste for variety. The base
    objective — maximize ingredient overlap — *rewards similar recipes*, so it
    naturally clusters same-protein nights (overlap and variety are opposing
    objectives). A weight > 0 subtracts a penalty for repeating a protein already
    in the week, letting you dial the balance. At 0.0 behavior is pure overlap
    (the intentional default: repeating proteins is fine).

    Returns a PlanDay per calendar day: cook days carry `recipe_id` + `servings`;
    leftover days carry `recipe_id` + `leftover_of` (the cook date they reuse).
    """
    history = history or []
    recent = recent_recipe_ids(history, since_days=avoid_recent_days, today=start_date)

    def eligible(r: Recipe) -> bool:
        return not main_course_only or is_main_course(r)

    candidates = search_recipes(
        library, max_time=max_time, include_tags=include_tags, exclude_tags=exclude_tags
    )
    candidates = [r for r in candidates if r.id not in recent and eligible(r)]

    chosen_cooks: list[Recipe] = []
    used_ids: set[str] = set()
    plan: list[PlanDay] = []
    cursor = 0

    while cursor < days:
        pool = [r for r in candidates if r.id not in used_ids]
        if not pool:
            # Ran out of fresh candidates — relax the avoid-recent/constraint
            # filters rather than leave days empty (still honoring the main-course
            # gate). Honest fallback: log-worthy in a real deployment.
            pool = [r for r in library if r.id not in used_ids and eligible(r)]
            if not pool:
                break
        # Greedy pick: ingredient overlap with what's chosen, minus an optional
        # protein-repetition penalty, tie-broken toward quicker recipes for a
        # tidy, deterministic result.
        chosen_proteins: set[str] = set()
        if diversity_weight:
            for c in chosen_cooks:
                chosen_proteins |= recipe_proteins(c)

        # Bind chosen_proteins as a default so the closure captures this
        # iteration's value (score is consumed immediately below).
        def score(r: Recipe, _cp: set[str] = chosen_proteins):
            combined = overlap_score(r, chosen_cooks)
            if diversity_weight:
                combined -= diversity_weight * len(recipe_proteins(r) & _cp)
            return (combined, -(r.total_time_min or 0))

        pick = max(pool, key=score)
        used_ids.add(pick.id)
        chosen_cooks.append(pick)

        cover = min(nights_covered(pick, household_size), days - cursor)
        cook_date = start_date + timedelta(days=cursor)
        plan.append(PlanDay(date=cook_date.isoformat(), recipe_id=pick.id, servings=pick.servings))
        for k in range(1, cover):
            d = start_date + timedelta(days=cursor + k)
            plan.append(PlanDay(date=d.isoformat(), recipe_id=pick.id, leftover_of=cook_date.isoformat()))
        cursor += cover

    return plan


def cook_days(plan: list[PlanDay]) -> list[PlanDay]:
    """The days you actually cook (not leftover nights) — what the shopping list
    is built from, since one cook buys for all its servings."""
    return [d for d in plan if d.recipe_id and not d.leftover_of]
