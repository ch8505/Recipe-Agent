"""Runs scenario.json against any agent and writes the results file.

Both main.py files call run_scenario(), so the two result files have the same
shape and the comparison is fair. An agent only needs ask(text) -> dict.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Callable

from shared.checks import run_checks

ROOT = Path(__file__).resolve().parent.parent
PARTS = ["loop", "tools", "history", "memory", "context", "compaction", "caching", "tokens"]
TURN_KEYS = ["input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens", "model_calls", "cost_usd"]


def _code_lines(path: Path) -> int:
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            n += 1
    return n


def loc_api() -> dict:
    return {p: _code_lines(ROOT / "API" / "harness" / f"{p}.py") for p in PARTS}


def loc_sdk() -> dict:
    counts = {p: 0 for p in PARTS}
    for f in (ROOT / "SDK").glob("*.py"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if "# replaces:" in line:
                for name in line.split("# replaces:")[1].split(","):
                    name = name.strip().split()[0] if name.strip() else ""
                    if name in counts:
                        counts[name] += 1
    return counts


def run_scenario(harness: str, scenario_path: str, out_path: str, state_dir: Path,
                 make_agent: Callable[[int, dict], object], loc: dict) -> dict:
    scenario = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
    if state_dir.exists():  # every run starts from a clean state
        shutil.rmtree(state_dir)
    state_dir.mkdir(parents=True)
    turns: list[dict] = []
    for session in scenario["sessions"]:
        sid = session["id"]
        print(f"\n===== [{harness}] session {sid}: new agent instance, state loaded from disk =====")
        agent = make_agent(sid, scenario)
        for i, prompt in enumerate(session["turns"], 1):
            print(f"\n--- s{sid}t{i} USER: {prompt}")
            t0 = time.perf_counter()
            r = agent.ask(prompt)
            r["seconds"] = round(time.perf_counter() - t0, 2)
            row = {"session": sid, "turn": i, "prompt": prompt, **r}
            turns.append(row)
            print(f"--- s{sid}t{i} AGENT: {r['answer']}")
            print(f"--- s{sid}t{i} in={r['input_tokens']} cache_read={r['cache_read_tokens']} "
                  f"cache_write={r['cache_write_tokens']} out={r['output_tokens']} calls={r['model_calls']} "
                  f"tools={r['tools']} cost=${r['cost_usd']:.4f} time={r['seconds']}s")
        close = getattr(agent, "close", None)
        if close:
            close()
    checks = run_checks(scenario["checks"], state_dir, turns)
    totals = {k: round(sum(t[k] for t in turns), 6) for k in TURN_KEYS}
    total_in = totals["input_tokens"] + totals["cache_read_tokens"] + totals["cache_write_tokens"]
    totals["cache_hit_pct"] = round(100 * totals["cache_read_tokens"] / total_in, 1) if total_in else 0.0
    totals["seconds"] = round(sum(t["seconds"] for t in turns), 2)
    result = {
        "harness": harness,
        "model": scenario["model"],
        "effort": scenario["effort"],
        "turns": turns,
        "totals": totals,
        "checks": checks,
        "checks_passed": f"{sum(c['passed'] for c in checks)}/{len(checks)}",
        "loc": loc,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n===== [{harness}] checks {result['checks_passed']} | total cost ${totals['cost_usd']:.4f} | wrote {out_path}")
    for c in checks:
        print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['id']}: {c['desc']} ({c['detail']})")
    return result
