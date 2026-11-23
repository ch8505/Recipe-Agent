"""ChefScout domain: recipes, the external TheMealDB API, and the shopping list.

Pure Python, no Claude code here. Both harnesses wrap these functions as tools.
Every function returns a short string (compact output saves tokens) or raises
ToolError, which the harness sends back to the model as an error result.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from shared.memory_store import MemoryError_, MemoryStore, write_json_atomic

DATA = Path(__file__).parent / "data" / "recipes.json"
MEALDB = "https://www.themealdb.com/api/json/v1/1"
MAX_RESULTS = 5


class ToolError(Exception):
    """A tool failed in a way the model can recover from."""


def http_get_json(url: str, timeout: float = 10.0) -> dict:
    """The one network call in the project. Tests replace it with a fake."""
    req = urllib.request.Request(url, headers={"User-Agent": "chefscout-homework/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_recipes() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))


class RecipeDomain:
    """All tool implementations, bound to one state directory."""

    def __init__(self, state_dir: str | Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.recipes = {r["id"]: r for r in load_recipes()}
        self.memory = MemoryStore(self.state_dir)
        self.shop_path = self.state_dir / "shopping_list.json"
        self._web_cache: dict[str, dict] = {}

    # ---- 1. local search ------------------------------------------------------
    def search_recipes(self, query: str = "", max_minutes: int | None = None,
                       diet: str | None = None, exclude_allergens: list[str] | None = None) -> str:
        words = [w for w in (query or "").lower().split() if len(w) > 2]
        exclude = {a.lower().rstrip("s") for a in (exclude_allergens or [])}
        hits = []
        for r in self.recipes.values():
            if max_minutes and r["minutes"] > int(max_minutes):
                continue
            if diet and diet.lower() not in r["diet"]:
                continue
            if exclude & {a.rstrip("s") for a in r["allergens"]}:
                continue
            text = " ".join([r["name"], r["cuisine"], *r["ingredients"]]).lower()
            score = sum(w.rstrip("s") in text for w in words)
            if words and score == 0:
                continue
            hits.append((score, -r["minutes"], r))
        hits.sort(key=lambda h: (h[0], h[1]), reverse=True)
        if not hits:
            return "no matches. try fewer filters."
        rows = [f"{r['id']}|{r['name']}|{r['minutes']}m|{','.join(r['diet'])}|allergens:{','.join(r['allergens']) or '-'}"
                for _, _, r in hits[:MAX_RESULTS]]
        more = f" (+{len(hits) - MAX_RESULTS} more)" if len(hits) > MAX_RESULTS else ""
        return "id|name|time|diet|allergens\n" + "\n".join(rows) + more

    # ---- 2. recipe details ----------------------------------------------------
    def get_recipe(self, recipe_id: str) -> str:
        rid = (recipe_id or "").strip()
        if rid.startswith("mdb:"):
            meal = self._web_cache.get(rid) or self._mealdb_lookup(rid[4:])
            return self._fmt_meal(meal, full=True)
        r = self.recipes.get(rid)
        if not r:
            raise ToolError(f"recipe '{rid}' not found. use an id from search_recipes, or mdb:<id> from search_web_recipes")
        steps = " ".join(f"{i}.{s}" for i, s in enumerate(r["steps"], 1))
        return (f"{r['id']} {r['name']} ({r['minutes']}m, {r['cuisine']})\n"
                f"ingredients: {', '.join(r['ingredients'])}\n"
                f"allergens: {', '.join(r['allergens']) or '-'}\nsteps: {steps}")

    # ---- 3. external: TheMealDB -------------------------------------------------
    def search_web_recipes(self, query: str) -> str:
        q = (query or "").strip()
        if not q:
            raise ToolError("query must not be empty")
        try:
            data = http_get_json(f"{MEALDB}/search.php?s={urllib.parse.quote(q)}")
        except Exception as e:  # network, timeout, bad JSON
            raise ToolError(f"TheMealDB request failed: {type(e).__name__}: {e}") from e
        meals = (data or {}).get("meals") or []
        if not meals:
            return f"no online recipes for '{q}'. try a simpler dish name in English."
        out = []
        for m in meals[:3]:
            self._web_cache[f"mdb:{m['idMeal']}"] = m
            out.append(self._fmt_meal(m, full=False))
        return "\n".join(out)

    def _mealdb_lookup(self, meal_id: str) -> dict:
        try:
            data = http_get_json(f"{MEALDB}/lookup.php?i={urllib.parse.quote(meal_id)}")
        except Exception as e:
            raise ToolError(f"TheMealDB request failed: {type(e).__name__}: {e}") from e
        meals = (data or {}).get("meals") or []
        if not meals:
            raise ToolError(f"online recipe mdb:{meal_id} not found")
        return meals[0]

    @staticmethod
    def _ingredients(m: dict) -> list[str]:
        out = []
        for i in range(1, 21):
            name = (m.get(f"strIngredient{i}") or "").strip()
            if name:
                out.append(name.lower())
        return out

    def _fmt_meal(self, m: dict, full: bool) -> str:
        ing = self._ingredients(m)
        head = f"mdb:{m['idMeal']}|{m['strMeal']}|{m.get('strArea') or '?'}|{m.get('strCategory') or '?'}"
        if not full:
            return f"{head}|ingredients: {', '.join(ing[:12])}{' ...' if len(ing) > 12 else ''}"
        steps = " ".join((m.get("strInstructions") or "").split())
        if len(steps) > 600:  # keep tool output compact
            steps = steps[:600] + " ...[truncated]"
        return f"{head}\ningredients: {', '.join(ing)}\nsteps: {steps}"

    # ---- 4/5. shopping list (file) ---------------------------------------------
    def _shop(self) -> list[str]:
        if self.shop_path.exists():
            return json.loads(self.shop_path.read_text(encoding="utf-8"))
        return []

    def add_to_shopping_list(self, recipe_id: str | None = None, items: list[str] | None = None) -> str:
        new: list[str] = []
        if recipe_id:
            r = self.recipes.get(recipe_id)
            if r:
                new += r["ingredients"]
            elif recipe_id.startswith("mdb:"):
                meal = self._web_cache.get(recipe_id) or self._mealdb_lookup(recipe_id[4:])
                new += self._ingredients(meal)
            else:
                raise ToolError(f"recipe '{recipe_id}' not found")
        new += [i.strip().lower() for i in (items or []) if i and i.strip()]
        if not new:
            raise ToolError("give recipe_id or items")
        current = self._shop()
        added = [i for i in dict.fromkeys(new) if i not in current]
        write_json_atomic(self.shop_path, current + added)
        return f"added {len(added)} (list has {len(current) + len(added)}): {', '.join(added) or '-'}"

    def get_shopping_list(self) -> str:
        items = self._shop()
        return f"{len(items)} items: {', '.join(items)}" if items else "shopping list is empty"

    # ---- 6/7. memory -----------------------------------------------------------
    def save_memory(self, key: str, value: str, remove: bool = False) -> str:
        try:
            return self.memory.save(key, value, remove=remove)
        except MemoryError_ as e:
            raise ToolError(str(e)) from e

    def recall_memory(self, key: str | None = None) -> str:
        self.memory.reload()
        if key:
            return self.memory.compact([key.lower()])
        out = self.memory.compact()
        changes = [h for h in self.memory.history() if h.get("old")]
        if changes:
            out += "\nchanged: " + "; ".join(f"{h['key']} {h['old']}->{h['new']}" for h in changes[-3:])
        return out

    # ---- dispatch helper used by both harnesses --------------------------------
    def call(self, name: str, args: dict) -> str:
        fn = getattr(self, name, None)
        if name.startswith("_") or name not in TOOL_NAMES or fn is None:
            raise ToolError(f"unknown tool '{name}'")
        try:
            return fn(**(args or {}))
        except TypeError as e:  # wrong / missing arguments from the model
            raise ToolError(f"bad arguments for {name}: {e}") from e


TOOL_NAMES = ["search_recipes", "get_recipe", "search_web_recipes", "add_to_shopping_list",
              "get_shopping_list", "save_memory", "recall_memory"]
