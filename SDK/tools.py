"""ChefScout tools for the Agent SDK: @tool wrappers over shared/recipes.py.

The SDK builds the JSON schema, the dispatch and the MCP plumbing; we only
wrap the domain functions and say which errors are is_error.
"""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from shared.memory_store import ALL_KEYS, DIETS
from shared.recipes import RecipeDomain, ToolError

SERVER = "chef"
MAX_RESULT_CHARS = 1500


def render_memory_file(domain: RecipeDomain, workspace: Path) -> None:
    (workspace / "CLAUDE.md").write_text(domain.memory.render_markdown(), encoding="utf-8")  # replaces: memory


def build_server(domain: RecipeDomain, workspace: Path):
    def run(name: str, args: dict) -> dict:
        try:  # replaces: tools
            text, err = domain.call(name, args), False  # replaces: tools
        except ToolError as e:  # replaces: tools
            text, err = f"error: {e}", True  # replaces: tools
        if name == "save_memory" and not err:
            render_memory_file(domain, workspace)  # replaces: memory
        return {"content": [{"type": "text", "text": text[:MAX_RESULT_CHARS]}], "is_error": err}  # replaces: tools

    @tool("search_recipes", "Search the local recipe catalog. Returns up to 5 rows: id|name|time|diet|allergens.", {  # replaces: tools
        "type": "object",
        "properties": {
            "query": {"type": "string"}, "max_minutes": {"type": "integer"},
            "diet": {"type": "string", "enum": DIETS[1:]},
            "exclude_allergens": {"type": "array", "items": {"type": "string"}},
        }})
    async def search_recipes(args):
        return run("search_recipes", args)

    @tool("get_recipe", "Full ingredients and steps for one recipe id (local 'r01' or online 'mdb:52772').",  # replaces: tools
          {"type": "object", "properties": {"recipe_id": {"type": "string"}}, "required": ["recipe_id"]})
    async def get_recipe(args):
        return run("get_recipe", args)

    @tool("search_web_recipes", "Search online recipes on TheMealDB (internet). Query is a dish name in English.",  # replaces: tools
          {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})
    async def search_web_recipes(args):
        return run("search_web_recipes", args)

    @tool("add_to_shopping_list", "Add all ingredients of a recipe (recipe_id) and/or single items to the saved shopping list.",  # replaces: tools
          {"type": "object", "properties": {"recipe_id": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}}})
    async def add_to_shopping_list(args):
        return run("add_to_shopping_list", args)

    @tool("get_shopping_list", "Read the saved shopping list.", {"type": "object", "properties": {}})  # replaces: tools
    async def get_shopping_list(args):
        return run("get_shopping_list", args)

    @tool("save_memory", "Save a lasting fact about the user. diet/household_size/skill_level replace the old value; "  # replaces: tools, memory
          "allergies/dislikes/favorites/notes add one value (remove=true deletes it).",
          {"type": "object", "properties": {"key": {"type": "string", "enum": ALL_KEYS}, "value": {"type": "string"},
                                            "remove": {"type": "boolean"}}, "required": ["key", "value"]})
    async def save_memory(args):
        return run("save_memory", args)

    @tool("recall_memory", "Read saved facts about the user (all, or one key) and recent changes.",  # replaces: tools, memory
          {"type": "object", "properties": {"key": {"type": "string", "enum": ALL_KEYS}}})
    async def recall_memory(args):
        return run("recall_memory", args)

    tools = [search_recipes, get_recipe, search_web_recipes, add_to_shopping_list,
             get_shopping_list, save_memory, recall_memory]
    server = create_sdk_mcp_server(name=SERVER, version="1.0.0", tools=tools)  # replaces: tools
    names = [f"mcp__{SERVER}__{t.name}" for t in tools]  # replaces: tools
    return server, names
