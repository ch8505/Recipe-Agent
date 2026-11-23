import pytest

import shared.recipes as recipes
from shared.memory_store import MemoryStore
from shared.recipes import RecipeDomain, ToolError


def test_search_filters_diet_and_allergens(state):
    d = RecipeDomain(state)
    out = d.search_recipes(query="", diet="pescatarian", exclude_allergens=["peanuts"])
    assert "r15" not in out and "r03" not in out
    assert "r07" not in d.search_recipes(diet="vegetarian")
    assert len(out.splitlines()) <= 1 + recipes.MAX_RESULTS + 0  # compact: header + max 5 rows


def test_unknown_recipe_raises_tool_error(state):
    with pytest.raises(ToolError):
        RecipeDomain(state).get_recipe("r99")


def test_external_search_uses_http_and_is_compact(state, no_network):
    out = RecipeDomain(state).search_web_recipes("shakshuka")
    assert "mdb:53025|Shakshuka" in out and "eggs" in out
    assert "search.php?s=shakshuka" in no_network[0]


def test_external_failure_becomes_tool_error(state, monkeypatch):
    def boom(url, timeout=10.0):
        raise TimeoutError("no network")
    monkeypatch.setattr(recipes, "http_get_json", boom)
    with pytest.raises(ToolError, match="TheMealDB request failed"):
        RecipeDomain(state).search_web_recipes("shakshuka")


def test_shopping_list_is_saved_and_deduplicated(state):
    d = RecipeDomain(state)
    d.add_to_shopping_list(recipe_id="r01")
    msg = d.add_to_shopping_list(items=["Rice", "lemons"])
    assert "added 1" in msg  # rice was already there
    assert "chickpeas" in RecipeDomain(state).get_shopping_list()  # new instance reads the file


def test_memory_contradiction_keeps_history(state):
    m = MemoryStore(state)
    m.save("diet", "vegetarian")
    m.save("diet", "Pescatarian")
    m2 = MemoryStore(state)  # reloaded from disk
    assert m2.get("diet") == "pescatarian"
    assert [(h["old"], h["new"]) for h in m2.history() if h["key"] == "diet"] == [(None, "vegetarian"), ("vegetarian", "pescatarian")]
    assert "vegetarian -> pescatarian" in m2.render_markdown()


def test_memory_rejects_bad_values(state):
    d = RecipeDomain(state)
    with pytest.raises(ToolError):
        d.save_memory("diet", "carnivore")
    with pytest.raises(ToolError):
        d.save_memory("password", "x")
