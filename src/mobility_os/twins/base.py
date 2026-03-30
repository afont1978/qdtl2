from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Literal

AssetType = Literal[
    "intersection",
    "road_corridor",
    "bus_corridor",
    "curb_zone",
    "risk_hotspot",
    "city_mobility_system",
]


@dataclass
class TwinBase:
    twin_id: str
    asset_type: AssetType
    name: str
    ts: str
    enabled: bool = True
    alarms: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> Dict[str, Any]:
        return asdict(self)

    def step(self, dt_h: float, context: Dict[str, Any]) -> None:
        raise NotImplementedError

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        raise NotImplementedError

    def get_constraints(self) -> Dict[str, Any]:
        return {}

    def get_kpis(self) -> Dict[str, Any]:
        return {}
