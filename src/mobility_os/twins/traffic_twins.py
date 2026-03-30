
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from .base import TwinBase

@dataclass
class IntersectionTwin(TwinBase):
    queue_ns: float = 18.0
    queue_ew: float = 15.0
    avg_delay_s: float = 34.0
    phase_id: int = 0
    cycle_time_s: float = 90.0
    ped_wait_s: float = 24.0
    bus_priority_request: int = 0
    risk_score: float = 0.32
    throughput_vph: float = 3200.0
    phase_plan: int = 0
    offset_s: float = 0.0
    priority_mode: int = 1
    ped_protection_mode: int = 0

    prev_avg_delay_s: Optional[float] = None
    prev_queue_total: Optional[float] = None
    connected_corridor_pressure: float = 0.0

    def step(self, dt_h: float, context: Dict[str, Any]) -> None:
        self.prev_avg_delay_s = self.avg_delay_s
        self.prev_queue_total = self.queue_ns + self.queue_ew

        demand = context["demand"]
        weather = context["weather"]
        bus_ops = context["bus_ops"]
        events = context["active_events"]
        base_flow = float(demand["corridor_flow_vph"])
        ped_flow = float(demand["ped_flow_pph"])
        rain = float(weather["rain_intensity"])
        incident_flag = any(ev["event_type"] == "incident" for ev in events)
        school_flag = any(ev["event_type"] == "school_peak" for ev in events)
        priority_effect = 0.10 * self.priority_mode
        ped_protection_effect = 0.08 * self.ped_protection_mode
        incident_penalty = 0.35 if incident_flag else 0.0
        school_penalty = 0.15 if school_flag else 0.0
        network_coupling = 0.18 * self.connected_corridor_pressure
        queue_pressure = 0.0022 * base_flow + 0.10 * rain + incident_penalty + network_coupling - 0.12 * priority_effect
        self.queue_ns = max(3.0, self.queue_ns + np.random.normal(0, 1.2) + queue_pressure * 3.0 - 0.35 * self.offset_s / 10.0)
        self.queue_ew = max(3.0, self.queue_ew + np.random.normal(0, 1.1) + queue_pressure * 2.5)
        self.avg_delay_s = max(8.0, 12.0 + 1.4 * (self.queue_ns + self.queue_ew) + 0.02 * ped_flow + 12.0 * incident_penalty + 6.0 * network_coupling)
        self.ped_wait_s = max(5.0, 14.0 + 0.012 * ped_flow + 7.0 * ped_protection_effect + 8.0 * school_penalty)
        self.bus_priority_request = int(bus_ops["priority_requests"])
        self.throughput_vph = max(1200.0, base_flow * (0.82 + 0.04 * self.priority_mode - 0.03 * rain - 0.08 * incident_penalty))
        self.risk_score = float(np.clip(
            0.22 + 0.003 * self.avg_delay_s + 0.002 * self.ped_wait_s + 0.03 * rain + 0.10 * school_penalty - 0.04 * self.ped_protection_mode,
            0.0, 1.0
        ))

        pressure_score = float(np.clip((self.queue_ns + self.queue_ew) / 80.0 + self.avg_delay_s / 140.0, 0.0, 1.0))
        self.pressure_level = self._pressure_label(pressure_score)
        self.trend_state = self._trend_from_values(self.avg_delay_s, self.prev_avg_delay_s, eps=0.5)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        self.operational_status = self._status_from_pressure(self.pressure_level, incident_flag)
        if self.ped_protection_mode:
            self.action_active = "pedestrian_protection"
        elif self.priority_mode >= 2:
            self.action_active = "bus_priority"
        else:
            self.action_active = "none"

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        self.phase_plan = int(dispatch.get("signal_plan_id", self.phase_plan))
        self.offset_s = float(dispatch.get("offset_s", self.offset_s))
        self.priority_mode = int(dispatch.get("bus_priority_level", self.priority_mode))
        self.ped_protection_mode = int(dispatch.get("ped_protection_mode", self.ped_protection_mode))

    def get_kpis(self) -> Dict[str, Any]:
        return {
            "queue_total": self.queue_ns + self.queue_ew,
            "avg_delay_s": self.avg_delay_s,
            "risk_score": self.risk_score,
            "pressure_level": self.pressure_level,
            "trend_state": self.trend_state,
        }

