"""Conversation history on disk: an append-only JSONL file per session.

Each line is an event: {"type": "message", ...} or {"type": "compaction", ...}.
Nothing is ever rewritten. To rebuild the messages we replay the file and start
again after the last compaction marker.
"""
from __future__ import annotations

import json
from pathlib import Path

from API.harness import log

F = "history.py"


def to_dict(block) -> dict:
    """SDK content block -> plain JSON dict that the API accepts back."""
    if isinstance(block, dict):
        return block
    return block.model_dump(mode="json", exclude_none=True)


class History:
    def __init__(self, state_dir: Path, session_id: int):
        self.path = Path(state_dir) / "history" / f"session_{session_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, event: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def append_message(self, message: dict) -> None:
        self._append({"type": "message", "message": message})
        log(F, f"appended {message['role']} message ({len(message['content'])} block(s)) -> {self.path.name}")

    def append_compaction(self, summary: str, replaced: int) -> None:
        self._append({"type": "compaction", "summary": summary, "replaced_messages": replaced})
        log(F, f"appended compaction marker (replaced {replaced} messages)")

    def events(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def load(self) -> list[dict]:
        """Messages the model should see: everything after the last compaction marker."""
        messages: list[dict] = []
        for ev in self.events():
            if ev["type"] == "compaction":
                messages = []
            else:
                messages.append(ev["message"])
        log(F, f"loaded {len(messages)} messages from {self.path.name}")
        return messages
