---
description: Implement one of the repo's deliberate-simplification seams, test-first.
argument-hint: "[parser | units | singularize | pantry | leftovers-b | importer]"
---
Extend one of this repo's deliberate-simplification seams (see `CLAUDE.md` →
"Deliberate simplifications"). If "$ARGUMENTS" names a seam, do that one;
otherwise pick the highest-value seam and say why in one sentence first.

House rules for this repo (don't violate these):

- Logic goes in a PURE module with a direct test; the MCP/CLI adapters stay thin.
- Write the FAILING test first, then implement until it's green.
- **No silent unit conversion** — same item in different units stays on separate
  shopping lines.
- Classification is **course-based, not title-based** (`course` is the
  normalized field; unknown course → treat as a main, never silently drop).
- Canonicalization preserves real distinctions (red onion ≠ yellow onion).
- Finish with `python -m pytest -q` green and `ruff check src/mealplanner tests`
  clean.

Seam reference:
- **parser** — `ingredients.parse_ingredient`: handle `1 (14 oz) can tomatoes`,
  "a pinch", multi-unit lines.
- **units** — add an EXPLICIT conversion table (3 tsp → 1 tbsp) applied only on
  request, never silently.
- **singularize** — extend the `_SINGULAR` rule table or swap in `inflect`.
- **pantry** — make `core.PANTRY_STAPLES` per-user / configurable.
- **leftovers-b** — cook-once-eat-twice via `produces`/`uses` recipe tags
  (roast chicken → chicken soup). The seed already carries `roast-chicken` + a
  `cooked chicken` soup waiting for it. Keep it behind the same `plan_week`
  signature.
- **importer** — add a Paprika / Mealie / plain-JSON importer behind
  `store.import_*`, alongside the Plan to Eat one.
