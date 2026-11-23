"""Run the scenario on the API version.

    python API/main.py --scenario scenario.json --out results/api.json

Needs ANTHROPIC_API_KEY in the environment (never in code or git).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from API.agent import ApiAgent  # noqa: E402
from shared.runner import loc_api, run_scenario  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="scenario.json")
    ap.add_argument("--out", default="results/api.json")
    ap.add_argument("--state", default=str(ROOT / "state" / "api"))
    args = ap.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Set it in this terminal only, e.g. PowerShell: $env:ANTHROPIC_API_KEY='sk-ant-...'")
    state = Path(args.state)

    def make_agent(session_id: int, scenario: dict) -> ApiAgent:
        return ApiAgent(state, session_id, scenario["model"], scenario["effort"],
                        compaction_threshold=scenario.get("compaction_threshold_tokens", 20000))

    run_scenario("api", args.scenario, args.out, state, make_agent, loc_api())


if __name__ == "__main__":
    main()
