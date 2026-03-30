from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .base import TwinBase


@dataclass
class GatewayClusterTwin(TwinBase):
    """Sprint 1 placeholder for future airport/port gateway clusters."""
    access_pressure: float = 0.0
    delay_index: float = 0.0

    def step(self, dt_h: float, context: Dict[str, Any]) -> None:
        pass

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        pass
