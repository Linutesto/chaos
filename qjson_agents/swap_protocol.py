from __future__ import annotations

from typing import Any, Dict

from .agent import Agent


class PersonaSwapper:
    def __init__(self, agent: Agent):
        self.agent = agent

    def swap(self, new_manifest: Dict[str, Any], *, cause: str = "manual") -> None:
        self.agent.swap_persona(new_manifest, cause=cause)

    def evolve(self, *, adopt: bool = True) -> Dict[str, Any]:
        return self.agent.mutate_self(adopt=adopt)

