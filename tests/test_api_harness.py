import json
from pathlib import Path

from API.agent import ApiAgent
from API.harness import caching, tokens
from API.harness.memory import Memory
from shared.memory_store import MemoryStore
from shared.runner import loc_api, run_scenario
from tests.fakes import FakeClient, ScriptedClient, text_msg, tool_msg

ROOT = Path(__file__).resolve().parent.parent


def agent(state, client, session=1, threshold=100000):
    return ApiAgent(state, session, "claude-opus-5-5", "medium", compaction_threshold=threshold, client=client)


def test_loop_sends_all_tool_results_in_one_message(state):
    client = FakeClient([tool_msg(("search_recipes", {"query": "curry"}), ("get_shopping_list", {})),
                         text_msg("Try r01.")])
    a = agent(state, client)
    r = a.ask("curry please")
    assert r["answer"] == "Try r01." and r["model_calls"] == 2
    assert r["tools"] == ["search_recipes", "get_shopping_list"]
    results_msg = a.messages[2]
    assert results_msg["role"] == "user"
    assert [b["type"] for b in results_msg["content"]] == ["tool_result", "tool_result"]
    assert client.calls[1]["output_config"] == {"effort": "medium"}


def test_tool_errors_go_back_as_is_error(state):
    client = FakeClient([tool_msg(("get_recipe", {"recipe_id": "r99"}), ("no_such_tool", {})), text_msg("Sorry.")])
    a = agent(state, client)
    a.ask("show r99")
    blocks = a.messages[2]["content"]
    assert all(b["is_error"] for b in blocks)
    assert "not found" in blocks[0]["content"] and "unknown tool" in blocks[1]["content"]


def test_history_is_append_only_and_resumes(state):
    a = agent(state, FakeClient([text_msg("one")]))
    a.ask("first")
    path = a.history.path
    lines_before = path.read_text(encoding="utf-8").splitlines()
    b = agent(state, FakeClient([text_msg("two")]))  # new instance, same session
    assert len(b.messages) == 2
    b.ask("second")
    lines_after = path.read_text(encoding="utf-8").splitlines()
    assert lines_after[: len(lines_before)] == lines_before and len(lines_after) == 4


def test_memory_reaches_new_session_and_only_relevant_keys(state):
    a = agent(state, FakeClient([tool_msg(("save_memory", {"key": "allergies", "value": "peanuts"}),
                                          ("save_memory", {"key": "favorites", "value": "shakshuka"})),
                                 text_msg("saved")]))
    a.ask("I'm allergic to peanuts and love shakshuka")
    client2 = FakeClient([text_msg("hi")])
    b = agent(state, client2, session=2)
    assert b.messages == []  # fresh conversation, memory is the only bridge
    b.ask("suggest dinner")
    sent = json.dumps(client2.calls[0]["messages"])
    assert "allergies=peanuts" in sent and "shakshuka" not in sent  # favorites not relevant here
    assert "favorites=shakshuka" in Memory(state).relevant("make my favorite again")


def test_caching_breakpoints_and_history_not_mutated(state):
    client = FakeClient([tool_msg(("get_shopping_list", {})), text_msg("empty")])
    a = agent(state, client)
    a.ask("list?")
    second = client.calls[1]
    assert second["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert second["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert second["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    n_marks = sum("cache_control" in json.dumps(b) for m in second["messages"] for b in m["content"])
    assert n_marks == 1  # rolling breakpoint, max 4 in total
    assert "cache_control" not in json.dumps(a.messages)
    assert "cache_control" not in a.history.path.read_text(encoding="utf-8")


def test_compaction_summarizes_past_threshold(state):
    client = FakeClient([text_msg("one"), text_msg("two")])
    a = agent(state, client, threshold=50)
    a.ask("first message")
    r = a.ask("second message")
    assert r["model_calls"] == 2  # summary call + agent call
    assert "tools" not in client.calls[1]  # the summary request
    assert len(a.messages) == 2  # history replaced by summary
    assert "SUMMARY" in json.dumps(client.calls[2]["messages"][0])
    events = a.history.events()
    assert [e["type"] for e in events].count("compaction") == 1
    assert len(a.history.events()) == 5  # nothing deleted on disk: 2 + marker + 2


def test_token_cost_math():
    assert tokens.cost("claude-opus-5-5", 1_000_000, 0, 0, 0) == 4.0
    assert round(tokens.cost("claude-opus-5-5", 0, 1000, 10000, 2000), 6) == round(0.02 + 0.002 + 0.01, 6)


def test_caching_apply_never_touches_input():
    tools_in = [{"name": "a"}]
    system_in = [{"type": "text", "text": "s"}]
    msgs_in = [{"role": "user", "content": [{"type": "text", "text": "x"}]}]
    caching.apply(tools_in, system_in, msgs_in)
    assert "cache_control" not in json.dumps([tools_in, system_in, msgs_in])


def test_full_scenario_offline(state, tmp_path, monkeypatch):
    """The real scenario.json end to end with a scripted model: all checks must pass."""
    out = tmp_path / "api.json"

    def make(sid, scenario):
        return ApiAgent(state, sid, scenario["model"], scenario["effort"], client=ScriptedClient())

    res = run_scenario("api-offline", str(ROOT / "scenario.json"), str(out), state, make, loc_api())
    assert res["checks_passed"] == "8/8", res["checks"]
    assert MemoryStore(state).get("diet") == "pescatarian"
    assert len(res["turns"]) == 7 and all(t["model_calls"] >= 1 for t in res["turns"])
    assert set(res["loc"]) == {"loop", "tools", "history", "memory", "context", "compaction", "caching", "tokens"}
