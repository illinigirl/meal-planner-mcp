# Meal Planner MCP

A self-contained [MCP](https://modelcontextprotocol.io) server that plans a
week of meals from a local recipe library — optimizing for **shared
ingredients**, reusing **leftovers**, and **avoiding recent repeats** — then
generates a consolidated shopping list and a Markdown plan you can stick on the
fridge.

No cloud, no API keys, no database. Clone it and it runs.

```bash
python -m pytest -q                                   # 37 tests, stdlib only
PYTHONPATH=src python -m mealplanner.cli plan --days 7
PYTHONPATH=src python -m mealplanner.cli shopping
```

## Why an MCP (and not just asking Claude)?

A tool only earns its place if it does something the model *can't*. This one
clears that bar on four counts — which is the whole reason it exists:

| Ask | Plain Claude | This server |
|---|---|---|
| "Suggest a sci-fi… er, a pasta dish" | ✅ fine on its own | (a tool adds nothing) |
| "Plan around **my** recipes" | ❌ doesn't know them | ✅ grounded in your local library |
| "Don't repeat what we ate last week" | ❌ no memory across chats | ✅ persistent history file |
| "Give me a plan + list I can keep" | ❌ can't write files | ✅ Markdown export |
| "Merge 1 + 2 + ½ onion across 4 recipes, scaled to 6" | ❌ hand-waves the math | ✅ exact, deterministic |

The model does the *creative* part (which week feels good); the server supplies
the private data, the memory, the persisted artifact, and the exact arithmetic.

## What it does

- **`plan_week`** — greedy optimizer: picks recipes that share the most
  ingredients with what's already chosen, skips anything cooked recently, and
  fills extra nights from serving-surplus leftovers (a batch of chili that
  serves 8 covers two dinners for a family of four).
- **`swap_meal` / `remove_meal`** — iterate per day: *"put tacos on Tuesday,"
  "skip Thursday."* The plan, shopping list, and export all update with you.
  ("Make Friday quicker" needs no new tool — Claude calls `suggest_recipes`
  then `swap_meal`.)
- **`generate_shopping_list`** — merges and scales ingredients across the plan's
  cook days, deduped, with no silent unit conversion.
- **`export_plan`** — writes the week + shopping list to Markdown.
- **`set_course`** — recategorize a recipe (mark a stray import as a `Sauce` so
  it stops landing in dinner slots). Curation; the planner relies on this
  normalized field, never on title guessing.
- **`suggest_recipes` / `list_recipes` / `get_recipe`** — query the library.
- **`record_cooked`** — log what you actually made; this is the memory that
  powers avoid-repeats.
- **`add_recipe`** — save one recipe from free text. The everyday way to build
  your library — no file or format needed.
- **`import_recipes`** — optional bulk shortcut for migrating an existing Plan
  to Eat CSV export (offline, no scraping).

## Seeding your library

Three ways, none requiring any particular app or format:

1. **Just start** — 14 recipes ship in `data/recipes.seed.json`, so it plans a
   week the moment you clone it.
2. **Add as you go (the normal path)** — paste or describe a recipe in chat;
   Claude structures it and calls `add_recipe`. *"Save my chili: 2 lb ground
   beef, an onion, 2 cans tomatoes, kidney beans, chili powder — serves 8."* No
   CSV, no schema.
3. **Bulk migrate (optional)** — already have a Plan to Eat export? `import_recipes`
   loads it in one offline pass. It's a convenience, not a requirement — and
   adding other formats (Paprika, Mealie, plain JSON) is a documented seam.

## Architecture

Pure core + thin adapters. All the logic is I/O-free and unit-tested without a
runtime; the MCP server and the CLI are two adapters over the same functions,
and one module does all the file I/O.

```
src/mealplanner/
  models.py       Recipe · Ingredient · HistoryEntry · PlanDay
  ingredients.py  parse free text → {qty,unit,item} · canonicalize · aggregate   (pure)
  core.py         library search · overlap scoring · avoid-repeats               (pure)
  planner.py      greedy week optimizer (overlap + leftovers + avoid-repeats)    (pure)
  exports.py      shopping-list build · Markdown render                          (pure)
  store.py        JSON persistence · Plan to Eat CSV import          (the only I/O)
  server.py       MCP adapter (FastMCP)
  cli.py          CLI adapter
data/recipes.seed.json   bundled starter library (clones-and-runs)
```

The bundled seed ships in the repo; your mutable state (history, plans,
imported recipes) lives in a gitignored `state.json` under
`~/.meal-planner/` — so your real recipes never land in a commit.

## Use it from Claude

The server runs over **two transports** from one codebase — stdio for a local
Claude Desktop subprocess, or streamable-HTTP so it can be added as a remote
*custom connector* by URL.

**Local (stdio) — Claude Desktop.** After `pip install -e .`, add to your config:

```json
{
  "mcpServers": {
    "meal-planner": {
      "command": "/path/to/meal-planner-mcp/.venv/bin/meal-planner"
    }
  }
}
```

**As a custom connector (HTTP).** Run it as an HTTP server and point a connector
at the URL:

```bash
meal-planner --http --port 8765          # or MEAL_PLANNER_HTTP=1
# then add http://localhost:8765/mcp as a custom connector
```

(For a *remote* connector — claude.ai / mobile — host it behind a public HTTPS
URL with auth, the same way a production MCP deployment would.)

Then just talk: *"Plan us 7 dinners this week, nothing we had recently, keep
weeknights under 30 minutes — then give me the shopping list."* — and iterate:
*"swap Tuesday for something vegetarian," "skip Thursday."*

## For reviewers — drive it with Claude Code

It's built to be worked in by an agent. Good first tasks, easiest first:

1. **Run the tests** — `python -m pytest -q` (37, stdlib only).
2. **Improve the ingredient parser** to handle `1 (14 oz) can tomatoes` — see
   `ingredients.parse_ingredient` and add a test.
3. **Add leftover mode B** (cook-once-eat-twice): give recipes `produces`/`uses`
   tags so roast chicken → chicken soup chains. The seed already has both
   recipes waiting.
4. **Add an explicit unit-conversion table** (3 tsp → 1 tbsp) — but only convert
   when asked, never silently.

`CLAUDE.md` is the orientation file: architecture, conventions, design
rationale, and every deliberate simplification (each one a place to extend).

## License

[MIT](LICENSE).
