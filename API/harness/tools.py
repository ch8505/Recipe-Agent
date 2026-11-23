"""Tool JSON schemas, dispatch, and errors returned to the model as is_error."""
from __future__ import annotations

from API.harness import log
from shared.memory_store import ALL_KEYS, DIETS
from shared.recipes import RecipeDomain, ToolError

F = "tools.py"
MAX_RESULT_CHARS = 1500  # hard cap per tool_result, keeps context small

TOOL_SCHEMAS = [
    {
        "name": "search_recipes",
        "description": "Search the local recipe catalog. Returns up to 5 rows: id|name|time|diet|allergens.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words to match in name, cuisine or ingredients. May be empty."},
                "max_minutes": {"type": "integer", "description": "Maximum cooking time in minutes."},
                "diet": {"type": "string", "enum": DIETS[1:], "description": "Only recipes suitable for this diet."},
                "exclude_allergens": {"type": "array", "items": {"type": "string"},
                                      "description": "Allergens to exclude, e.g. ['peanuts']."},
            },
        },
    },
    {
        "name": "get_recipe",
        "description": "Full ingredients and steps for one recipe id (local 'r01' or online 'mdb:52772').",
        "input_schema": {"type": "object", "properties": {"recipe_id": {"type": "string"}}, "required": ["recipe_id"]},
    },
    {
        "name": "search_web_recipes",
        "description": "Search online recipes on TheMealDB (internet). Query is a dish name in English. Returns up to 3 results.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "add_to_shopping_list",
        "description": "Add all ingredients of a recipe (recipe_id) and/or single items to the saved shopping list.",
        "input_schema": {
            "type": "object",
            "properties": {"recipe_id": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}},
        },
    },
    {
        "name": "get_shopping_list",
        "description": "Read the saved shopping list.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "save_memory",
        "description": "Save a lasting fact about the user. diet/household_size/skill_level replace the old value; "
                       "allergies/dislikes/favorites/notes add one value (remove=true deletes it).",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "enum": ALL_KEYS},
                "value": {"type": "string", "description": "English, lowercase."},
                "remove": {"type": "boolean"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "recall_memory",
        "description": "Read saved facts about the user (all, or one key) and recent changes.",
        "input_schema": {"type": "object", "properties": {"key": {"type": "string", "enum": ALL_KEYS}}},
    },
]


class ToolRunner:
    def __init__(self, domain: RecipeDomain):
        self.domain = domain

    def schemas(self) -> list[dict]:
        return TOOL_SCHEMAS

    def run_one(self, name: str, args: dict, tool_use_id: str) -> dict:
        try:
            text = self.domain.call(name, args)
            is_error = False
        except ToolError as e:
            text, is_error = f"error: {e}", True
        except Exception as e:  # bug in a tool: report it, never crash the loop
            text, is_error = f"internal error in {name}: {type(e).__name__}: {e}", True
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + " ...[truncated]"
        log(F, f"{name}({args}) -> {'ERROR ' if is_error else ''}{len(text)} chars")
        block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": text}
        if is_error:
            block["is_error"] = True
        return block

    def execute(self, tool_uses: list) -> list[dict]:
        """Runs every tool_use block of one assistant message; returns all results (for ONE user message)."""
        log(F, f"dispatching {len(tool_uses)} tool call(s)")
        return [self.run_one(b["name"], b.get("input") or {}, b["id"]) for b in tool_uses]
