"""Ingredient parsing, canonicalization, and shopping-list aggregation.

This is the deterministic-math heart of the project (justification #4: the
exact computation Claude would otherwise hand-wave). Three pure functions, all
heavily unit-tested:

- parse_ingredient: free text  -> structured {qty, unit, item}   (powers CSV import)
- canonical_item:   "Chopped Yellow Onions" -> "onion"           (powers overlap + merge)
- aggregate:        many recipe ingredients  -> one shopping list (merge + scale)

Deliberate simplifications, each a documented "good first task" for a reviewer:
- No unit conversion. Same item in different units stays on separate lines
  (we never silently turn 3 tsp into 1 tbsp).
- Singularization is a small rule table, not a stemmer.
"""

from __future__ import annotations

import re
from collections import OrderedDict

from .models import Ingredient

# Units we recognize as a leading measurement. Anything else after the quantity
# is treated as part of the item name ("2 eggs" -> qty=2, unit=None, item="egg").
_UNITS = {
    "cup", "cups", "c",
    "tablespoon", "tablespoons", "tbsp", "tbsp.", "tbs", "t",
    "teaspoon", "teaspoons", "tsp", "tsp.",
    "ounce", "ounces", "oz", "oz.",
    "pound", "pounds", "lb", "lb.", "lbs",
    "gram", "grams", "g", "kilogram", "kilograms", "kg",
    "milliliter", "milliliters", "ml", "liter", "liters", "l",
    "clove", "cloves", "can", "cans", "package", "packages", "pkg",
    "slice", "slices", "pinch", "pinches", "bunch", "bunches",
    "head", "heads", "stalk", "stalks", "sprig", "sprigs", "quart", "quarts",
    "pint", "pints", "stick", "sticks", "dash", "dashes",
}

# Map plural/abbreviated units to a canonical spelling so "cups"/"c" merge.
_UNIT_CANON = {
    "cups": "cup", "c": "cup",
    "tablespoons": "tablespoon", "tbsp": "tablespoon", "tbsp.": "tablespoon",
    "tbs": "tablespoon", "t": "tablespoon",
    "teaspoons": "teaspoon", "tsp": "teaspoon", "tsp.": "teaspoon",
    "ounces": "ounce", "oz": "ounce", "oz.": "ounce",
    "pounds": "pound", "lb": "pound", "lb.": "pound", "lbs": "pound",
    "grams": "gram", "g": "gram", "kilograms": "kilogram", "kg": "kilogram",
    "milliliters": "milliliter", "ml": "milliliter",
    "liters": "liter", "l": "liter",
    "cloves": "clove", "cans": "can", "packages": "package", "pkg": "package",
    "slices": "slice", "pinches": "pinch", "bunches": "bunch",
    "heads": "head", "stalks": "stalk", "sprigs": "sprig", "quarts": "quart",
    "pints": "pint", "sticks": "stick", "dashes": "dash",
}

# Descriptors stripped when canonicalizing an item for overlap/merge.
_DESCRIPTORS = {
    "chopped", "diced", "minced", "sliced", "fresh", "frozen", "dried",
    "ground", "large", "small", "medium", "ripe", "boneless", "skinless",
    "shredded", "grated", "crushed", "peeled", "cooked", "raw", "finely",
    "roughly", "thinly", "extra", "virgin",
}

# Tiny irregular/regular singularization table — enough for grocery items.
_SINGULAR = {
    "tomatoes": "tomato", "potatoes": "potato", "onions": "onion",
    "eggs": "egg", "carrots": "carrot", "peppers": "pepper",
    "leaves": "leaf", "loaves": "loaf", "berries": "berry",
}

