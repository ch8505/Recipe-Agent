"""Pass/fail checks from scenario.json. Most of them read the saved state on disk."""
from __future__ import annotations

import json
from pathlib import Path

from shared.memory_store import MemoryStore


def _turn(turns: list[dict], ref: str) -> dict | None:
    # ref looks like "s2t1" (session 2, turn 1)
    for t in turns:
        if f"s{t['session']}t{t['turn']}" == ref:
            return t
    return None


def _as_text(v) -> str:
    return ", ".join(v) if isinstance(v, list) else str(v or "")


def run_check(check: dict, state_dir: Path, turns: list[dict]) -> tuple[bool, str]:
    kind = check["type"]
    mem = MemoryStore(state_dir)
    if kind == "memory_equals":
        got = mem.get(check["key"])
        return got == check["value"], f"{check['key']}={got!r}"
    if kind == "memory_contains":
        got = _as_text(mem.get(check["key"])).lower()
        return check["value"].lower() in got, f"{check['key']}={got!r}"
    if kind == "memory_changed":
        hist = [h for h in mem.history() if h.get("key") == check["key"] and "old" in h]
        ok = any(h["old"] == check["old"] and h["new"] == check["new"] for h in hist)
        return ok, "history: " + "; ".join(f"{h['old']}->{h['new']}" for h in hist)
    if kind == "shopping_contains":
        path = state_dir / "shopping_list.json"
        items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        missing = [v for v in check["values"] if v.lower() not in items]
        return not missing, f"{len(items)} items, missing={missing}"
    if kind == "tool_called":
        t = _turn(turns, check["turn"])
        tools = t["tools"] if t else []
        return check["tool"] in tools, f"tools={tools}"
    if kind in ("answer_contains", "answer_not_contains"):
        t = _turn(turns, check["turn"])
        text = (t or {}).get("answer", "").lower()
        hits = [v for v in check["values"] if v.lower() in text]
        if kind == "answer_contains":
            return len(hits) == len(check["values"]), f"found={hits}"
        return not hits, f"forbidden found={hits}"
    return False, f"unknown check type {kind}"


def run_checks(checks: list[dict], state_dir: Path, turns: list[dict]) -> list[dict]:
    out = []
    for c in checks:
        try:
            ok, detail = run_check(c, Path(state_dir), turns)
        except Exception as e:  # a broken check fails, it does not crash the run
            ok, detail = False, f"error: {e}"
        out.append({"id": c["id"], "desc": c.get("desc", ""), "passed": ok, "detail": detail})
    return out
