"""Builds the API-vs-SDK tables in REPORT.md from results/api.json and results/sdk.json.

    python compare.py

Rewrites only the part of REPORT.md between the TABLES markers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from shared.runner import PARTS  # noqa: E402

START, END = "<!-- TABLES:START -->", "<!-- TABLES:END -->"


def load(name: str) -> dict | None:
    p = ROOT / "results" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cell(r: dict | None, fn) -> str:
    return fn(r) if r else "לא הורץ עדיין"


def build() -> str:
    api, sdk = load("api"), load("sdk")
    t = lambda r: r["totals"]  # noqa: E731
    rows = [
        ("input (לא מ-cache)", lambda r: f"{t(r)['input_tokens']:,}"),
        ("cache read", lambda r: f"{t(r)['cache_read_tokens']:,}"),
        ("cache write", lambda r: f"{t(r)['cache_write_tokens']:,}"),
        ("output", lambda r: f"{t(r)['output_tokens']:,}"),
        ("אחוז cache (read מתוך כל ה-input)", lambda r: f"{t(r)['cache_hit_pct']}%"),
        ("קריאות למודל", lambda r: str(t(r)["model_calls"])),
        ("עלות כוללת", lambda r: f"${t(r)['cost_usd']:.4f}"),
        ("זמן כולל", lambda r: f"{t(r)['seconds']}s"),
        ("בדיקות שעברו", lambda r: r["checks_passed"]),
    ]
    out = ["### API מול SDK (כל התרחיש, 7 פניות, 2 סשנים)", "",
           "| מדד | API | SDK |", "|---|---|---|"]
    out += [f"| {name} | {cell(api, fn)} | {cell(sdk, fn)} |" for name, fn in rows]

    out += ["", "### לפי תור", "", "| תור | API in/read/write/out | API קריאות | API כלים | API עלות | "
            "SDK in/read/write/out | SDK קריאות | SDK כלים | SDK עלות |", "|---|---|---|---|---|---|---|---|---|"]
    n = len((api or sdk or {"turns": []})["turns"])
    for i in range(n):
        def side(r):
            if not r:
                return ["-"] * 4
            x = r["turns"][i]
            return [f"{x['input_tokens']}/{x['cache_read_tokens']}/{x['cache_write_tokens']}/{x['output_tokens']}",
                    str(x["model_calls"]), ", ".join(x["tools"]) or "-", f"${x['cost_usd']:.4f}"]
        ref = (api or sdk)["turns"][i]
        out.append(f"| s{ref['session']}t{ref['turn']} | " + " | ".join(side(api) + side(sdk)) + " |")

    out += ["", "### שורות קוד לכל חלק ב-harness", "",
            "API = שורות קוד (בלי הערות ושורות ריקות) ב-`API/harness/<part>.py`. "
            "SDK = שורות שמסומנות `# replaces: <part>` ב-`SDK/`.", "",
            "| חלק | API | SDK |", "|---|---|---|"]
    loc_a = (api or {}).get("loc") or _loc_api()
    loc_s = (sdk or {}).get("loc") or {}
    for p in PARTS:
        out.append(f"| {p} | {loc_a.get(p, '-')} | {loc_s.get(p, '-')} |")
    out.append(f"| **סה\"כ** | **{sum(loc_a.values())}** | **{sum(loc_s.values()) if loc_s else '-'}** |")

    out += ["", "### בדיקות", "", "| בדיקה | תיאור | API | SDK |", "|---|---|---|---|"]
    checks = (api or sdk or {"checks": []})["checks"]
    for i, c in enumerate(checks):
        mark = lambda r: ("✅" if r["checks"][i]["passed"] else "❌") if r else "-"  # noqa: E731
        out.append(f"| {c['id']} | {c['desc']} | {mark(api)} | {mark(sdk)} |")
    return "\n".join(out)


def _loc_api() -> dict:
    from shared.runner import loc_api
    return loc_api()


def main() -> None:
    report = ROOT / "REPORT.md"
    text = report.read_text(encoding="utf-8")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    report.write_text(f"{head}{START}\n{build()}\n{END}{tail}", encoding="utf-8")
    print("REPORT.md tables updated")


if __name__ == "__main__":
    main()