_UNICODE_FRACTIONS = {
    "½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}


def _parse_quantity(token: str) -> float | None:
    """'1', '1/2', '1 1/2', '½', '2-3' -> float (ranges take the midpoint)."""
    token = token.strip()
    if not token:
        return None
    # Range like "2-3" or "2–3": midpoint.
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)", token)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2
    total = 0.0
    matched = False
    for part in token.split():
        if part in _UNICODE_FRACTIONS:
            total += _UNICODE_FRACTIONS[part]
            matched = True
        elif re.fullmatch(r"\d+/\d+", part):
            num, den = part.split("/")
            total += float(num) / float(den)
            matched = True
        elif re.fullmatch(r"\d+(?:\.\d+)?", part):
            total += float(part)
            matched = True
        else:
            return total if matched else None
    return total if matched else None


def parse_ingredient(raw: str) -> Ingredient:
    """Heuristically split a free-text ingredient line into qty/unit/item.

    Examples:
        "3 egg yolks"        -> qty=3,   unit=None,  item="egg yolks"
        "1 cup flour"        -> qty=1,   unit="cup", item="flour"
        "1 1/2 lbs chicken"  -> qty=1.5, unit="pound", item="chicken"
        "salt to taste"      -> qty=None, unit=None, item="salt to taste"
    """
    text = (raw or "").strip()
    # Drop parenthetical asides: "(see how to separate eggs)".
    cleaned = re.sub(r"\(.*?\)", "", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return Ingredient(item=text, raw=raw)

    # Pull a leading quantity (digits, fractions, unicode fractions, ranges).
    qty_match = re.match(
        r"^((?:\d+\s+\d+/\d+)|(?:\d+/\d+)|(?:\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?)"
        r"|[½¼¾⅓⅔⅛⅜⅝⅞]|(?:\d+(?:\.\d+)?))\s*",
        cleaned,
    )
    qty = None
    rest = cleaned
    if qty_match:
        qty = _parse_quantity(qty_match.group(1))
        rest = cleaned[qty_match.end():].strip()

    # Optional unit immediately after the quantity.
    unit = None
    if qty is not None and rest:
        first, _, remainder = rest.partition(" ")
        if first.lower() in _UNITS:
            unit = _UNIT_CANON.get(first.lower(), first.lower())
            rest = remainder.strip()

    item = rest or cleaned
    return Ingredient(item=item, qty=qty, unit=unit, raw=raw)


def canonical_item(item: str) -> str:
    """Normalize an item name for overlap detection and shopping merge.

    "Chopped Yellow Onions" / "onion, diced" -> "onion". Lowercases, strips
    parentheticals + trailing notes, removes descriptor words, singularizes.
    """
    s = item.lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = s.split(",")[0]                       # drop "onion, diced" trailing note
    s = re.sub(r"[^a-z\s/-]", " ", s)
    words = [w for w in s.split() if w and w not in _DESCRIPTORS]
    words = [_SINGULAR.get(w, w) for w in words]
    # Naive regular plural: trailing 's' (but not 'ss' like "grass").
    words = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
             for w in words]
    return " ".join(words).strip()


def aggregate(items: list[tuple[Ingredient, float]]) -> list[Ingredient]:
    """Merge (ingredient, scale) pairs into a consolidated shopping list.

    `scale` is the serving multiplier for the recipe the ingredient came from
    (e.g. cooking a 4-serving recipe for 6 -> scale 1.5). Lines merge by
    (canonical item, canonical unit); quantities sum; unmeasured lines (qty
    None) collapse to a single entry. Same item in different units stays
    separate (no unit conversion — see module docstring).
    """
    merged: "OrderedDict[tuple[str, str | None], Ingredient]" = OrderedDict()
    for ing, scale in items:
        key = (canonical_item(ing.item), ing.unit)
        if key in merged:
            existing = merged[key]
            if ing.qty is None or existing.qty is None:
                new_qty = existing.qty if existing.qty is not None else ing.qty
            else:
                new_qty = existing.qty + ing.qty * scale
            merged[key] = Ingredient(item=existing.item, qty=new_qty, unit=existing.unit)
        else:
            qty = ing.qty * scale if ing.qty is not None else None
            merged[key] = Ingredient(item=canonical_item(ing.item), qty=qty, unit=ing.unit)
    return list(merged.values())
