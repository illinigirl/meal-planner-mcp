"""Persistence + CSV import — the only module that touches the filesystem.

Two locations, deliberately separate (the getParkRides-style "keep mutable and
bundled apart" discipline):
- The **bundled seed** (`data/recipes.seed.json`) ships in the repo, read-only —
  so the project clones-and-runs with zero setup.
- **Mutable state** (`state.json`: history, current plan, your imported/added
  recipes) lives in a user data dir (MEAL_PLANNER_DATA_DIR, default
  ~/.meal-planner) and is gitignored — a reviewer's experiments never dirty the
  repo, and your real recipe library never lands in a public commit.
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

from .ingredients import parse_ingredient
from .models import HistoryEntry, PlanDay, Recipe

_PKG_ROOT = Path(__file__).resolve().parents[2]  # repo root when run from a clone


def seed_path() -> Path:
    return Path(os.environ.get("MEAL_PLANNER_SEED", _PKG_ROOT / "data" / "recipes.seed.json"))


def data_dir() -> Path:
    d = Path(os.environ.get("MEAL_PLANNER_DATA_DIR", Path.home() / ".meal-planner"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_path() -> Path:
    return data_dir() / "state.json"


# ── State (mutable) ─────────────────────────────────────────────────

def load_state() -> dict:
    p = state_path()
    if not p.exists():
        return {"history": [], "current_plan": [], "custom_recipes": []}
    return json.loads(p.read_text())


def save_state(state: dict) -> None:
    state_path().write_text(json.dumps(state, indent=2))


# ── Library (bundled seed + your custom recipes) ────────────────────

def load_library() -> list[Recipe]:
    raw = json.loads(seed_path().read_text())
    recipes = [Recipe.from_dict(r) for r in raw.get("recipes", [])]
    state = load_state()
    recipes += [Recipe.from_dict(r) for r in state.get("custom_recipes", [])]
    return recipes


# ── History + plan helpers ──────────────────────────────────────────

def history_entries() -> list[HistoryEntry]:
    return [HistoryEntry(recipe_id=h["recipe_id"], date=h["date"]) for h in load_state().get("history", [])]


def record_cooked(recipe_id: str, on_date: str) -> None:
    state = load_state()
    state.setdefault("history", []).append({"recipe_id": recipe_id, "date": on_date})
    save_state(state)


def save_plan(plan: list[PlanDay]) -> None:
    state = load_state()
    state["current_plan"] = [
        {"date": d.date, "recipe_id": d.recipe_id, "servings": d.servings, "leftover_of": d.leftover_of}
        for d in plan
    ]
    save_state(state)


def load_plan() -> list[PlanDay]:
    return [
        PlanDay(date=d["date"], recipe_id=d.get("recipe_id"), servings=d.get("servings"),
                leftover_of=d.get("leftover_of"))
        for d in load_state().get("current_plan", [])
    ]


# ── Adding recipes (the everyday path: one at a time) ───────────────

def _recipe_to_dict(r: Recipe) -> dict:
    return {
        "id": r.id, "title": r.title, "servings": r.servings,
        "ingredients": [{"item": i.item, "qty": i.qty, "unit": i.unit, "raw": i.raw}
                        for i in r.ingredients],
        "tags": r.tags, "cuisine": r.cuisine, "course": r.course,
        "total_time_min": r.total_time_min, "directions": r.directions, "source": r.source,
    }


def existing_ids() -> set[str]:
    """All recipe ids currently in the library (seed + custom)."""
    return {r.id for r in load_library()}


def unique_id(base: str) -> str:
    """A slug not already taken by a seed or custom recipe."""
    taken = existing_ids()
    rid = _slug(base)
    candidate = rid
    n = 2
    while candidate in taken:
        candidate = f"{rid}-{n}"
        n += 1
    return candidate


def add_custom_recipe(recipe: Recipe) -> None:
    """Append one recipe to the mutable custom library."""
    state = load_state()
    state.setdefault("custom_recipes", []).append(_recipe_to_dict(recipe))
    save_state(state)


def set_recipe_course(recipe_id: str, course: str) -> bool:
    """Curate a recipe's course (e.g. mark an uncategorized import as a sauce so
    the planner stops treating it as a dinner). Only custom recipes are editable;
    seed recipes are read-only. Returns True if updated."""
    state = load_state()
    for r in state.get("custom_recipes", []):
        if r["id"] == recipe_id:
            r["course"] = course
            save_state(state)
            return True
    return False


# ── Plan edits (conversational iteration) ───────────────────────────

def swap_meal(date: str, recipe_id: str, servings: int | None) -> list[PlanDay]:
    """Set one calendar day to a cook of `recipe_id` (a literal override — clears
    any leftover marking on that day). Appends the day if it wasn't in the plan."""
    state = load_state()
    plan = state.get("current_plan", [])
    for d in plan:
        if d["date"] == date:
            d.update(recipe_id=recipe_id, servings=servings, leftover_of=None)
            break
    else:
        plan.append({"date": date, "recipe_id": recipe_id, "servings": servings, "leftover_of": None})
        plan.sort(key=lambda x: x["date"])
    state["current_plan"] = plan
    save_state(state)
    return load_plan()


