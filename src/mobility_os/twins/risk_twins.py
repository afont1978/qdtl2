from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np

from .base import TwinBase

@dataclass
class RiskHotspotTwin(TwinBase):
    risk_score: float = 0.34
    near_miss_index: float = 0.12
    pedestrian_exposure: float = 0.38
    bike_conflict_index: float = 0.20
    visibility_proxy: float = 0.92
    weather_modifier: float = 0.0
    motorcycle_risk_proxy: float = 0.18
    preventive_alert_level: int = 0
    speed_mitigation_request: int = 0
    signal_safety_mode: int = 0

    def step(self, dt_h: float, context: Dict[str, Any]) -> None:
        weather = context["weather"]
        demand = context["demand"]
        events = context["active_events"]
        ped_flow = float(demand["ped_flow_pph"])
        bike_flow = float(demand["bike_flow_pph"])
        rain = float(weather["rain_intensity"])
        visibility = float(weather["visibility"])
        school_flag = any(ev["event_type"] == "school_peak" for ev in events)
        incident_flag = any(ev["event_type"] == "incident" for ev in events)
        self.visibility_proxy = visibility
        self.weather_modifier = rain
        self.pedestrian_exposure = float(np.clip(0.15 + ped_flow / 2500.0 + (0.18 if school_flag else 0.0), 0.0, 1.0))
        self.bike_conflict_index = float(np.clip(0.08 + bike_flow / 2200.0 + 0.12 * rain, 0.0, 1.0))
        self.motorcycle_risk_proxy = float(np.clip(0.08 + 0.14 * rain + 0.10 * incident_flag, 0.0, 1.0))
        mitigation = 0.08 * self.preventive_alert_level + 0.10 * self.speed_mitigation_request + 0.10 * self.signal_safety_mode
        self.near_miss_index = float(np.clip(0.04 + 0.18 * self.pedestrian_exposure + 0.12 * self.bike_conflict_index + 0.10 * rain + 0.05 * incident_flag - mitigation, 0.0, 1.0))
        self.risk_score = float(np.clip(0.10 + 0.45 * self.near_miss_index + 0.20 * self.pedestrian_exposure + 0.14 * self.bike_conflict_index + 0.08 * self.motorcycle_risk_proxy, 0.0, 1.0))

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        self.preventive_alert_level = int(dispatch.get("preventive_alert_level", self.preventive_alert_level))
        self.speed_mitigation_request = int(dispatch.get("speed_mitigation_mode", self.speed_mitigation_request))
        self.signal_safety_mode = int(dispatch.get("ped_protection_mode", self.signal_safety_mode))


