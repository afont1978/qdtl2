from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from .base import TwinBase


@dataclass
class InterchangeNodeTwin(TwinBase):
    node_name: str = "Sants Estació"
    connected_modes: List[str] = None
    transfer_pressure: float = 0.34
    pedestrian_pressure: float = 0.30
    curb_pressure: float = 0.24
    bus_pressure: float = 0.28
    rail_pressure: float = 0.36
    overall_interchange_load: float = 0.34
    risk_score: float = 0.22
    prev_overall_interchange_load: Optional[float] = None
    connected_corridor_pressure: float = 0.0
    connected_gateway_pressure: float = 0.0

    def __post_init__(self):
        if self.connected_modes is None:
            self.connected_modes = ["metro", "rodalies", "fgc", "bus", "road", "curb"]

    def step(self, dt_h: float, context: Dict[str, any]) -> None:
        self.prev_overall_interchange_load = self.overall_interchange_load
        demand = context.get("demand", {})
        bus_ops = context.get("bus_ops", {})
        rail_ops = context.get("rail_ops", {})
        curb_ops = context.get("curb_ops", {})
        weather = context.get("weather", {})
        events = context.get("active_events", [])
        ped = float(demand.get("ped_flow_pph", 500.0))
        bus_pressure = float(bus_ops.get("headway_pressure", 0.3))
        rail_pressure = float(0.40 * rail_ops.get("metro_load", 0.3) + 0.35 * rail_ops.get("rodalies_load", 0.25) + 0.25 * rail_ops.get("fgc_load", 0.2))
        curb_pressure = float(0.55 * curb_ops.get("delivery_pressure", 0.25) + 0.45 * curb_ops.get("pickup_dropoff_pressure", 0.2))
        rain = float(weather.get("rain_intensity", 0.0))
        event_release = any(ev["event_type"] == "event_release" for ev in events)
        gateway = any(ev["event_type"] == "gateway_surge" for ev in events)
        self.transfer_pressure = float(np.clip(0.10 + 0.65 * rail_ops.get("interchange_pressure", 0.25) + 0.18 * rail_pressure + 0.08 * self.connected_corridor_pressure, 0.0, 1.0))
        self.pedestrian_pressure = float(np.clip(0.08 + 0.00020 * ped + 0.12 * rain + (0.12 if event_release else 0.0), 0.0, 1.0))
        self.curb_pressure = float(np.clip(0.10 + curb_pressure + 0.12 * self.connected_gateway_pressure, 0.0, 1.0))
        self.bus_pressure = float(np.clip(0.10 + 0.75 * bus_pressure + 0.10 * self.connected_corridor_pressure, 0.0, 1.0))
        self.rail_pressure = float(np.clip(0.10 + 0.85 * rail_pressure + (0.10 if gateway else 0.0), 0.0, 1.0))
        self.overall_interchange_load = float(np.clip(0.25 * self.transfer_pressure + 0.20 * self.pedestrian_pressure + 0.15 * self.curb_pressure + 0.15 * self.bus_pressure + 0.25 * self.rail_pressure, 0.0, 1.0))
        self.risk_score = float(np.clip(0.08 + 0.35 * self.pedestrian_pressure + 0.20 * self.curb_pressure + 0.20 * self.bus_pressure + 0.17 * self.rail_pressure, 0.0, 1.0))
        self.pressure_level = self._pressure_label(self.overall_interchange_load)
        self.trend_state = self._trend_from_values(self.overall_interchange_load, self.prev_overall_interchange_load, eps=0.02)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        self.operational_status = self._status_from_pressure(self.pressure_level, False)
        self.action_active = "interchange_crowd_management" if self.pressure_level in {"high", "critical"} else "none"

    def apply_dispatch(self, dispatch: Dict[str, any], dt_h: float) -> None:
        if dispatch.get("interchange_crowd_management", 0):
            self.action_active = "interchange_crowd_management"
