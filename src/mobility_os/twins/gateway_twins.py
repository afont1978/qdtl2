
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from .base import TwinBase

@dataclass
class GatewayClusterTwin(TwinBase):
    access_pressure: float = 0.0
    delay_index: float = 0.0
    surge_factor: float = 0.0
    metering_mode: int = 0
    staging_mode: int = 0

    prev_delay_index: Optional[float] = None

    def step(self, dt_h: float, context: Dict[str, any]) -> None:
        self.prev_delay_index = self.delay_index
        gateway_ops = context.get("gateway_ops", {})
        events = context.get("active_events", [])
        incident_flag = any(ev["event_type"] == "incident" for ev in events)
        surge_event = any(ev["event_type"] == "gateway_surge" for ev in events)
        self.surge_factor = float(gateway_ops.get("surge_factor", 0.0))
        mitigation = 0.08 * self.metering_mode + 0.06 * self.staging_mode
        self.access_pressure = float(np.clip(0.20 + 0.75 * self.surge_factor + (0.15 if surge_event else 0.0), 0.0, 1.0))
        self.delay_index = float(np.clip(0.15 + 0.85 * self.access_pressure + (0.10 if incident_flag else 0.0) - mitigation, 0.0, 1.0))
        self.pressure_level = self._pressure_label(self.delay_index)
        self.trend_state = self._trend_from_values(self.delay_index, self.prev_delay_index, eps=0.02)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        self.operational_status = self._status_from_pressure(self.pressure_level, incident_flag)
        if self.metering_mode and self.staging_mode:
            self.action_active = "gateway_metering_and_staging"
        elif self.metering_mode:
            self.action_active = "gateway_metering"
        elif self.staging_mode:
            self.action_active = "gateway_staging"
        else:
            self.action_active = "none"

    def apply_dispatch(self, dispatch: Dict[str, any], dt_h: float) -> None:
        self.metering_mode = int(dispatch.get("gateway_metering_mode", self.metering_mode))
        self.staging_mode = int(dispatch.get("gateway_staging_mode", self.staging_mode))

    def get_kpis(self) -> Dict[str, any]:
        return {
            "delay_index": self.delay_index,
            "access_pressure": self.access_pressure,
            "pressure_level": self.pressure_level,
            "trend_state": self.trend_state,
        }
