---
description: Add an MCP tool ONLY if it passes the four-part test; otherwise compose existing tools.
argument-hint: <what the new tool would do>
---
You are considering adding a new MCP tool to this server: **$ARGUMENTS**

Before writing any code, apply this repo's four-part test (see `CLAUDE.md` →
"Why this is an MCP and not just a prompt"). A capability earns a tool ONLY if
it does something the model can't do well on its own:

1. **Persists state** across sessions (e.g. cooked-history in `state.json`)
2. **Causes a side effect** / writes a durable artifact (e.g. an export file)
3. **Accesses private or live data** (e.g. the user's local recipe library)
4. **Computes something that must be exact** (e.g. ingredient merge/scale math)

Then do exactly this:

- State, in ONE sentence, which of the four (if any) "$ARGUMENTS" serves.
- **If it serves none** — it's "reason over what Claude already knows" — do
  NOT add a tool. Show how to get the result by composing existing tools
  (e.g. `suggest_recipes` → `swap_meal` for "make Friday quicker"), and stop.
- **If it serves at least one**, scaffold it the repo's way:
  - Put the real logic in the appropriate PURE module (`ingredients` / `core` /
    `planner` / `exports`) with a direct unit test in `tests/` — no I/O in the
    logic.
  - Add a THIN `@mcp.tool()` wrapper in `server.py` that calls the pure function
    and touches the filesystem only through `store.py`.
  - Give it a planning-flavored name that won't collide with a storage-style
    recipes server (see CLAUDE.md → "Running alongside another recipe MCP").
  - Mirror the wrapper into `cli.py` if it makes sense as a CLI verb too.
  - Run `python -m pytest -q` and `ruff check src/mealplanner tests` before
    declaring done.

Report which branch you took (composed vs. added) and the one-sentence
justification.
