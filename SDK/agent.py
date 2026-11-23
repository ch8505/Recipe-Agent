"""ChefScout on the Claude Agent SDK: Claude Code runs the harness, we configure it.

Lines marked "# replaces: <name>" stand in for API/harness/<name>.py.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage,
                              SystemMessage, TextBlock, ToolUseBlock)

from SDK.tools import SERVER, build_server, render_memory_file
from shared.prompt import SYSTEM_PROMPT
from shared.recipes import RecipeDomain

PREFIX = f"mcp__{SERVER}__"


class SdkAgent:
    def __init__(self, state_dir: Path, session_id: int, model: str, effort: str):
        self.model, self.effort = model, effort
        self.domain = RecipeDomain(state_dir)
        self.workspace = Path(state_dir) / "workspace"  # replaces: memory
        self.workspace.mkdir(parents=True, exist_ok=True)
        render_memory_file(self.domain, self.workspace)  # replaces: memory
        self.server, self.tool_names = build_server(self.domain, self.workspace)
        self.session_file = Path(state_dir) / "sessions" / f"session_{session_id}.json"  # replaces: history
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        saved = json.loads(self.session_file.read_text()) if self.session_file.exists() else {}  # replaces: history
        self.session_id = saved.get("session_id")  # replaces: history
        # total_cost_usd is cumulative over a resumed session, so keep the last value  # replaces: tokens
        self.cum_cost = saved.get("cum_cost_usd", 0.0)  # replaces: tokens
        print(f"[SDK/agent.py] session {session_id} ready, resume={self.session_id}")

    def options(self) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            model=self.model,
            effort=self.effort,
            system_prompt=SYSTEM_PROMPT,  # replaces: context
            mcp_servers={SERVER: self.server},  # replaces: tools
            tools=[],  # no built-in Claude Code tools  # replaces: tools
            allowed_tools=self.tool_names,  # replaces: tools
            strict_mcp_config=True,  # replaces: tools
            setting_sources=["project"],  # loads workspace/CLAUDE.md  # replaces: memory, context
            cwd=str(self.workspace),  # replaces: memory
            resume=self.session_id,  # replaces: history
            permission_mode="dontAsk",
            max_turns=12,  # replaces: loop
            # compaction and caching are automatic inside Claude Code  # replaces: compaction, caching
        )

    async def _ask(self, text: str) -> dict:
        answer, tools, calls = [], [], set()
        result: ResultMessage | None = None
        async with ClaudeSDKClient(options=self.options()) as client:  # replaces: loop
            await client.query(text)  # replaces: loop
            async for msg in client.receive_response():  # replaces: loop
                if isinstance(msg, SystemMessage) and msg.subtype == "init":
                    self.session_id = msg.data.get("session_id", self.session_id)  # replaces: history
                elif isinstance(msg, AssistantMessage):
                    calls.add(msg.message_id or id(msg))  # replaces: tokens
                    for b in msg.content:
                        if isinstance(b, ToolUseBlock):
                            tools.append(b.name.removeprefix(PREFIX))
                            print(f"[SDK/agent.py] tool call {b.name.removeprefix(PREFIX)}({b.input})")
                        elif isinstance(b, TextBlock):
                            answer.append(b.text)
                elif isinstance(msg, ResultMessage):
                    result = msg
        if result is not None:
            self.session_id = result.session_id or self.session_id
        cum = (result.total_cost_usd or 0.0) if result else self.cum_cost  # replaces: tokens
        turn_cost, self.cum_cost = max(cum - self.cum_cost, 0.0), cum  # replaces: tokens
        self.session_file.write_text(json.dumps({"session_id": self.session_id,  # replaces: history
                                                 "cum_cost_usd": self.cum_cost}))  # replaces: tokens
        u = (result.usage if result else None) or {}  # usage is per turn  # replaces: tokens
        return {
            "answer": (result.result if result and result.result else "\n".join(answer)).strip(),
            "tools": tools,
            "input_tokens": u.get("input_tokens", 0),  # replaces: tokens
            "cache_read_tokens": u.get("cache_read_input_tokens", 0),  # replaces: tokens
            "cache_write_tokens": u.get("cache_creation_input_tokens", 0),  # replaces: tokens
            "output_tokens": u.get("output_tokens", 0),  # replaces: tokens
            "model_calls": len(calls) or (result.num_turns if result else 0),  # replaces: tokens
            "cost_usd": round(turn_cost, 6),  # replaces: tokens
        }

    def ask(self, text: str) -> dict:
        r = asyncio.run(self._ask(text))
        print(f"[SDK/agent.py] usage in={r['input_tokens']} cache_read={r['cache_read_tokens']} "
              f"cache_write={r['cache_write_tokens']} out={r['output_tokens']} cost=${r['cost_usd']:.5f}")
        return r
