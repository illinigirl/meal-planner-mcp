# CLAUDE.md — Meal Planner guidance

Read this first. It's the contract for working in this repo with an agent:
what the pieces are, how to run and test, the design decisions and why they
were made, and the deliberate simplifications (each one a good place to extend).

## What this is

A **self-contained MCP server** that plans a week of meals from a local recipe
library. It optimizes for **ingredient overlap** (buy shared things once),
reuses **serving-surplus leftovers** (a big-batch cook covers extra nights),
and **avoids recently-cooked recipes** — then produces a consolidated shopping
list and a Markdown plan doc.

Single-user by design. No auth, no cloud, no external API. It clones and runs
with zero credentials — the bundled `data/recipes.seed.json` is enough to plan
a week immediately.

## Why this is an MCP and not just a prompt

The honest test for whether a tool earns its place: **does it give the model
something it can't do alone?** There are four such things, and this hits all
four — which is the whole justification for the project:

| Need | Plain Claude | This MCP |
|---|---|---|
| Suggest a generic meal | ✅ fine | (a tool would add nothing) |
| Plan around *your* recipe library | ❌ doesn't know it | ✅ grounded in local data (#3 private data) |
| Remember what you ate, avoid repeats | ❌ no cross-session memory | ✅ `state.json` history (#1 persistence) |
| Produce a plan + list that persists | ❌ can't write files | ✅ Markdown export (#2 side effects) |
| Merge/scale ingredients exactly | ❌ hand-waves arithmetic | ✅ deterministic `aggregate` (#4 exact compute) |

When changing or adding a tool, ask which of the four it serves. If the answer
is "none — Claude already does this well," it probably shouldn't be a tool.

## Architecture: pure core + thin adapters

The logic is pure and I/O-free, so it's all unit-tested without a runtime. Two
adapters (MCP server, CLI) wire the same functions to the outside world; one
module (`store.py`) is the *only* thing that touches the filesystem.

| Module | Role | Touches I/O? |
|---|---|---|
| `models.py` | dataclasses: `Recipe`, `Ingredient`, `HistoryEntry`, `PlanDay` | no |
| `ingredients.py` | parse free text → `{qty,unit,item}`, canonicalize, `aggregate` | no |
| `core.py` | library search, overlap scoring, avoid-repeats set | no |
| `planner.py` | greedy week optimizer (overlap + leftovers + avoid-repeats) | no |
| `exports.py` | shopping-list build + Markdown render | no |
| `store.py` | JSON persistence + Plan to Eat CSV import | **yes** |
| `server.py` | MCP adapter (FastMCP) | via store |
| `cli.py` | CLI adapter | via store |

Keep new logic in the pure modules and test it directly; let the adapters stay
thin. This is the same split Magic Monitor uses to share one impl across two
transports.

## Run + test

```bash
# Tests — pure core, run on the standard library alone (no install needed):
python -m pytest -q                 # 37 tests

# CLI — also stdlib-only; demos the whole flow without an MCP client:
PYTHONPATH=src python -m mealplanner.cli list --max-time 30
PYTHONPATH=src python -m mealplanner.cli plan --days 7 --household 4
PYTHONPATH=src python -m mealplanner.cli shopping
PYTHONPATH=src python -m mealplanner.cli export

# MCP server — the only thing that needs a dependency:
pip install -r requirements.txt
PYTHONPATH=src python -m mealplanner.server
```

Mutable state lives in `MEAL_PLANNER_DATA_DIR` (default `~/.meal-planner/`),
not the repo. Set it to a temp dir to experiment without touching your real
data: `export MEAL_PLANNER_DATA_DIR=/tmp/mp`.

## Seeding the library

Three paths, deliberately not tied to any one app or format:
- **Bundled seed** (`data/recipes.seed.json`) — ships read-only so the repo
  runs cold.
- **`add_recipe`** — the everyday path. Free-text ingredient lines are run
  through `parse_ingredient`; Claude fills the fields from a pasted/described
  recipe. This is what a normal user uses; no file or format involved.
- **`import_plantoeat_csv`** — an *optional* bulk shortcut for an existing Plan
  to Eat export. It is one importer, not the project's identity; other formats
  (Paprika, Mealie, JSON) are a documented seam (`store.import_*`).

## Design decisions

- **Greedy planner, not optimal (`planner.py`).** Each step picks the recipe
  that shares the most non-pantry ingredients with what's already chosen,
  skipping recently-cooked ones, tie-broken toward quicker recipes. Greedy is
  explainable and fast; an optimal week (ILP) is the documented upgrade and is
  overkill at household scale.
- **Overlap vs. variety is an explicit, tunable tradeoff.** The base objective —
  maximize ingredient overlap — *rewards similar recipes*, so it naturally
  clusters same-protein nights. That's not a bug; repeating proteins is fine by
  default. `diversity_weight` (0 = off, the default) subtracts a penalty for
  repeating a protein already in the week, letting the caller dial waste vs.
  variety. Two opposing objectives, made explicit and tunable rather than hidden.
- **Server-side I/O degrades gracefully for remote callers.** `export_plan`
  returns the rendered Markdown inline (not just a path) and defaults to a known
  data-dir location, not the process cwd — so a caller who can't read the
  server's disk still gets the content. `import_recipes` accepts pasted
  `csv_content`, not only a server-side `csv_path`. The split matters once
  someone *runs* the server remotely rather than just reading the repo.
- **Deterministic math in the data plane; the LLM narrates.** Ingredient
  merging, serving-scaling, and overlap counting are exact functions, never
  left to the model. The model's job is selection and conversation.
- **Leftovers, mode A (serving-surplus).** A cook yielding more servings than
  the household eats covers extra nights (`nights_covered`). **Mode B**
  (cook-once-eat-twice via `produces`/`uses` recipe tags — roast chicken →
  chicken soup) is the next increment; the seed already carries
  `roast-chicken` + a `cooked chicken` soup waiting for it.
- **Storage: bundled seed vs. mutable state, kept apart.** `recipes.seed.json`
  ships read-only so the repo runs cold; your history/plans/imported recipes go
  in a gitignored `state.json` in a user dir. Personal recipe data never lands
  in a public commit.
- **Dual transport from one codebase.** `main()` defaults to stdio (Claude
  Desktop launches it as a subprocess); `--http` / `MEAL_PLANNER_HTTP=1` serves
  streamable-HTTP so the same server can be a remote custom connector. Transport
  selection (`_resolve_transport`) is factored out so it's testable without
  binding a port. Mirrors Magic Monitor's stdio + HTTPS dual transport.
- **Conversational iteration is first-class.** `plan_week` makes the week;
  `swap_meal` / `remove_meal` are literal per-day overrides for "put tacos on
  Tuesday / skip Thursday." The rule that keeps edits predictable: only
  `plan_week` auto-manages leftovers; manual edits touch just the named day.
  "Make Friday quicker" composes existing tools (`suggest_recipes` → `swap_meal`)
  rather than adding a bespoke one.
- **Main-course filter is course-based, source-independent — not title
  matching.** `course` is our normalized field; every ingest path fills it (Plan
  to Eat import maps it; `add_recipe` takes it from the LLM, which knows a sauce
  from a main; `set_course` curates). Unknown course → treated as a main, so a
  real dinner is never silently dropped. Title keyword-matching is deliberately
  avoided — it misclassifies "Noodles with Sesame Sauce."

## Conventions

- **Tool names are planning-flavored** (`plan_week`, `suggest_recipes`,
  `generate_shopping_list`) so they don't collide with a storage-style recipes
  MCP you might also have connected. See below.
- **No silent unit conversion.** Same item in different units stays on separate
  shopping lines — we never turn 3 tsp into 1 tbsp behind your back.
- **Canonicalization preserves distinctions that matter.** "Chopped yellow
  onions" merges with "yellow onion", but red onion ≠ yellow onion (different
  purchases).

## Deliberate simplifications (each a good first task)

These are honest limitations, not omissions — and they're the natural places to
extend (good tasks if you're driving this repo with an agent):

1. **Ingredient parser is heuristic** (`ingredients.parse_ingredient`). Handles
   counts, fractions, unicode fractions, ranges, units, parentheticals. Doesn't
   handle "a pinch", "1 (14 oz) can", or multi-unit lines. Improve it.
2. **No unit conversion.** Add a small, *explicit* conversion table (and decide
   when to apply it) — but never convert silently.
3. **Singularization is a rule table**, not a stemmer (`_SINGULAR`). Extend it
   or swap in `inflect`.
4. **Pantry-staples list is hardcoded** (`core.PANTRY_STAPLES`). Make it
   per-user / configurable.
5. **Greedy planner.** Add leftover mode B (produces/uses chains), or an
   optimal ILP planner, behind the same `plan_week` signature.
6. **CSV import is Plan to Eat-shaped.** Add Paprika / Mealie / JSON importers
   behind `store.import_*`.

## Running alongside another recipe MCP

If you also connect a storage-style recipes server (recipe CRUD, grocery
integration, calendar scheduling), nothing breaks — separate processes, separate
state. The only risk is Claude routing a request to the wrong one. Mitigated
here by **distinct, planning-flavored tool names** and clear tool descriptions
so the lanes are obvious (this server = *planning/optimization*; a storage
server = *save/schedule/shop*).
