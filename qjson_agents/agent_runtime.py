from __future__ import annotations

from typing import Any, Dict

from .agent import Agent
from .fmm_core import FractalMemory


class AgentRuntime:
    def __init__(self):
        self.active_agent: Agent | None = None
        self.memory = FractalMemory()

    def load_agent(self, manifest: Dict[str, Any]) -> None:
        self.active_agent = Agent(manifest)

    def run(self, input_data: str) -> str:
        if not self.active_agent:
            raise RuntimeError("No active agent loaded")
        out = self.active_agent.chat_turn(input_data)
        self.memory.insert(self.active_agent.agent_id.split(), out)
        return out

