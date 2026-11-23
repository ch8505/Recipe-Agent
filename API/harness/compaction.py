"""Context window management: past a token threshold, summarize the whole conversation.

Runs at the start of a turn, before the new user message is added. The summary
replaces all earlier messages (history.py keeps them on disk behind a marker)
and is placed in the next user message by context.py. Because no old assistant
message survives, no old thinking block is replayed into a changed prefix.
"""
from __future__ import annotations

import json

from API.harness import log

F = "compaction.py"

SUMMARY_PROMPT = ("Summarize this cooking-assistant conversation in at most 120 words for the assistant itself. "
                  "Keep: recipes discussed (with ids), what the user decided, open requests. Facts already saved to memory "
                  "do not need detail. Output only the summary.")


def estimate_tokens(messages: list[dict]) -> int:
    return len(json.dumps(messages, ensure_ascii=False)) // 4


def transcript(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        for b in m["content"]:
            t = b.get("type")
            if t == "text":
                lines.append(f"{m['role']}: {b['text']}")
            elif t == "tool_use":
                lines.append(f"assistant called {b['name']}({json.dumps(b.get('input'), ensure_ascii=False)})")
            elif t == "tool_result":
                c = b.get("content")
                c = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                lines.append(f"tool result: {c[:200]}")
    return "\n".join(lines)


class Compactor:
    def __init__(self, client, model: str, threshold_tokens: int):
        self.client = client
        self.model = model
        self.threshold = threshold_tokens

    def needed(self, messages: list[dict], last_context_tokens: int) -> bool:
        size = max(last_context_tokens, estimate_tokens(messages))
        over = bool(messages) and size > self.threshold
        log(F, f"context size ~{size} tokens, threshold {self.threshold} -> {'COMPACT' if over else 'ok'}")
        return over

    def summarize(self, messages: list[dict]):
        """Returns (summary_text, usage) so tokens.py can bill the extra call."""
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SUMMARY_PROMPT,
            messages=[{"role": "user", "content": transcript(messages)}],
            output_config={"effort": "low"},
        )
        summary = "".join(b.text for b in resp.content if b.type == "text").strip()
        log(F, f"summarized {len(messages)} messages into {len(summary)} chars")
        return summary, resp.usage
