
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

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

    prev_pressure_score: Optional[float] = None
    connected_gateway_pressure: float = 0.0

    def step(self, dt_h: float, context: Dict[str, any]) -> None:
        curb_ops = context["curb_ops"]
        demand = context["demand"]
        events = context["active_events"]
        delivery_pressure = float(curb_ops["delivery_pressure"])
        illegal_pressure = float(curb_ops["illegal_parking_pressure"])
        pickup_dropoff = float(curb_ops["pickup_dropoff_pressure"])
        ped_flow = float(demand["ped_flow_pph"])
        illegal_event = any(ev["event_type"] == "illegal_curb_occupation" for ev in events)
        wave_event = any(ev["event_type"] == "delivery_wave" for ev in events)
        gateway_coupling = 0.15 * self.connected_gateway_pressure
        slot_effect = 0.10 * self.slot_allocation_mode
        enforcement_effect = 0.09 * self.enforcement_level
        access_effect = 0.07 * self.access_window_mode
        self.occupancy_rate = float(np.clip(0.42 + 0.55 * delivery_pressure + 0.15 * pickup_dropoff + (0.12 if wave_event else 0.0) + gateway_coupling - 0.06 * slot_effect, 0.0, 1.0))
        self.illegal_occupancy_rate = float(np.clip(0.05 + 0.45 * illegal_pressure + (0.18 if illegal_event else 0.0) - 0.08 * enforcement_effect, 0.0, 1.0))
        self.avg_dwell_time_min = float(np.clip(6.0 + 10.0 * self.occupancy_rate - 1.0 * access_effect, 3.0, 30.0))
        self.delivery_queue = float(np.clip(2.0 + 14.0 * delivery_pressure + 3.0 * self.occupancy_rate - 1.4 * slot_effect + 2.0 * gateway_coupling, 0.0, 40.0))
        self.pickup_dropoff_pressure = float(np.clip(pickup_dropoff, 0.0, 1.0))
        self.pedestrian_conflict_score = float(np.clip(0.08 + 0.28 * self.illegal_occupancy_rate + 0.20 * self.occupancy_rate + 0.00012 * ped_flow, 0.0, 1.0))

        pressure_score = float(np.clip(0.55 * self.occupancy_rate + 0.45 * self.illegal_occupancy_rate, 0.0, 1.0))
        self.pressure_level = self._pressure_label(pressure_score)
        self.trend_state = self._trend_from_values(pressure_score, self.prev_pressure_score, eps=0.02)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        self.operational_status = self._status_from_pressure(self.pressure_level, illegal_event)
        if self.enforcement_level >= 2 and self.slot_allocation_mode >= 2:
            self.action_active = "curb_enforcement_and_reallocation"
        elif self.enforcement_level >= 2:
            self.action_active = "curb_enforcement"
        elif self.slot_allocation_mode >= 2:
            self.action_active = "slot_reallocation"
        else:
            self.action_active = "none"
        self.prev_pressure_score = pressure_score

    def apply_dispatch(self, dispatch: Dict[str, any], dt_h: float) -> None:
        self.slot_allocation_mode = int(dispatch.get("curb_slot_policy", self.slot_allocation_mode))
        self.enforcement_level = int(dispatch.get("enforcement_level", self.enforcement_level))
        self.access_window_mode = int(dispatch.get("access_window_mode", self.access_window_mode))

    def get_kpis(self) -> Dict[str, any]:
        return {
            "occupancy_rate": self.occupancy_rate,
            "illegal_occupancy_rate": self.illegal_occupancy_rate,
            "delivery_queue": self.delivery_queue,
            "pressure_level": self.pressure_level,
            "trend_state": self.trend_state,
        }
