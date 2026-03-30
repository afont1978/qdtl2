
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Literal, Optional

AssetType = Literal[
    "intersection",
    "road_corridor",
    "bus_corridor",
    "curb_zone",
    "risk_hotspot",
    "gateway_cluster",
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

    operational_status: str = "nominal"
    pressure_level: str = "low"
    trend_state: str = "stable"
    forecast_state: str = "stable"
    action_active: str = "none"

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

    def _trend_from_values(self, current: float, previous: Optional[float], eps: float = 0.01) -> str:
        if previous is None:
            return "stable"
        delta = current - previous
        if delta > eps:
            return "rising"
        if delta < -eps:
            return "falling"
        return "stable"

    def _pressure_label(self, score: float) -> str:
        if score >= 0.80:
            return "critical"
        if score >= 0.60:
            return "high"
        if score >= 0.35:
            return "medium"
        return "low"

    def _forecast_from_trend(self, trend: str, pressure_level: Optional[str] = None) -> str:
        if pressure_level == "critical":
            return "critical_escalation_risk"
        if trend == "rising":
            return "worsening"
        if trend == "falling":
            return "improving"
        return "stable"

    def _status_from_pressure(self, pressure_level: str, incident: bool = False) -> str:
        if incident:
            return "disrupted"
        if pressure_level == "critical":
            return "critical"
        if pressure_level == "high":
            return "stressed"
        if pressure_level == "medium":
            return "watch"
        return "nominal"