def remove_meal(date: str) -> list[PlanDay]:
    """Clear one day (eating out, skipping). The date stays in the plan as
    unplanned so the week's shape is preserved."""
    state = load_state()
    for d in state.get("current_plan", []):
        if d["date"] == date:
            d.update(recipe_id=None, servings=None, leftover_of=None)
    save_state(state)
    return load_plan()


# ── CSV import (Plan to Eat export) ─────────────────────────────────

def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "recipe"


def _parse_servings(raw: str) -> int:
    m = re.search(r"\d+", raw or "")
    return int(m.group()) if m else 4


def parse_plantoeat_rows(rows: list[dict]) -> list[Recipe]:
    """Map Plan to Eat CSV rows → Recipe objects. Ingredients are free text
    (newline-separated), so each line goes through the heuristic parser. Pure
    over the parsed rows — unit-testable without touching a file."""
    out: list[Recipe] = []
    seen: set[str] = set()
    for row in rows:
        title = (row.get("Title") or "").strip()
        if not title:
            continue
        rid = _slug(title)
        while rid in seen:
            rid += "-x"
        seen.add(rid)
        ing_lines = [ln.strip() for ln in (row.get("Ingredients") or "").splitlines() if ln.strip()]
        tags = [t.strip() for t in (row.get("Tags") or "").split(",") if t.strip()]
        total = None
        m = re.search(r"\d+", row.get("Total Time") or "")
        if m:
            total = int(float(m.group()))
        out.append(Recipe(
            id=rid,
            title=title,
            servings=_parse_servings(row.get("Servings", "")),
            ingredients=[parse_ingredient(ln) for ln in ing_lines],
            tags=tags,
            cuisine=(row.get("Cuisine") or "").strip() or None,
            course=(row.get("Course") or "").strip() or None,
            total_time_min=total,
            directions=(row.get("Directions") or "").strip() or None,
            source=(row.get("Source") or row.get("Url") or "").strip() or None,
        ))
    return out


def _add_parsed_recipes(recipes: list[Recipe]) -> int:
    """Append recipes to custom_recipes, skipping ids already present. Returns
    the count added. Shared by the path and content importers."""
    state = load_state()
    existing = {r["id"] for r in state.get("custom_recipes", [])}
    added = 0
    for r in recipes:
        if r.id in existing:
            continue
        state.setdefault("custom_recipes", []).append(_recipe_to_dict(r))
        existing.add(r.id)
        added += 1
    save_state(state)
    return added


def import_plantoeat_csv(path: str) -> int:
    """Bulk-import a Plan to Eat CSV by path — LOCAL use (the file is on the
    server's filesystem). For a remote caller, use import_plantoeat_content."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return _add_parsed_recipes(parse_plantoeat_rows(rows))


def import_plantoeat_content(content: str) -> int:
    """Bulk-import from Plan to Eat CSV *text* — works for a remote caller who
    can't reach the server's filesystem (they paste the export's contents)."""
    import io
    rows = list(csv.DictReader(io.StringIO(content)))
    return _add_parsed_recipes(parse_plantoeat_rows(rows))


def export_default_path(first_date: str) -> Path:
    """Where export_plan writes when no path is given: a KNOWN location under the
    data dir (not the server's cwd, which is unpredictable when Claude Desktop
    launches the process). Creates the dir."""
    d = data_dir() / "meal-plans"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{first_date}.md"
