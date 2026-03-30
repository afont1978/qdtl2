from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from .base import TwinBase


@dataclass
class MetroStationTwin(TwinBase):
    station_name: str = "Plaça de Catalunya"
    line_ids: List[str] = None
    platform_crowding_index: float = 0.34
    entry_flow_ppm: float = 120.0
    exit_flow_ppm: float = 110.0
    transfer_pressure: float = 0.30
    access_pressure: float = 0.26
    service_status: str = "normal"
    prev_platform_crowding_index: Optional[float] = None
    connected_interchange_pressure: float = 0.0
    connected_gateway_pressure: float = 0.0

    def __post_init__(self):
        if self.line_ids is None:
            self.line_ids = ["L1", "L3"]

    def step(self, dt_h: float, context: Dict[str, any]) -> None:
        self.prev_platform_crowding_index = self.platform_crowding_index
        demand = context.get("demand", {})
        rail_ops = context.get("rail_ops", {})
        weather = context.get("weather", {})
        events = context.get("active_events", [])
        ped_flow = float(demand.get("ped_flow_pph", 500.0))
        rail_load = float(rail_ops.get("metro_load", 0.35))
        airport_pressure = float(rail_ops.get("airport_rail_pressure", 0.10))
        rain = float(weather.get("rain_intensity", 0.0))
        event_release = any(ev["event_type"] in {"event_release", "gateway_surge"} for ev in events)
        self.platform_crowding_index = float(np.clip(0.15 + 0.62 * rail_load + 0.00018 * ped_flow + 0.20 * self.connected_interchange_pressure + 0.12 * airport_pressure + 0.06 * rain + (0.10 if event_release else 0.0), 0.0, 1.0))
        self.entry_flow_ppm = float(np.clip(70 + 220 * rail_load + 60 * self.connected_interchange_pressure, 10, 600))
        self.exit_flow_ppm = float(np.clip(65 + 200 * rail_load + 40 * airport_pressure, 10, 600))
        self.transfer_pressure = float(np.clip(0.10 + 0.55 * self.connected_interchange_pressure + 0.22 * rail_load, 0.0, 1.0))
        self.access_pressure = float(np.clip(0.08 + 0.35 * rail_load + 0.18 * rain + 0.14 * self.connected_gateway_pressure, 0.0, 1.0))
        pressure_score = float(np.clip(0.55 * self.platform_crowding_index + 0.25 * self.transfer_pressure + 0.20 * self.access_pressure, 0.0, 1.0))
        self.pressure_level = self._pressure_label(pressure_score)
        self.trend_state = self._trend_from_values(self.platform_crowding_index, self.prev_platform_crowding_index, eps=0.02)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        incident = any(ev["event_type"] == "incident" for ev in events)
        self.operational_status = self._status_from_pressure(self.pressure_level, incident)
        self.action_active = "crowd_guidance" if self.pressure_level in {"high", "critical"} else "none"
        self.service_status = "degraded" if incident else "normal"

    def apply_dispatch(self, dispatch: Dict[str, any], dt_h: float) -> None:
        if dispatch.get("interchange_crowd_management", 0):
            self.action_active = "crowd_management_active"


@dataclass
class MetroLineTwin(TwinBase):
    line_id: str = "L1"
    headway_proxy: float = 4.0
    line_load_index: float = 0.36
    reliability_proxy: float = 0.86
    disruption_severity: float = 0.0
    interchange_dependency: float = 0.20
    prev_line_load_index: Optional[float] = None

    def step(self, dt_h: float, context: Dict[str, any]) -> None:
        self.prev_line_load_index = self.line_load_index
        rail_ops = context.get("rail_ops", {})
        events = context.get("active_events", [])
        line_base = float(rail_ops.get("metro_load", 0.35))
        interchange = float(rail_ops.get("interchange_pressure", 0.20))
        disruption = any(ev["event_type"] == "incident" for ev in events)
        self.line_load_index = float(np.clip(0.16 + 0.72 * line_base + 0.18 * interchange, 0.0, 1.0))
        self.headway_proxy = float(np.clip(2.8 + 2.4 * self.line_load_index, 2.0, 8.0))
        self.reliability_proxy = float(np.clip(0.95 - 0.25 * self.line_load_index - (0.18 if disruption else 0.0), 0.3, 1.0))
        self.disruption_severity = 0.45 if disruption else 0.0
        self.interchange_dependency = interchange
        pressure_score = float(np.clip(self.line_load_index + (1 - self.reliability_proxy) * 0.5, 0.0, 1.0))
        self.pressure_level = self._pressure_label(pressure_score)
        self.trend_state = self._trend_from_values(self.line_load_index, self.prev_line_load_index, eps=0.02)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        self.operational_status = self._status_from_pressure(self.pressure_level, disruption)
        self.action_active = "frequency_rebalancing" if self.pressure_level in {"high", "critical"} else "none"

    def apply_dispatch(self, dispatch: Dict[str, any], dt_h: float) -> None:
        pass


