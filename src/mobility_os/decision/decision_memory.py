from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DecisionMemory:
    maxlen: int = 8
    recent_actions: List[Dict[str, Any]] = field(default_factory=list)

    def remember(self, payload: Dict[str, Any]) -> None:
        self.recent_actions.append(payload)
        self.recent_actions = self.recent_actions[-self.maxlen:]

    def latest_action(self) -> Dict[str, Any]:
        return self.recent_actions[-1] if self.recent_actions else {}

    def recent_similar_action(self, action: str) -> bool:
        return any(item.get("recommended_action") == action for item in self.recent_actions[-3:])
