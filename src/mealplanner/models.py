"""Domain models for the meal planner.

Plain dataclasses, no I/O. Everything the planner reasons over is here, so the
whole `core` layer can be tested without an MCP runtime, a network, or a file.

Single-user by design (no auth, no per-eater model). The two mutable things —
meal `history` and the current `plan` — live in a state file (see store.py);
the recipe library is read-mostly (bundled seed + imported/added recipes).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ingredient:
    """One ingredient line.

    `item` is the human name ("yellow onion"); `qty`/`unit` are the structured
    amount when we could parse one ("2", "cup"). `qty` is None for unmeasured
    lines ("salt to taste"). `raw` preserves the original text for display and
    for debugging the parser.
    """

    item: str
    qty: float | None = None
    unit: str | None = None
    raw: str | None = None


@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    servings: int
    ingredients: list[Ingredient]
    tags: list[str] = field(default_factory=list)
    cuisine: str | None = None
    course: str | None = None
    total_time_min: int | None = None
    directions: str | None = None
    source: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Recipe":
        return cls(
            id=d["id"],
            title=d["title"],
            servings=int(d.get("servings") or 1),
            ingredients=[
                ing if isinstance(ing, Ingredient) else Ingredient(
                    item=ing["item"], qty=ing.get("qty"), unit=ing.get("unit"),
                    raw=ing.get("raw"),
                )
                for ing in d.get("ingredients", [])
            ],
            tags=list(d.get("tags", [])),
            cuisine=d.get("cuisine"),
            course=d.get("course"),
            total_time_min=d.get("total_time_min"),
            directions=d.get("directions"),
            source=d.get("source"),
        )


@dataclass(frozen=True)
class HistoryEntry:
    """A recipe that was actually cooked on a date (YYYY-MM-DD). This file-backed
    list is what lets the planner avoid repeats across sessions — the thing plain
    Claude can't remember."""

    recipe_id: str
    date: str


@dataclass(frozen=True)
class PlanDay:
    """One day of a plan. `leftover_of` is set when this day is covered by an
    earlier day's surplus servings rather than its own cook (serving-surplus
    leftovers)."""

    date: str
    recipe_id: str | None = None
    servings: int | None = None
    leftover_of: str | None = None  # date of the cook this reuses, if any
