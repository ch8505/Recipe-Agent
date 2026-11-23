"""Fake Messages API client built from the real anthropic response types."""
from __future__ import annotations

import copy
import itertools

from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

_ids = itertools.count(1)


def text_msg(text: str, usage=(100, 20, 0, 0)) -> Message:
    return _msg([TextBlock(type="text", text=text)], "end_turn", usage)


def tool_msg(*calls: tuple[str, dict], usage=(100, 30, 0, 0)) -> Message:
    blocks = [ToolUseBlock(type="tool_use", id=f"toolu_{next(_ids)}", name=n, input=a) for n, a in calls]
    return _msg(blocks, "tool_use", usage)


def _msg(content, stop, usage) -> Message:
    inp, out, cr, cw = usage
    return Message(id=f"msg_{next(_ids)}", type="message", role="assistant", model="claude-opus-5-5",
                   content=content, stop_reason=stop, stop_sequence=None,
                   usage=Usage(input_tokens=inp, output_tokens=out,
                               cache_read_input_tokens=cr, cache_creation_input_tokens=cw))


class _Messages:
    def __init__(self, owner):
        self.owner = owner

    def create(self, **kwargs):
        self.owner.calls.append(copy.deepcopy(kwargs))
        return self.owner.respond(kwargs)


class FakeClient:
    """Pass a list of responses (played in order) or override respond()."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls: list[dict] = []
        self.messages = _Messages(self)

    def respond(self, kwargs):
        if "tools" not in kwargs:  # compaction.py summary call
            return text_msg("SUMMARY: user is vegetarian, picked r01.")
        return self.responses.pop(0)


def last_user_text(kwargs) -> str:
    m = kwargs["messages"][-1]
    return " ".join(b.get("text", "") for b in m["content"] if b.get("type") == "text")


class ScriptedClient(FakeClient):
    """Plays the whole scenario.json: picks tool calls from the user's words."""

    SCRIPT = [
        ("remember both", [("save_memory", {"key": "diet", "value": "vegetarian"}),
                           ("save_memory", {"key": "allergies", "value": "peanuts"})], "Saved: vegetarian, peanut allergy."),
        ("under 30", [("search_recipes", {"max_minutes": 30, "diet": "vegetarian", "exclude_allergens": ["peanuts"]})],
         "Try r01 Chickpea Spinach Curry (25m)."),
        ("online", [("search_web_recipes", {"query": "shakshuka"})], "Shakshuka: eggs, tomatoes, onion."),
        ("shopping list and save", [("add_to_shopping_list", {"recipe_id": "r01"}),
                                    ("save_memory", {"key": "favorites", "value": "chickpea spinach curry"})], "Done."),
        ("what do you remember", [], "You are vegetarian and allergic to peanuts."),
        ("eating fish", [("save_memory", {"key": "diet", "value": "pescatarian"}),
                         ("search_recipes", {"query": "fish", "diet": "pescatarian", "exclude_allergens": ["peanuts"]})],
         "Diet updated to pescatarian. Try r04 Lemon Garlic Salmon."),
        ("shopping list now", [("get_shopping_list", {})], "chickpeas, spinach, coconut milk ..."),
    ]

    def respond(self, kwargs):
        if "tools" not in kwargs:
            return text_msg("SUMMARY")
        last = kwargs["messages"][-1]
        if last["content"][0].get("type") == "tool_result":
            return text_msg(self._pending)
        text = last_user_text(kwargs).lower()
        for key, calls, answer in self.SCRIPT:
            if key in text:
                self._pending = answer
                return tool_msg(*calls) if calls else text_msg(answer)
        return text_msg("ok")
