"""Tests for the deterministic-math heart: parsing, canonicalization, and
shopping-list aggregation. These are the functions that justify the MCP
(exact computation Claude would otherwise hand-wave), so they're the most
heavily covered."""

from mealplanner.ingredients import aggregate, canonical_item, parse_ingredient
from mealplanner.models import Ingredient


class TestParseIngredient:
    def test_qty_and_unit(self):
        ing = parse_ingredient("1 cup flour")
        assert ing.qty == 1.0
        assert ing.unit == "cup"
        assert ing.item == "flour"

    def test_count_no_unit(self):
        # "egg" is not a unit, so "3 egg yolks" -> qty 3, no unit.
        ing = parse_ingredient("3 egg yolks")
        assert ing.qty == 3.0
        assert ing.unit is None
        assert ing.item == "egg yolks"

    def test_mixed_fraction_and_abbrev_unit(self):
        ing = parse_ingredient("1 1/2 lbs chicken")
        assert ing.qty == 1.5
        assert ing.unit == "pound"   # "lbs" canonicalized
        assert ing.item == "chicken"

    def test_unicode_fraction(self):
        ing = parse_ingredient("½ cup sugar")
        assert ing.qty == 0.5
        assert ing.unit == "cup"
        assert ing.item == "sugar"

    def test_range_takes_midpoint(self):
        ing = parse_ingredient("2-3 cloves garlic")
        assert ing.qty == 2.5
        assert ing.unit == "clove"
        assert ing.item == "garlic"

    def test_unmeasured_is_qty_none(self):
        ing = parse_ingredient("salt to taste")
        assert ing.qty is None
        assert ing.unit is None
        assert ing.item == "salt to taste"

    def test_parenthetical_is_dropped(self):
        ing = parse_ingredient("3 egg yolks (see how to separate eggs)")
        assert ing.qty == 3.0
        assert ing.item == "egg yolks"

    def test_raw_preserved(self):
        ing = parse_ingredient("1 cup flour")
        assert ing.raw == "1 cup flour"


class TestCanonicalItem:
    def test_strips_descriptors_and_singularizes(self):
        assert canonical_item("Chopped Yellow Onions") == "yellow onion"

    def test_trailing_note_dropped(self):
        assert canonical_item("garlic, minced") == "garlic"

    def test_fresh_plural(self):
        assert canonical_item("Fresh Tomatoes") == "tomato"

    def test_irregular_plural(self):
        assert canonical_item("Eggs") == "egg"

    def test_us_ending_not_over_stripped(self):
        # "asparagus" isn't a plural — don't turn it into "asparagu".
        assert canonical_item("asparagus") == "asparagus"

    def test_keeps_distinguishing_color(self):
        # red onion vs yellow onion are different purchases — don't collapse.
        assert canonical_item("red onion") != canonical_item("yellow onion")


class TestAggregate:
    def test_sums_same_item_and_unit(self):
        items = [
            (Ingredient(item="flour", qty=1, unit="cup"), 1.0),
            (Ingredient(item="flour", qty=2, unit="cup"), 1.0),
        ]
        out = aggregate(items)
        assert len(out) == 1
        assert out[0].qty == 3.0
        assert out[0].unit == "cup"

    def test_scaling_multiplies_quantity(self):
        # A 4-serving recipe cooked for 6 -> scale 1.5.
        items = [(Ingredient(item="chicken breast", qty=1, unit="pound"), 1.5)]
        out = aggregate(items)
        assert out[0].qty == 1.5

    def test_different_units_stay_separate(self):
        # No silent unit conversion.
        items = [
            (Ingredient(item="rice", qty=1, unit="cup"), 1.0),
            (Ingredient(item="rice", qty=2, unit="pound"), 1.0),
        ]
        out = aggregate(items)
        assert len(out) == 2

    def test_unmeasured_collapses_to_one(self):
        items = [
            (Ingredient(item="salt", qty=None, unit=None), 1.0),
            (Ingredient(item="salt", qty=None, unit=None), 1.0),
        ]
        out = aggregate(items)
        assert len(out) == 1
        assert out[0].qty is None

    def test_merges_across_canonical_names(self):
        # "Chopped yellow onions" and "yellow onion" are the same shopping line.
        items = [
            (Ingredient(item="Chopped yellow onions", qty=1, unit=None), 1.0),
            (Ingredient(item="yellow onion", qty=2, unit=None), 1.0),
        ]
        out = aggregate(items)
        assert len(out) == 1
        assert out[0].qty == 3.0
