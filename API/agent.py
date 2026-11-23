"""ChefScout on the raw Messages API: wires the harness parts together."""
from __future__ import annotations

from pathlib import Path

from API.harness import compaction, context, log, loop
from API.harness.history import History
from API.harness.memory import Memory
from API.harness.tokens import TokenMeter
from API.harness.tools import ToolRunner
from shared.recipes import RecipeDomain

F = "agent.py"


class ApiAgent:
    def __init__(self, state_dir: Path, session_id: int, model: str, effort: str,
                 compaction_threshold: int = 20000, client=None):
        if client is None:
            import anthropic  # imported here so offline tests never need a key
            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
        self.client = client
        self.model, self.effort = model, effort
        self.domain = RecipeDomain(state_dir)
        self.runner = ToolRunner(self.domain)
        self.memory = Memory(state_dir)
        self.history = History(state_dir, session_id)
        self.messages = self.history.load()  # resumes if this session already has history
        self.meter = TokenMeter(model)
        self.compactor = compaction.Compactor(client, model, compaction_threshold)
        self.system = context.system_blocks()
        log(F, f"session {session_id} ready: {len(self.messages)} messages restored, model={model}, effort={effort}")

    def ask(self, user_text: str) -> dict:
        self.meter.start_turn()
        summary = None
        if self.compactor.needed(self.messages, self.meter.last_context_tokens):
            summary, usage = self.compactor.summarize(self.messages)
            self.meter.record(usage, label="compaction")
            self.history.append_compaction(summary, len(self.messages))
            self.messages = []
            self.meter.last_context_tokens = 0
        user = context.user_turn(user_text, self.memory.relevant(user_text), summary)
        self.messages.append(user)
        self.history.append_message(user)
        answer, tools = loop.run_turn(self.client, self.model, self.effort, self.system, self.runner,
                                      self.messages, self.history, self.meter)
        return {"answer": answer, "tools": tools, **self.meter.end_turn()}
