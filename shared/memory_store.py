"""Long-term memory for ChefScout, stored as JSON on disk.

Both harnesses use this one store. The API harness decides which slice of it
goes into each turn (API/harness/memory.py + context.py). The SDK version
renders it to CLAUDE.md so that Claude Code loads it on its own.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Keys the agent may write. Single-value keys are replaced (and the old value is
# kept in history); list keys accumulate.
SINGLE_KEYS = {"diet", "household_size", "skill_level"}
LIST_KEYS = {"allergies", "dislikes", "favorites", "notes"}
ALL_KEYS = sorted(SINGLE_KEYS | LIST_KEYS)
DIETS = ["omnivore", "vegetarian", "vegan", "pescatarian"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class MemoryError_(ValueError):
    """Bad memory write. Shown to the model as a tool error."""


class MemoryStore:
    def __init__(self, state_dir: str | Path):
        self.path = Path(state_dir) / "memory.json"
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"facts": {}, "history": []}

    def reload(self) -> None:
        self.data = self._load()

    def _save(self) -> None:
        write_json_atomic(self.path, self.data)

    # ---- writes -------------------------------------------------------------
    def save(self, key: str, value: str, remove: bool = False) -> str:
        key = (key or "").strip().lower()
        value = (value or "").strip().lower()
        if key not in ALL_KEYS:
            raise MemoryError_(f"unknown key '{key}'. allowed: {', '.join(ALL_KEYS)}")
        if not value:
            raise MemoryError_("value must not be empty")
        if key == "diet" and value not in DIETS:
            raise MemoryError_(f"diet must be one of {DIETS}")
        facts = self.data["facts"]
        old = facts.get(key)
        if key in SINGLE_KEYS:
            if old == value:
                return f"unchanged {key}={value}"
            facts[key] = value
            self.data["history"].append({"at": _now(), "key": key, "old": old, "new": value})
            self._save()
            return f"saved {key}: {old or '-'} -> {value}"
        items = list(old or [])
        if remove:
            if value not in items:
                return f"'{value}' not in {key}"
            items.remove(value)
            self.data["history"].append({"at": _now(), "key": key, "removed": value})
        else:
            if value in items:
                return f"already in {key}: {value}"
            items.append(value)
            self.data["history"].append({"at": _now(), "key": key, "added": value})
        facts[key] = items
        self._save()
        return f"{key} now: {', '.join(items) or '-'}"

    # ---- reads --------------------------------------------------------------
    def facts(self) -> dict:
        return dict(self.data["facts"])

    def get(self, key: str, default=None):
        return self.data["facts"].get(key, default)

    def history(self) -> list[dict]:
        return list(self.data["history"])

    def compact(self, keys: list[str] | None = None) -> str:
        """One line per fact, e.g. 'diet=vegetarian; allergies=peanuts'."""
        facts = self.data["facts"]
        keys = keys if keys is not None else sorted(facts)
        parts = []
        for k in keys:
            if k in facts and facts[k]:
                v = facts[k]
                parts.append(f"{k}={', '.join(v) if isinstance(v, list) else v}")
        return "; ".join(parts) if parts else "(empty)"

    def render_markdown(self) -> str:
        """Used by the SDK version: CLAUDE.md content."""
        lines = ["# ChefScout memory (auto-generated, do not edit)", ""]
        facts = self.data["facts"]
        if not facts:
            lines.append("No saved preferences yet.")
        for k in sorted(facts):
            v = facts[k]
            lines.append(f"- {k}: {', '.join(v) if isinstance(v, list) else v}")
        changes = [h for h in self.data["history"] if "old" in h and h["old"]]
        if changes:
            lines += ["", "## Changed decisions"]
            lines += [f"- {h['key']}: {h['old']} -> {h['new']} ({h['at'][:10]})" for h in changes[-5:]]
        return "\n".join(lines) + "\n"
