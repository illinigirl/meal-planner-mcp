"""Test fixtures + import-path setup.

Puts `src/` on the path so tests can `from mealplanner import ...` without an
editable install — keeping with the zero-setup goal: the pure-core tests run on
stdlib alone (no `pip install` needed; that's only for the MCP server itself).
"""

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from mealplanner.models import Recipe  # noqa: E402

_SEED = Path(__file__).resolve().parent.parent / "data" / "recipes.seed.json"


@pytest.fixture
def library() -> list[Recipe]:
    """The bundled seed library, as Recipe objects."""
    raw = json.loads(_SEED.read_text())
    return [Recipe.from_dict(r) for r in raw["recipes"]]