@dataclass
class RoadCorridorTwin(TwinBase):
    avg_speed_kmh: float = 22.0
    travel_time_index: float = 1.35
    density_proxy: float = 0.55
    queue_spillback_risk: float = 0.18
    incident_state: bool = False
    emission_proxy: float = 0.42
    noise_proxy: float = 0.38
    signal_coordination_mode: int = 1
    diversion_mode: int = 0
    lane_priority_mode: int = 1

    prev_avg_speed_kmh: Optional[float] = None
    connected_gateway_pressure: float = 0.0

    def step(self, dt_h: float, context: Dict[str, Any]) -> None:
        self.prev_avg_speed_kmh = self.avg_speed_kmh
        demand = context["demand"]
        weather = context["weather"]
        events = context["active_events"]
        flow = float(demand["corridor_flow_vph"])
        rain = float(weather["rain_intensity"])
        incident_flag = any(ev["event_type"] == "incident" for ev in events)
        event_release = any(ev["event_type"] == "event_release" for ev in events)
        demand_spike = any(ev["event_type"] == "demand_spike" for ev in events)
        self.incident_state = incident_flag
        gateway_coupling = 0.25 * self.connected_gateway_pressure
        congestion_pressure = 0.00022 * flow + 0.28 * rain + (0.35 if incident_flag else 0.0) + (0.18 if demand_spike else 0.0) + (0.12 if event_release else 0.0) + gateway_coupling
        coordination_effect = 0.08 * self.signal_coordination_mode
        diversion_effect = 0.07 * self.diversion_mode
        lane_effect = 0.06 * self.lane_priority_mode
        self.avg_speed_kmh = float(np.clip(
            33.0 - 18.0 * congestion_pressure + 2.5 * coordination_effect + 1.8 * diversion_effect + 1.3 * lane_effect + np.random.normal(0, 0.8),
            6.0, 45.0
        ))
        self.travel_time_index = float(np.clip(40.0 / max(self.avg_speed_kmh, 1e-6), 0.8, 5.0))
        self.density_proxy = float(np.clip(0.25 + 0.9 * congestion_pressure, 0.0, 1.0))
        self.queue_spillback_risk = float(np.clip(0.15 + 0.85 * self.density_proxy - 0.06 * diversion_effect, 0.0, 1.0))
        self.emission_proxy = float(np.clip(0.25 + 0.7 * self.travel_time_index / 3.5, 0.0, 1.2))
        self.noise_proxy = float(np.clip(0.22 + 0.4 * self.density_proxy + 0.08 * flow / 6000.0, 0.0, 1.0))

        pressure_score = float(np.clip((1.0 - self.avg_speed_kmh / 35.0) + 0.45 * self.queue_spillback_risk, 0.0, 1.0))
        self.pressure_level = self._pressure_label(pressure_score)
        self.trend_state = self._trend_from_values(-self.avg_speed_kmh, -self.prev_avg_speed_kmh if self.prev_avg_speed_kmh is not None else None, eps=0.3)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        self.operational_status = self._status_from_pressure(self.pressure_level, incident_flag)
        if self.diversion_mode >= 1:
            self.action_active = "diversion_active"
        elif self.signal_coordination_mode >= 2:
            self.action_active = "corridor_coordination"
        else:
            self.action_active = "none"

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        self.signal_coordination_mode = int(dispatch.get("signal_coordination_mode", self.signal_coordination_mode))
        self.diversion_mode = int(dispatch.get("diversion_mode", self.diversion_mode))
        self.lane_priority_mode = int(dispatch.get("lane_priority_mode", self.lane_priority_mode))

    def get_kpis(self) -> Dict[str, Any]:
        return {
            "avg_speed_kmh": self.avg_speed_kmh,
            "travel_time_index": self.travel_time_index,
            "queue_spillback_risk": self.queue_spillback_risk,
            "pressure_level": self.pressure_level,
            "trend_state": self.trend_state,
        }
