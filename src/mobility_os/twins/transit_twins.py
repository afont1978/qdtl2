from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np

from .base import TwinBase

@dataclass
class BusCorridorTwin(TwinBase):
    headway_real_s: float = 380.0
    headway_target_s: float = 360.0
    bunching_index: float = 0.22
    commercial_speed_kmh: float = 12.8
    occupancy_proxy: float = 0.58
    priority_requests_active: int = 0
    stops_pressure_index: float = 0.35
    priority_level: int = 1
    holding_strategy: int = 0
    dispatch_adjustment: int = 0

    def step(self, dt_h: float, context: Dict[str, Any]) -> None:
        bus_ops = context["bus_ops"]
        weather = context["weather"]
        events = context["active_events"]
        headway_pressure = float(bus_ops["headway_pressure"])
        priority_requests = int(bus_ops["priority_requests"])
        rain = float(weather["rain_intensity"])
        bunching_event = any(ev["event_type"] == "bus_bunching" for ev in events)
        incident_flag = any(ev["event_type"] == "incident" for ev in events)
        self.priority_requests_active = priority_requests
        control_gain = 0.08 * self.priority_level + 0.05 * self.holding_strategy + 0.04 * self.dispatch_adjustment
        self.bunching_index = float(np.clip(
            0.12 + 0.55 * headway_pressure + (0.15 if bunching_event else 0.0) + (0.10 if incident_flag else 0.0) - control_gain + np.random.normal(0, 0.015),
            0.0, 1.0
        ))
        self.headway_real_s = float(np.clip(self.headway_target_s * (1.0 + 0.75 * self.bunching_index), 220.0, 900.0))
        self.commercial_speed_kmh = float(np.clip(16.0 - 5.0 * self.bunching_index - 1.5 * rain + 0.9 * self.priority_level + np.random.normal(0, 0.2), 7.0, 18.0))
        self.occupancy_proxy = float(np.clip(0.45 + 0.35 * headway_pressure + 0.10 * self.bunching_index, 0.0, 1.0))
        self.stops_pressure_index = float(np.clip(0.20 + 0.55 * self.occupancy_proxy, 0.0, 1.0))

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        self.priority_level = int(dispatch.get("bus_priority_level", self.priority_level))
        self.holding_strategy = int(dispatch.get("holding_strategy", self.holding_strategy))
        self.dispatch_adjustment = int(dispatch.get("dispatch_adjustment", self.dispatch_adjustment))


