import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import shared.recipes as recipes  # noqa: E402

FAKE_MEALDB = {"meals": [{"idMeal": "53025", "strMeal": "Shakshuka", "strArea": "Egyptian", "strCategory": "Vegetarian",
                          "strInstructions": "Cook the onion. Add tomatoes. Crack eggs.",
                          "strIngredient1": "Eggs", "strIngredient2": "Tomatoes", "strIngredient3": "Onion",
                          "strIngredient4": ""}]}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never touch the internet: TheMealDB is faked."""
    calls = []

    def fake(url, timeout=10.0):
        calls.append(url)
        return FAKE_MEALDB

    monkeypatch.setattr(recipes, "http_get_json", fake)
    return calls


@pytest.fixture
def state(tmp_path):
    return tmp_path / "state"
