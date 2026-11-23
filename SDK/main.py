"""Run the scenario on the Agent SDK version.

    python SDK/main.py --scenario scenario.json --out results/sdk.json

Runs on your Claude Code login. ANTHROPIC_API_KEY must NOT be set, otherwise
billing moves to the key; we drop it from this process to be safe.
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

from SDK.agent import SdkAgent  # noqa: E402
from shared.runner import loc_sdk, run_scenario  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="scenario.json")
    ap.add_argument("--out", default="results/sdk.json")
    ap.add_argument("--state", default=str(ROOT / "state" / "sdk"))
    args = ap.parse_args()
    if os.environ.pop("ANTHROPIC_API_KEY", None):
        print("[SDK/main.py] ANTHROPIC_API_KEY was set; removed it so the run uses the Claude Code login")
    state = Path(args.state)

    def make_agent(session_id: int, scenario: dict) -> SdkAgent:
        return SdkAgent(state, session_id, scenario["model"], scenario["effort"])

    run_scenario("sdk", args.scenario, args.out, state, make_agent, loc_sdk())


if __name__ == "__main__":
    main()