@dataclass
class RodaliesStationTwin(TwinBase):
    station_name: str = "Sants Estació"
    line_ids: List[str] = None
    platform_pressure: float = 0.30
    access_delay_index: float = 0.22
    interchange_pressure: float = 0.28
    regional_load_index: float = 0.34
    service_status: str = "normal"
    prev_platform_pressure: Optional[float] = None
    connected_gateway_pressure: float = 0.0

    def __post_init__(self):
        if self.line_ids is None:
            self.line_ids = ["R1", "R2", "R4"]

    def step(self, dt_h: float, context: Dict[str, any]) -> None:
        self.prev_platform_pressure = self.platform_pressure
        rail_ops = context.get("rail_ops", {})
        events = context.get("active_events", [])
        load = float(rail_ops.get("rodalies_load", 0.32))
        interchange = float(rail_ops.get("interchange_pressure", 0.20))
        airport_branch = float(rail_ops.get("airport_rail_pressure", 0.10))
        disruption = any(ev["event_type"] in {"incident", "gateway_surge"} for ev in events)
        self.platform_pressure = float(np.clip(0.14 + 0.65 * load + 0.22 * interchange + 0.16 * self.connected_gateway_pressure, 0.0, 1.0))
        self.access_delay_index = float(np.clip(0.08 + 0.50 * self.platform_pressure + 0.18 * airport_branch, 0.0, 1.0))
        self.interchange_pressure = float(np.clip(0.10 + 0.62 * interchange + 0.10 * load, 0.0, 1.0))
        self.regional_load_index = float(np.clip(0.16 + 0.78 * load + 0.08 * airport_branch, 0.0, 1.0))
        pressure_score = float(np.clip(0.50 * self.platform_pressure + 0.25 * self.interchange_pressure + 0.25 * self.access_delay_index, 0.0, 1.0))
        self.pressure_level = self._pressure_label(pressure_score)
        self.trend_state = self._trend_from_values(self.platform_pressure, self.prev_platform_pressure, eps=0.02)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        self.operational_status = self._status_from_pressure(self.pressure_level, disruption)
        self.action_active = "platform_flow_control" if self.pressure_level in {"high", "critical"} else "none"
        self.service_status = "degraded" if disruption else "normal"

    def apply_dispatch(self, dispatch: Dict[str, any], dt_h: float) -> None:
        pass


@dataclass
class RodaliesLineTwin(TwinBase):
    line_id: str = "R2"
    line_load_index: float = 0.30
    reliability_proxy: float = 0.82
    disruption_severity: float = 0.0
    suburban_access_pressure: float = 0.24
    airport_branch_pressure: float = 0.20
    prev_line_load_index: Optional[float] = None

    def step(self, dt_h: float, context: Dict[str, any]) -> None:
        self.prev_line_load_index = self.line_load_index
        rail_ops = context.get("rail_ops", {})
        events = context.get("active_events", [])
        load = float(rail_ops.get("rodalies_load", 0.32))
        gateway = float(rail_ops.get("airport_rail_pressure", 0.10))
        disruption = any(ev["event_type"] in {"incident", "gateway_surge"} for ev in events)
        self.line_load_index = float(np.clip(0.12 + 0.80 * load + 0.18 * gateway, 0.0, 1.0))
        self.reliability_proxy = float(np.clip(0.93 - 0.28 * self.line_load_index - (0.20 if disruption else 0.0), 0.2, 1.0))
        self.disruption_severity = 0.50 if disruption else 0.0
        self.suburban_access_pressure = float(np.clip(0.10 + 0.65 * load, 0.0, 1.0))
        self.airport_branch_pressure = float(np.clip(0.10 + 0.75 * gateway, 0.0, 1.0))
        pressure_score = float(np.clip(self.line_load_index + (1 - self.reliability_proxy) * 0.5, 0.0, 1.0))
        self.pressure_level = self._pressure_label(pressure_score)
        self.trend_state = self._trend_from_values(self.line_load_index, self.prev_line_load_index, eps=0.02)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        self.operational_status = self._status_from_pressure(self.pressure_level, disruption)
        self.action_active = "rail_load_balancing" if self.pressure_level in {"high", "critical"} else "none"

    def apply_dispatch(self, dispatch: Dict[str, any], dt_h: float) -> None:
        pass


