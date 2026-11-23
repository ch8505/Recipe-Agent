"""The agent loop: call the model while stop_reason == "tool_use".

All tool_result blocks of one assistant message go back in ONE user message.
"""
from __future__ import annotations

from API.harness import caching, log
from API.harness.history import History, to_dict
from API.harness.tokens import TokenMeter
from API.harness.tools import ToolRunner

F = "loop.py"
MAX_ITERATIONS = 12
MAX_TOKENS = 16000


def run_turn(client, model: str, effort: str, system: list[dict], runner: ToolRunner,
             messages: list[dict], history: History, meter: TokenMeter) -> tuple[str, list[str]]:
    """messages already ends with the new user message. Returns (answer, tools used)."""
    tools_used: list[str] = []
    for i in range(1, MAX_ITERATIONS + 1):
        tools, sys_blocks, msgs = caching.apply(runner.schemas(), system, messages)
        log(F, f"iteration {i}: calling {model} with {len(msgs)} messages")
        resp = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=sys_blocks,
            tools=tools,
            messages=msgs,
            output_config={"effort": effort},
        )
        meter.record(resp.usage)
        assistant = {"role": "assistant", "content": [to_dict(b) for b in resp.content]}
        messages.append(assistant)
        history.append_message(assistant)
        log(F, f"stop_reason={resp.stop_reason}")

        if resp.stop_reason != "tool_use":
            if resp.stop_reason in ("max_tokens", "refusal"):
                log(F, f"WARNING: turn ended with {resp.stop_reason}")
            text = "".join(b["text"] for b in assistant["content"] if b.get("type") == "text").strip()
            return text or f"(no text, stop_reason={resp.stop_reason})", tools_used

        tool_uses = [b for b in assistant["content"] if b.get("type") == "tool_use"]
        tools_used += [b["name"] for b in tool_uses]
        results = runner.execute(tool_uses)
        user = {"role": "user", "content": results}  # every result in a single message
        messages.append(user)
        history.append_message(user)
    log(F, f"stopped after {MAX_ITERATIONS} iterations")
    return "(stopped: too many tool iterations)", tools_used
