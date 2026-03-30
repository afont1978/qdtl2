from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np

from .base import TwinBase

@dataclass
class CurbZoneTwin(TwinBase):
    occupancy_rate: float = 0.66
    illegal_occupancy_rate: float = 0.14
    avg_dwell_time_min: float = 11.5
    delivery_queue: float = 6.0
    pickup_dropoff_pressure: float = 0.32
    pedestrian_conflict_score: float = 0.20
    slot_allocation_mode: int = 1
    enforcement_level: int = 1
    access_window_mode: int = 1

    def step(self, dt_h: float, context: Dict[str, Any]) -> None:
        curb_ops = context["curb_ops"]
        demand = context["demand"]
        events = context["active_events"]
        delivery_pressure = float(curb_ops["delivery_pressure"])
        illegal_pressure = float(curb_ops["illegal_parking_pressure"])
        pickup_dropoff = float(curb_ops["pickup_dropoff_pressure"])
        ped_flow = float(demand["ped_flow_pph"])
        illegal_event = any(ev["event_type"] == "illegal_curb_occupation" for ev in events)
        wave_event = any(ev["event_type"] == "delivery_wave" for ev in events)
        slot_effect = 0.10 * self.slot_allocation_mode
        enforcement_effect = 0.09 * self.enforcement_level
        access_effect = 0.07 * self.access_window_mode
        self.occupancy_rate = float(np.clip(0.42 + 0.55 * delivery_pressure + 0.15 * pickup_dropoff + (0.12 if wave_event else 0.0) - 0.06 * slot_effect, 0.0, 1.0))
        self.illegal_occupancy_rate = float(np.clip(0.05 + 0.45 * illegal_pressure + (0.18 if illegal_event else 0.0) - 0.08 * enforcement_effect, 0.0, 1.0))
        self.avg_dwell_time_min = float(np.clip(6.0 + 10.0 * self.occupancy_rate - 1.0 * access_effect, 3.0, 30.0))
        self.delivery_queue = float(np.clip(2.0 + 14.0 * delivery_pressure + 3.0 * self.occupancy_rate - 1.4 * slot_effect, 0.0, 40.0))
        self.pickup_dropoff_pressure = float(np.clip(pickup_dropoff, 0.0, 1.0))
        self.pedestrian_conflict_score = float(np.clip(0.08 + 0.28 * self.illegal_occupancy_rate + 0.20 * self.occupancy_rate + 0.00012 * ped_flow, 0.0, 1.0))

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        self.slot_allocation_mode = int(dispatch.get("curb_slot_policy", self.slot_allocation_mode))
        self.enforcement_level = int(dispatch.get("enforcement_level", self.enforcement_level))
        self.access_window_mode = int(dispatch.get("access_window_mode", self.access_window_mode))


