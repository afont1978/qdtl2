
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

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

    prev_risk_score: Optional[float] = None
    connected_curb_conflict: float = 0.0
    connected_intersection_risk: float = 0.0

    def step(self, dt_h: float, context: Dict[str, any]) -> None:
        self.prev_risk_score = self.risk_score
        weather = context["weather"]
        demand = context["demand"]
        events = context["active_events"]
        ped_flow = float(demand["ped_flow_pph"])
        bike_flow = float(demand["bike_flow_pph"])
        rain = float(weather["rain_intensity"])
        visibility = float(weather["visibility"])
        school_flag = any(ev["event_type"] == "school_peak" for ev in events)
        incident_flag = any(ev["event_type"] == "incident" for ev in events)
        curb_coupling = 0.20 * self.connected_curb_conflict
        intersection_coupling = 0.20 * self.connected_intersection_risk

        self.visibility_proxy = visibility
        self.weather_modifier = rain
        self.pedestrian_exposure = float(np.clip(0.15 + ped_flow / 2500.0 + (0.18 if school_flag else 0.0), 0.0, 1.0))
        self.bike_conflict_index = float(np.clip(0.08 + bike_flow / 2200.0 + 0.12 * rain + 0.08 * curb_coupling, 0.0, 1.0))
        self.motorcycle_risk_proxy = float(np.clip(0.08 + 0.14 * rain + 0.10 * incident_flag, 0.0, 1.0))
        mitigation = 0.08 * self.preventive_alert_level + 0.10 * self.speed_mitigation_request + 0.10 * self.signal_safety_mode
        self.near_miss_index = float(np.clip(0.04 + 0.18 * self.pedestrian_exposure + 0.12 * self.bike_conflict_index + 0.10 * rain + 0.05 * incident_flag + 0.06 * intersection_coupling - mitigation, 0.0, 1.0))
        self.risk_score = float(np.clip(0.10 + 0.45 * self.near_miss_index + 0.20 * self.pedestrian_exposure + 0.14 * self.bike_conflict_index + 0.08 * self.motorcycle_risk_proxy + 0.08 * curb_coupling, 0.0, 1.0))

        self.pressure_level = self._pressure_label(self.risk_score)
        self.trend_state = self._trend_from_values(self.risk_score, self.prev_risk_score, eps=0.02)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        self.operational_status = self._status_from_pressure(self.pressure_level, incident_flag or self.risk_score > 0.75)
        if self.preventive_alert_level >= 2:
            self.action_active = "preventive_alert"
        elif self.speed_mitigation_request:
            self.action_active = "speed_mitigation"
        elif self.signal_safety_mode:
            self.action_active = "signal_safety_mode"
        else:
            self.action_active = "none"

    def apply_dispatch(self, dispatch: Dict[str, any], dt_h: float) -> None:
        self.preventive_alert_level = int(dispatch.get("preventive_alert_level", self.preventive_alert_level))
        self.speed_mitigation_request = int(dispatch.get("speed_mitigation_mode", self.speed_mitigation_request))
        self.signal_safety_mode = int(dispatch.get("ped_protection_mode", self.signal_safety_mode))

    def get_kpis(self) -> Dict[str, any]:
        return {
            "risk_score": self.risk_score,
            "near_miss_index": self.near_miss_index,
            "pedestrian_exposure": self.pedestrian_exposure,
            "pressure_level": self.pressure_level,
            "trend_state": self.trend_state,
        }
