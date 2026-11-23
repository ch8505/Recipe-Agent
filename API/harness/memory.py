"""Long-term memory: where it is stored and which part of it is retrieved.

Storage: state/<harness>/memory.json, through shared.memory_store (the
save_memory tool writes there). Retrieval: we never send the whole memory.
Safety facts (diet, allergies, dislikes) always go in, because a wrong recipe
is worse than a few tokens. Other keys go in only when the message is about them.
"""
from __future__ import annotations

import re
from pathlib import Path

from API.harness import log
from shared.memory_store import MemoryStore

F = "memory.py"
ALWAYS = ["diet", "allergies", "dislikes"]
TRIGGERS = {
    "favorites": r"favou?rite|again|usual|last time|loved|liked",
    "household_size": r"people|guests|family|servings|portion|kids",
    "skill_level": r"easy|beginner|hard|skill|advanced",
    "notes": r"remember|note|usual|always|never",
}


class Memory:
    def __init__(self, state_dir: Path):
        self.store = MemoryStore(state_dir)

    def relevant(self, user_text: str) -> str:
        self.store.reload()  # tools may have written since last turn
        facts = self.store.facts()
        text = user_text.lower()
        keys = [k for k in ALWAYS if k in facts]
        keys += [k for k, rx in TRIGGERS.items() if k in facts and re.search(rx, text)]
        skipped = [k for k in facts if k not in keys]
        digest = self.store.compact(keys) if keys else "(nothing saved yet)"
        changes = [h for h in self.store.history() if h.get("old") and h["key"] in keys]
        if changes:
            h = changes[-1]
            digest += f" | changed {h['key']}: {h['old']}->{h['new']}"
        log(F, f"retrieved keys={keys} skipped={skipped} -> {len(digest)} chars")
        return digest
