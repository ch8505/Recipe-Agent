"""Token usage and cost per model call and per turn."""
from __future__ import annotations

from API.harness import log

F = "tokens.py"

# USD per 1M tokens, claude-opus-5-5 (cache write = 5-minute TTL, 1.25x input).
PRICES = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00},
}


def cost(model: str, inp: int, out: int, cache_read: int, cache_write: int) -> float:
    p = PRICES[model]
    return (inp * p["input"] + out * p["output"] + cache_read * p["cache_read"] + cache_write * p["cache_write"]) / 1e6


class TokenMeter:
    def __init__(self, model: str):
        self.model = model
        self.last_context_tokens = 0  # size of the latest request, used by compaction.py
        self.start_turn()

    def start_turn(self) -> None:
        self.turn = {"input_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0,
                     "output_tokens": 0, "model_calls": 0, "cost_usd": 0.0}

    def record(self, usage, label: str = "agent") -> None:
        inp = usage.input_tokens or 0
        out = usage.output_tokens or 0
        cr = getattr(usage, "cache_read_input_tokens", 0) or 0
        cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
        c = cost(self.model, inp, out, cr, cw)
        t = self.turn
        t["input_tokens"] += inp
        t["output_tokens"] += out
        t["cache_read_tokens"] += cr
        t["cache_write_tokens"] += cw
        t["model_calls"] += 1
        t["cost_usd"] = round(t["cost_usd"] + c, 6)
        if label == "agent":
            self.last_context_tokens = inp + cr + cw
        log(F, f"{label} call #{t['model_calls']}: in={inp} cache_read={cr} cache_write={cw} out={out} cost=${c:.5f}")

    def end_turn(self) -> dict:
        t = dict(self.turn)
        log(F, f"turn total: calls={t['model_calls']} in={t['input_tokens']} cache_read={t['cache_read_tokens']} "
               f"cache_write={t['cache_write_tokens']} out={t['output_tokens']} cost=${t['cost_usd']:.5f}")
        return t
