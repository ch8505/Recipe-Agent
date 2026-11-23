"""Prompt caching: where the cache_control breakpoints go.

Render order is tools -> system -> messages, so we mark:
  1. the last tool          (tool list is fixed for the whole run)
  2. the system prompt      (fixed text)
  3. the last block of the last message (rolling: next call reads all history from cache)
3 of the 4 allowed breakpoints. Stored history is never mutated; we mark copies.
"""
from __future__ import annotations

import copy

from API.harness import log

F = "caching.py"
EPHEMERAL = {"type": "ephemeral"}


def apply(tools: list[dict], system: list[dict], messages: list[dict]):
    tools = copy.deepcopy(tools)
    system = copy.deepcopy(system)
    messages = copy.deepcopy(messages)
    tools[-1]["cache_control"] = EPHEMERAL
    system[-1]["cache_control"] = EPHEMERAL
    if messages and messages[-1]["content"]:
        messages[-1]["content"][-1]["cache_control"] = EPHEMERAL
    log(F, f"breakpoints: tools[{len(tools) - 1}], system, messages[{len(messages) - 1}] last block")
    return tools, system, messages