@dataclass
class FGCStationTwin(TwinBase):
    station_name: str = "Plaça d'Espanya"
    network_family: str = "Llobregat-Anoia"
    platform_pressure: float = 0.24
    transfer_pressure: float = 0.26
    access_pressure: float = 0.20
    service_status: str = "normal"
    prev_platform_pressure: Optional[float] = None

    def step(self, dt_h: float, context: Dict[str, any]) -> None:
        self.prev_platform_pressure = self.platform_pressure
        rail_ops = context.get("rail_ops", {})
        interchange = float(rail_ops.get("interchange_pressure", 0.20))
        fgc_load = float(rail_ops.get("fgc_load", 0.26))
        events = context.get("active_events", [])
        event_release = any(ev["event_type"] == "event_release" for ev in events)
        self.platform_pressure = float(np.clip(0.10 + 0.72 * fgc_load + 0.18 * interchange + (0.08 if event_release else 0.0), 0.0, 1.0))
        self.transfer_pressure = float(np.clip(0.08 + 0.62 * interchange + 0.12 * fgc_load, 0.0, 1.0))
        self.access_pressure = float(np.clip(0.06 + 0.40 * fgc_load, 0.0, 1.0))
        pressure_score = float(np.clip(0.55 * self.platform_pressure + 0.25 * self.transfer_pressure + 0.20 * self.access_pressure, 0.0, 1.0))
        self.pressure_level = self._pressure_label(pressure_score)
        self.trend_state = self._trend_from_values(self.platform_pressure, self.prev_platform_pressure, eps=0.02)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        self.operational_status = self._status_from_pressure(self.pressure_level, False)
        self.action_active = "fgc_guidance" if self.pressure_level in {"high", "critical"} else "none"

    def apply_dispatch(self, dispatch: Dict[str, any], dt_h: float) -> None:
        pass


@dataclass
class FGCLineTwin(TwinBase):
    line_id: str = "L8"
    network_family: str = "Llobregat-Anoia"
    line_load_index: float = 0.24
    frequency_proxy: float = 7.0
    reliability_proxy: float = 0.88
    disruption_severity: float = 0.0
    prev_line_load_index: Optional[float] = None

    def step(self, dt_h: float, context: Dict[str, any]) -> None:
        self.prev_line_load_index = self.line_load_index
        rail_ops = context.get("rail_ops", {})
        fgc_load = float(rail_ops.get("fgc_load", 0.26))
        events = context.get("active_events", [])
        self.line_load_index = float(np.clip(0.10 + 0.82 * fgc_load, 0.0, 1.0))
        self.frequency_proxy = float(np.clip(4.0 + 5.0 * self.line_load_index, 3.0, 12.0))
        disruption = any(ev["event_type"] == "incident" for ev in events)
        self.reliability_proxy = float(np.clip(0.95 - 0.18 * self.line_load_index - (0.10 if disruption else 0.0), 0.3, 1.0))
        self.disruption_severity = 0.35 if disruption else 0.0
        pressure_score = float(np.clip(self.line_load_index + (1 - self.reliability_proxy) * 0.3, 0.0, 1.0))
        self.pressure_level = self._pressure_label(pressure_score)
        self.trend_state = self._trend_from_values(self.line_load_index, self.prev_line_load_index, eps=0.02)
        self.forecast_state = self._forecast_from_trend(self.trend_state, self.pressure_level)
        self.operational_status = self._status_from_pressure(self.pressure_level, disruption)
        self.action_active = "fgc_frequency_shift" if self.pressure_level in {"high", "critical"} else "none"

    def apply_dispatch(self, dispatch: Dict[str, any], dt_h: float) -> None:
        pass
