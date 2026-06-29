"""Live roster — agents register / unregister mid-session."""
from __future__ import annotations

from typing import Optional


class Roster:
    def __init__(self, agents: Optional[list] = None) -> None:
        self._by_id: dict = {}
        for a in agents or []:
            self.add(a)

    def add(self, agent) -> None:
        self._by_id[agent.id] = agent

    def remove(self, agent_id: str) -> None:
        self._by_id.pop(agent_id, None)

    def get(self, agent_id: str):
        return self._by_id.get(agent_id)

    def by_role_or_id(self, key: str):
        if key in self._by_id:
            return self._by_id[key]
        for a in self._by_id.values():
            if a.role == key:
                return a
        return None

    def first(self):
        return next(iter(self._by_id.values()), None)

    def all(self) -> list:
        return list(self._by_id.values())
