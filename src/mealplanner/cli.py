"""A thin CLI over the same core — so the project runs and demos WITHOUT wiring
up an MCP client, and gives you the "lists of recipes" view in the terminal.

    python -m mealplanner.cli list [--tag vegetarian] [--max-time 30]
    python -m mealplanner.cli plan --days 7 --household 4
    python -m mealplanner.cli shopping
    python -m mealplanner.cli export [path.md]
    python -m mealplanner.cli import <plantoeat.csv>
"""

from __future__ import annotations

import argparse
from datetime import date

from . import core, store
from .exports import build_shopping_list, render_plan_markdown, render_plan_text
from .ingredients import Ingredient  # noqa: F401
from .planner import plan_week


def _fmt_qty(q):
    if q is None:
        return ""
    return str(int(q)) if float(q).is_integer() else f"{q:g}"


def cmd_list(args):
    lib = store.load_library()
    rows = core.search_recipes(lib, max_time=args.max_time,
                               include_tags=[args.tag] if args.tag else None)
    print(f"{len(rows)} recipes\n")
    for r in sorted(rows, key=lambda x: x.title):
        t = f"{r.total_time_min}m" if r.total_time_min else "—"
        print(f"  {r.title:<28} serves {r.servings:<2} {t:>5}  [{', '.join(r.tags)}]")


def cmd_plan(args):
    lib = store.load_library()
    plan = plan_week(lib, days=args.days, start_date=date.today(),
                     household_size=args.household, history=store.history_entries())
    store.save_plan(plan)
    idx = core.recipe_index(lib)
    print(f"Plan for {args.days} days (household {args.household}):\n")
    for d in plan:
        if d.leftover_of:
            print(f"  {d.date}   ↩ leftovers ({idx[d.recipe_id].title})")
        else:
            print(f"  {d.date}   {idx[d.recipe_id].title}  (serves {idx[d.recipe_id].servings})")
    print("\nSaved as current plan. Run `shopping` or `export` next.")


def cmd_shopping(args):
    plan = store.load_plan()
    if not plan:
        print("No current plan — run `plan` first.")
        return
    idx = core.recipe_index(store.load_library())
    shopping = build_shopping_list(plan, idx)
    print("Shopping list:\n")
    for ing in sorted(shopping, key=lambda i: i.item):
        amt = " ".join(p for p in (_fmt_qty(ing.qty), ing.unit) if p)
        print(f"  [ ] {amt + '  ' if amt else ''}{ing.item}")


def cmd_export(args):
    plan = store.load_plan()
    if not plan:
        print("No current plan — run `plan` first.")
        return
    from pathlib import Path
    idx = core.recipe_index(store.load_library())
    title = f"Meal Plan — week of {plan[0].date}"
    if args.format == "text":
        content, ext = render_plan_text(plan, idx, title=title), "txt"
    else:
        content, ext = render_plan_markdown(plan, idx, title=title), "md"
    out = Path(args.path) if args.path else store.export_default_path(plan[0].date, ext=ext)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content)
    print(f"Wrote {out}")


def cmd_import(args):
    added = store.import_plantoeat_csv(args.csv)
    print(f"Imported {added} recipes into {store.state_path()}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mealplanner", description="Self-contained meal planner")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="list recipes in the library")
    pl.add_argument("--tag")
    pl.add_argument("--max-time", type=int, dest="max_time")
    pl.set_defaults(func=cmd_list)

    pp = sub.add_parser("plan", help="build + save a meal plan")
    pp.add_argument("--days", type=int, default=7)
    pp.add_argument("--household", type=int, default=4)
    pp.set_defaults(func=cmd_plan)

    ps = sub.add_parser("shopping", help="shopping list for the current plan")
    ps.set_defaults(func=cmd_shopping)

    pe = sub.add_parser("export", help="write plan + list to a file")
    pe.add_argument("path", nargs="?")
    pe.add_argument("--format", choices=["markdown", "text"], default="markdown")
    pe.set_defaults(func=cmd_export)

    pi = sub.add_parser("import", help="import a Plan to Eat CSV")
    pi.add_argument("csv")
    pi.set_defaults(func=cmd_import)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
