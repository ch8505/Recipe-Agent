import asyncio
import json

from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock, ToolUseBlock

import SDK.agent as sdk_agent
from SDK.agent import SdkAgent
from SDK.tools import build_server
from shared.prompt import SYSTEM_PROMPT
from shared.recipes import RecipeDomain
from shared.runner import PARTS, loc_sdk


def test_options_are_locked_down(state):
    a = SdkAgent(state, 1, "claude-opus-5-5", "medium")
    o = a.options()
    assert o.system_prompt == SYSTEM_PROMPT
    assert o.strict_mcp_config is True
    assert o.tools == []  # no built-in Claude Code tools
    assert o.setting_sources == ["project"]
    assert o.model == "claude-opus-5-5" and o.effort == "medium"
    assert sorted(o.allowed_tools) == sorted(f"mcp__chef__{n}" for n in [
        "search_recipes", "get_recipe", "search_web_recipes", "add_to_shopping_list",
        "get_shopping_list", "save_memory", "recall_memory"])
    assert (state / "workspace" / "CLAUDE.md").exists()


def test_tool_handlers_errors_and_memory_file(state):
    d = RecipeDomain(state)
    ws = state / "workspace"
    ws.mkdir(parents=True)
    _, names = build_server(d, ws)
    assert len(names) == 7
    # call the wrapped handlers through the SDK tool objects
    import SDK.tools as t
    captured = {}
    orig = t.create_sdk_mcp_server

    def spy(name, version, tools):
        captured.update({x.name: x for x in tools})
        return orig(name=name, version=version, tools=tools)

    t.create_sdk_mcp_server = spy
    try:
        build_server(d, ws)
    finally:
        t.create_sdk_mcp_server = orig
    ok = asyncio.run(captured["save_memory"].handler({"key": "diet", "value": "vegetarian"}))
    assert ok["is_error"] is False
    assert "diet: vegetarian" in (ws / "CLAUDE.md").read_text(encoding="utf-8")
    bad = asyncio.run(captured["get_recipe"].handler({"recipe_id": "r99"}))
    assert bad["is_error"] is True and "not found" in bad["content"][0]["text"]


class FakeSDKClient:
    seen_options = []
    cum_cost = 0.0  # like the real CLI: total_cost_usd grows over a resumed session

    def __init__(self, options):
        FakeSDKClient.seen_options.append(options)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def query(self, text):
        self.text = text

    async def receive_response(self):
        yield SystemMessage(subtype="init", data={"session_id": "sess-123"})
        yield AssistantMessage(content=[ToolUseBlock(id="t1", name="mcp__chef__get_shopping_list", input={})],
                               model="claude-opus-5-5", message_id="m1")
        yield AssistantMessage(content=[TextBlock(text="Your list is empty.")], model="claude-opus-5-5", message_id="m2")
        FakeSDKClient.cum_cost += 0.0123
        yield ResultMessage(subtype="success", duration_ms=10, duration_api_ms=8, is_error=False, num_turns=2,
                            session_id="sess-123", total_cost_usd=FakeSDKClient.cum_cost, result="Your list is empty.",
                            usage={"input_tokens": 50, "cache_read_input_tokens": 4000,
                                   "cache_creation_input_tokens": 300, "output_tokens": 40})


def test_ask_reads_usage_and_resumes_session(state, monkeypatch):
    monkeypatch.setattr(sdk_agent, "ClaudeSDKClient", FakeSDKClient)
    a = SdkAgent(state, 1, "claude-opus-5-5", "medium")
    r = a.ask("what's on my list?")
    assert r["answer"] == "Your list is empty." and r["tools"] == ["get_shopping_list"]
    assert r["model_calls"] == 2 and r["cache_read_tokens"] == 4000 and r["cost_usd"] == 0.0123
    assert json.loads((state / "sessions" / "session_1.json").read_text())["session_id"] == "sess-123"
    b = SdkAgent(state, 1, "claude-opus-5-5", "medium")  # new instance resumes from disk
    assert b.options().resume == "sess-123"
    assert b.ask("again")["cost_usd"] == 0.0123  # per-turn, not the cumulative 0.0246
    assert SdkAgent(state, 2, "claude-opus-5-5", "medium").options().resume is None


def test_every_harness_part_has_a_replacement_line():
    loc = loc_sdk()
    assert all(loc[p] > 0 for p in PARTS), loc
