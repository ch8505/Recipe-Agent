"""What goes into each turn.

- system: the fixed ChefScout prompt (never changes, so it caches).
- tools: the fixed tool list (same reason).
- the new user message = only the relevant memory slice + a summary if the
  conversation was compacted + the user's text.
The recipe catalog, the shopping list and the full memory are NOT sent; the
model fetches them with tools when it needs them.
"""
from __future__ import annotations

from API.harness import log
from shared.prompt import SYSTEM_PROMPT

F = "context.py"


def system_blocks() -> list[dict]:
    return [{"type": "text", "text": SYSTEM_PROMPT}]


def user_turn(user_text: str, memory_digest: str, summary: str | None = None) -> dict:
    blocks = []
    if summary:
        blocks.append({"type": "text", "text": f"<conversation_summary>\n{summary}\n</conversation_summary>"})
    blocks.append({"type": "text", "text": f"<memory>{memory_digest}</memory>"})
    blocks.append({"type": "text", "text": user_text})
    log(F, f"built user turn: memory={len(memory_digest)} chars, summary={'yes' if summary else 'no'}, "
           f"text={len(user_text)} chars")
    return {"role": "user", "content": blocks}
