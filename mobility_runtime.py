from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import numpy as np
import pandas as pd

Mode = Literal["traffic", "safety", "logistics", "gateway", "event"]
ScenarioName = str
Route = Literal["CLASSICAL", "QUANTUM", "FALLBACK_CLASSICAL"]
AssetType = Literal[
    "intersection",
    "road_corridor",
    "bus_corridor",
    "curb_zone",
    "risk_hotspot",
    "city_mobility_system",
]
EventType = Literal[
    "demand_spike",
    "incident",
    "school_peak",
    "rain_event",
    "bus_bunching",
    "illegal_curb_occupation",
    "delivery_wave",
    "gateway_surge",
    "event_release",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Hotspot:
    name: str
    lat: float
    lon: float
    category: str
    streets: str
    why: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _default_hotspot_search_paths(explicit_path: Optional[str] = None) -> List[Path]:
    here = Path(__file__).resolve().parent
    candidates: List[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    candidates.extend([
        here / "barcelona_mobility_hotspots.csv",
        Path.cwd() / "barcelona_mobility_hotspots.csv",
    ])
    deduped: List[Path] = []
    seen: set[str] = set()
    for p in candidates:
        key = str(p)
        if key not in seen:
            seen.add(key)
            deduped.append(p)
    return deduped


def load_barcelona_hotspots(explicit_path: Optional[str] = None) -> Dict[str, Hotspot]:
    for candidate in _default_hotspot_search_paths(explicit_path):
        if candidate.exists():
            with candidate.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                hotspots: Dict[str, Hotspot] = {}
                for row in reader:
                    hs = Hotspot(
                        name=row["name"],
                        lat=float(row["lat"]),
                        lon=float(row["lon"]),
                        category=row["category"],
                        streets=row["streets"],
                        why=row["why"],
                    )
                    hotspots[hs.name] = hs
                if hotspots:
                    return hotspots
    return {}


@dataclass
class TwinBase:
    twin_id: str
    asset_type: AssetType
    name: str
    ts: str
    enabled: bool = True
    alarms: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

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

    def step(self, dt_h: float, context: Dict[str, Any]) -> None:
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
        queue_pressure = 0.0022 * base_flow + 0.10 * rain + incident_penalty - 0.12 * priority_effect
        self.queue_ns = max(3.0, self.queue_ns + np.random.normal(0, 1.2) + queue_pressure * 3.0 - 0.35 * self.offset_s / 10.0)
        self.queue_ew = max(3.0, self.queue_ew + np.random.normal(0, 1.1) + queue_pressure * 2.5)
        self.avg_delay_s = max(8.0, 12.0 + 1.4 * (self.queue_ns + self.queue_ew) + 0.02 * ped_flow + 12.0 * incident_penalty)
        self.ped_wait_s = max(5.0, 14.0 + 0.012 * ped_flow + 7.0 * ped_protection_effect + 8.0 * school_penalty)
        self.bus_priority_request = int(bus_ops["priority_requests"])
        self.throughput_vph = max(1200.0, base_flow * (0.82 + 0.04 * self.priority_mode - 0.03 * rain - 0.08 * incident_penalty))
        self.risk_score = float(np.clip(
            0.22 + 0.003 * self.avg_delay_s + 0.002 * self.ped_wait_s + 0.03 * rain + 0.10 * school_penalty - 0.04 * self.ped_protection_mode,
            0.0, 1.0
        ))

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        self.phase_plan = int(dispatch.get("signal_plan_id", self.phase_plan))
        self.offset_s = float(dispatch.get("offset_s", self.offset_s))
        self.priority_mode = int(dispatch.get("bus_priority_level", self.priority_mode))
        self.ped_protection_mode = int(dispatch.get("ped_protection_mode", self.ped_protection_mode))


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

    def step(self, dt_h: float, context: Dict[str, Any]) -> None:
        demand = context["demand"]
        weather = context["weather"]
        events = context["active_events"]
        flow = float(demand["corridor_flow_vph"])
        rain = float(weather["rain_intensity"])
        incident_flag = any(ev["event_type"] == "incident" for ev in events)
        event_release = any(ev["event_type"] == "event_release" for ev in events)
        demand_spike = any(ev["event_type"] == "demand_spike" for ev in events)
        self.incident_state = incident_flag
        congestion_pressure = 0.00022 * flow + 0.28 * rain + (0.35 if incident_flag else 0.0) + (0.18 if demand_spike else 0.0) + (0.12 if event_release else 0.0)
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

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        self.signal_coordination_mode = int(dispatch.get("signal_coordination_mode", self.signal_coordination_mode))
        self.diversion_mode = int(dispatch.get("diversion_mode", self.diversion_mode))
        self.lane_priority_mode = int(dispatch.get("lane_priority_mode", self.lane_priority_mode))


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


@dataclass
class CityMobilitySystemTwin(TwinBase):
    mode: Mode = "traffic"
    scenario: ScenarioName = "corridor_congestion"
    network_speed_index: float = 0.0
    corridor_reliability_index: float = 0.0
    bus_bunching_index: float = 0.0
    curb_pressure_index: float = 0.0
    risk_hotspots_active: int = 0
    near_miss_city_index: float = 0.0
    gateway_delay_index: float = 0.0
    step_operational_score: float = 0.0
    cumulative_operational_score: float = 0.0
    decision_route: Route = "CLASSICAL"
    decision_confidence: float = 0.0
    fallback_triggered: bool = False
    active_event: Optional[str] = None

    def step(self, dt_h: float, context: Dict[str, Any]) -> None:
        pass

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        pass


@dataclass
class ScenarioEvent:
    event_type: EventType
    severity: float
    start_step: int
    end_step: int
    payload: Dict[str, Any]

    def is_active(self, step_id: int) -> bool:
        return self.start_step <= step_id <= self.end_step


@dataclass
class ScenarioContext:
    scenario: ScenarioName
    mode: Mode
    weather: Dict[str, Any]
    demand: Dict[str, Any]
    bus_ops: Dict[str, Any]
    curb_ops: Dict[str, Any]
    gateway_ops: Dict[str, Any]
    active_events: List[ScenarioEvent] = field(default_factory=list)


@dataclass
class MobilityDispatchProblem:
    step_id: int
    mode: Mode
    scenario: ScenarioName
    objective_name: str
    constraints: Dict[str, Any]
    objective_terms: Dict[str, float]
    complexity_score: float
    discrete_ratio: float
    horizon_steps: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MobilityExecRecord:
    step_id: int
    ts: str
    mode: Mode
    scenario: ScenarioName
    active_event: Optional[str]
    network_speed_index: float
    corridor_reliability_index: float
    corridor_delay_s: float
    bus_bunching_index: float
    bus_commercial_speed_kmh: float
    bus_priority_requests: int
    curb_occupancy_rate: float
    illegal_curb_occupancy_rate: float
    delivery_queue: float
    risk_score: float
    near_miss_index: float
    pedestrian_exposure: float
    bike_conflict_index: float
    gateway_delay_index: float
    step_operational_score: float
    cumulative_operational_score: float
    decision_route: Route
    decision_confidence: float
    exec_ms: int
    latency_breach: bool
    fallback_triggered: bool
    fallback_reasons: List[str]
    route_reason: str
    complexity_score: float
    discrete_ratio: float
    intersection_hotspot: str = ""
    road_corridor_hotspot: str = ""
    bus_corridor_hotspot: str = ""
    curb_zone_hotspot: str = ""
    risk_hotspot_name: str = ""
    primary_hotspot_name: str = ""
    primary_hotspot_lat: float = 41.3851
    primary_hotspot_lon: float = 2.1734
    scenario_note: str = ""
    qre_json: Optional[str] = None
    result_json: Optional[str] = None
    dispatch_json: Optional[str] = None
    objective_breakdown_json: Optional[str] = None


class ClassicalMobilitySolver:
    def solve(self, state: Dict[str, Any], problem: MobilityDispatchProblem) -> Tuple[Dict[str, Any], Dict[str, float], float]:
        risk = state["risk_score"]
        bunching = state["bus_bunching_index"]
        curb_pressure = state["curb_pressure_index"]
        speed_index = state["network_speed_index"]
        active_event = state["active_event"]
        mode = problem.mode
        signal_plan_id = 1
        offset_s = 0.0
        bus_priority_level = 1
        holding_strategy = 0
        dispatch_adjustment = 0
        diversion_mode = 0
        lane_priority_mode = 1
        curb_slot_policy = 1
        enforcement_level = 1
        access_window_mode = 1
        ped_protection_mode = 0
        speed_mitigation_mode = 0
        preventive_alert_level = 0
        if mode == "safety" or risk > 0.62:
            ped_protection_mode = 1
            speed_mitigation_mode = 1
            preventive_alert_level = 2
            signal_plan_id = 2
            bus_priority_level = 1
        if bunching > 0.35:
            bus_priority_level = 2
            holding_strategy = 1
            dispatch_adjustment = 1
        if speed_index < 0.62:
            signal_plan_id = 2
            diversion_mode = 1
            lane_priority_mode = 2
            offset_s = 8.0
        if curb_pressure > 0.55:
            curb_slot_policy = 2
            enforcement_level = 2
            access_window_mode = 2
        if active_event == "incident":
            diversion_mode = 2
            signal_plan_id = 3
        if active_event == "delivery_wave":
            curb_slot_policy = 2
            enforcement_level = 2
        if active_event == "school_peak":
            ped_protection_mode = 1
            speed_mitigation_mode = 1
            preventive_alert_level = 2
        dispatch = {
            "signal_plan_id": signal_plan_id,
            "offset_s": offset_s,
            "bus_priority_level": bus_priority_level,
            "holding_strategy": holding_strategy,
            "dispatch_adjustment": dispatch_adjustment,
            "signal_coordination_mode": signal_plan_id,
            "diversion_mode": diversion_mode,
            "lane_priority_mode": lane_priority_mode,
            "curb_slot_policy": curb_slot_policy,
            "enforcement_level": enforcement_level,
            "access_window_mode": access_window_mode,
            "ped_protection_mode": ped_protection_mode,
            "speed_mitigation_mode": speed_mitigation_mode,
            "preventive_alert_level": preventive_alert_level,
        }
        objective_breakdown = {
            "delay_penalty": state["corridor_delay_s"] * 0.08,
            "bunching_penalty": bunching * 8.0,
            "risk_penalty": risk * 14.0,
            "curb_penalty": curb_pressure * 7.0,
            "gateway_penalty": state["gateway_delay_index"] * 4.0,
        }
        confidence = 0.86 if mode in {"safety", "traffic"} else 0.80
        return dispatch, objective_breakdown, confidence


class MockQuantumMobilitySolver:
    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    def solve(self, state: Dict[str, Any], problem: MobilityDispatchProblem) -> Tuple[Dict[str, Any], Dict[str, float], float, Dict[str, Any], Dict[str, Any]]:
        classical = ClassicalMobilitySolver()
        dispatch, obj, _ = classical.solve(state, problem)
        active_event = state["active_event"]
        if active_event in {"delivery_wave", "illegal_curb_occupation"}:
            dispatch["curb_slot_policy"] = 2
            dispatch["enforcement_level"] = 2
            dispatch["access_window_mode"] = 2
            obj["curb_penalty"] *= 0.83
        if active_event in {"bus_bunching", "demand_spike"}:
            dispatch["bus_priority_level"] = min(3, int(dispatch["bus_priority_level"]) + 1)
            dispatch["holding_strategy"] = 1
            dispatch["signal_coordination_mode"] = max(2, int(dispatch["signal_coordination_mode"]))
            obj["bunching_penalty"] *= 0.85
            obj["delay_penalty"] *= 0.92
        if active_event in {"event_release", "gateway_surge"}:
            dispatch["diversion_mode"] = 2
            dispatch["signal_coordination_mode"] = 3
            dispatch["bus_priority_level"] = max(2, int(dispatch["bus_priority_level"]))
            obj["gateway_penalty"] *= 0.84
            obj["delay_penalty"] *= 0.90
        if active_event in {"school_peak", "rain_event"}:
            dispatch["ped_protection_mode"] = 1
            dispatch["speed_mitigation_mode"] = 1
            dispatch["preventive_alert_level"] = 2
            obj["risk_penalty"] *= 0.86
        confidence = 0.75 + 0.10 * self.rng.random()
        qre = {
            "qre_version": "1.0",
            "mode": problem.mode,
            "scenario": problem.scenario,
            "objective_name": problem.objective_name,
            "complexity_score": problem.complexity_score,
            "discrete_ratio": problem.discrete_ratio,
            "constraints": problem.constraints,
            "active_event": problem.metadata.get("active_event"),
        }
        result = {
            "status": "SUCCEEDED",
            "backend": {
                "provider": "SIM_QPU",
                "backend_id": "sim-mobility-qpu",
                "queue_ms": int(220 + 420 * self.rng.random()),
                "exec_ms": int(150 + 180 * self.rng.random()),
            },
            "solution": {
                "dispatch": dispatch,
                "confidence": confidence,
            },
        }
        return dispatch, obj, confidence, qre, result


class MobilityHybridOrchestrator:
    def __init__(self, seed: int = 42):
        self.classical = ClassicalMobilitySolver()
        self.quantum = MockQuantumMobilitySolver(seed=seed)

    def choose_route(self, problem: MobilityDispatchProblem) -> Tuple[Route, str]:
        event = problem.metadata.get("active_event")
        risk = float(problem.metadata.get("risk_score", 0.0))
        bunching = float(problem.metadata.get("bus_bunching_index", 0.0))
        curb_pressure = float(problem.metadata.get("curb_pressure_index", 0.0))
        gateway_pressure = float(problem.metadata.get("gateway_delay_index", 0.0))
        if problem.mode == "safety" and (risk > 0.58 or event in {"school_peak", "incident"}):
            return "CLASSICAL", "Classical selected because the step is in immediate safety protection mode."
        if problem.complexity_score < 4.7 or problem.discrete_ratio < 0.40:
            return "CLASSICAL", "Classical selected because the decision space is still limited."
        if event in {"delivery_wave", "illegal_curb_occupation", "gateway_surge", "event_release", "bus_bunching"}:
            return "QUANTUM", "Quantum selected because the step combines multiple discrete urban control actions."
        if problem.mode == "logistics" and curb_pressure > 0.52:
            return "QUANTUM", "Quantum selected because curbside allocation and enforcement are under high pressure."
        if problem.mode == "gateway" and gateway_pressure > 0.52:
            return "QUANTUM", "Quantum selected because access coordination across multiple resources is required."
        if problem.mode == "traffic" and bunching > 0.30 and problem.complexity_score > 5.3:
            return "QUANTUM", "Quantum selected because corridor coordination and bus priority conflict across several actions."
        return "CLASSICAL", "Classical selected because the step remains manageable with deterministic coordination."

    def solve(self, state: Dict[str, Any], problem: MobilityDispatchProblem) -> Dict[str, Any]:
        route, reason = self.choose_route(problem)
        if route == "CLASSICAL":
            dispatch, breakdown, confidence = self.classical.solve(state, problem)
            return {
                "route": "CLASSICAL",
                "route_reason": reason,
                "dispatch": dispatch,
                "objective_breakdown": breakdown,
                "confidence": confidence,
                "exec_ms": 48,
                "latency_breach": False,
                "fallback_triggered": False,
                "fallback_reasons": [],
                "qre_json": None,
                "result_json": None,
            }
        dispatch, breakdown, confidence, qre, result = self.quantum.solve(state, problem)
        exec_ms = int(result["backend"]["queue_ms"] + result["backend"]["exec_ms"])
        latency_limit_ms = 1100 if problem.mode in {"gateway", "event"} else 900
        latency_breach = exec_ms > latency_limit_ms
        fallback_reasons: List[str] = []
        fallback_triggered = False
        if latency_breach:
            fallback_triggered = True
            fallback_reasons.append("SLA_BREACH")
        if confidence < 0.73:
            fallback_triggered = True
            fallback_reasons.append("LOW_CONFIDENCE")
        if fallback_triggered:
            dispatch, breakdown, confidence = self.classical.solve(state, problem)
            return {
                "route": "FALLBACK_CLASSICAL",
                "route_reason": "Fallback to classical because the hybrid attempt breached SLA or confidence constraints.",
                "dispatch": dispatch,
                "objective_breakdown": breakdown,
                "confidence": confidence,
                "exec_ms": exec_ms,
                "latency_breach": latency_breach,
                "fallback_triggered": True,
                "fallback_reasons": fallback_reasons,
                "qre_json": json.dumps(qre, ensure_ascii=False),
                "result_json": json.dumps(result, ensure_ascii=False),
            }
        return {
            "route": "QUANTUM",
            "route_reason": reason,
            "dispatch": dispatch,
            "objective_breakdown": breakdown,
            "confidence": confidence,
            "exec_ms": exec_ms,
            "latency_breach": latency_breach,
            "fallback_triggered": False,
            "fallback_reasons": [],
            "qre_json": json.dumps(qre, ensure_ascii=False),
            "result_json": json.dumps(result, ensure_ascii=False),
        }


class MobilityRuntime:
    def __init__(self, scenario: ScenarioName = "corridor_congestion", seed: int = 42, hotspots_csv: Optional[str] = None):
        self.scenario = scenario
        self.seed = int(seed)
        self.hotspots_csv = hotspots_csv
        self.rng = np.random.default_rng(self.seed)
        self.step_id = 0
        self.cumulative_operational_score = 0.0
        self.orchestrator = MobilityHybridOrchestrator(seed=self.seed)
        self.records: List[MobilityExecRecord] = []
        self.hotspots: Dict[str, Hotspot] = load_barcelona_hotspots(hotspots_csv)
        self.twins: Dict[str, TwinBase] = {}
        self._build_twins()

    def _build_twins(self) -> None:
        ts = utc_now_iso()
        self.twins = {
            "intersection": IntersectionTwin("intersection", "intersection", "Main Intersection", ts),
            "road_corridor": RoadCorridorTwin("road_corridor", "road_corridor", "Primary Corridor", ts),
            "bus_corridor": BusCorridorTwin("bus_corridor", "bus_corridor", "Bus Corridor", ts),
            "curb_zone": CurbZoneTwin("curb_zone", "curb_zone", "Curb Zone", ts),
            "risk_hotspot": RiskHotspotTwin("risk_hotspot", "risk_hotspot", "Risk Hotspot", ts),
            "city_mobility_system": CityMobilitySystemTwin("city_mobility_system", "city_mobility_system", "City Mobility System", ts),
        }
        self._attach_hotspots_to_twins()

    def _hotspot(self, name: str) -> Optional[Hotspot]:
        return self.hotspots.get(name)

    def _scenario_hotspot_names(self) -> Dict[str, str]:
        mappings: Dict[str, Dict[str, str]] = {
            "corridor_congestion": {
                "intersection": "Plaça de les Glòries Catalanes",
                "road_corridor": "Plaça de les Glòries Catalanes",
                "bus_corridor": "Plaça de les Glòries Catalanes",
                "curb_zone": "Plaça de Catalunya / Ronda Universitat",
                "risk_hotspot": "Plaça d'Espanya",
            },
            "school_area_risk": {
                "intersection": "Plaça de Catalunya / Ronda Universitat",
                "road_corridor": "Plaça de Catalunya / Ronda Universitat",
                "bus_corridor": "Sants Estació / Plaça dels Països Catalans",
                "curb_zone": "Plaça de Catalunya / Ronda Universitat",
                "risk_hotspot": "Plaça de Catalunya / Ronda Universitat",
            },
            "urban_logistics_saturation": {
                "intersection": "Plaça Cerdà / Passeig de la Zona Franca",
                "road_corridor": "Ronda del Port VI / Carrer 3 (Puertas 29-30)",
                "bus_corridor": "Paral·lel / Port Vell / salida 21 Ronda Litoral",
                "curb_zone": "Plaça Cerdà / Passeig de la Zona Franca",
                "risk_hotspot": "Paral·lel / Port Vell / salida 21 Ronda Litoral",
            },
            "gateway_access_stress": {
                "intersection": "Plaça Cerdà / Passeig de la Zona Franca",
                "road_corridor": "Aeropuerto Josep Tarradellas BCN-El Prat T1",
                "bus_corridor": "Aeropuerto Josep Tarradellas BCN-El Prat T2",
                "curb_zone": "Aeropuerto Josep Tarradellas BCN-El Prat T1",
                "risk_hotspot": "Moll Adossat / Port Creuers (Puerta 2)",
            },
            "event_mobility": {
                "intersection": "Plaça d'Espanya",
                "road_corridor": "Plaça de Catalunya / Ronda Universitat",
                "bus_corridor": "Sants Estació / Plaça dels Països Catalans",
                "curb_zone": "Plaça de Catalunya / Ronda Universitat",
                "risk_hotspot": "Plaça d'Espanya",
            },
            "corridor_congestion_multi_corridor": {
                "intersection": "Plaça de les Glòries Catalanes",
                "road_corridor": "Plaça de les Glòries Catalanes",
                "bus_corridor": "Plaça d'Espanya",
                "curb_zone": "Plaça de Catalunya / Ronda Universitat",
                "risk_hotspot": "Sants Estació / Plaça dels Països Catalans",
            },
            "school_peak_rain_visibility": {
                "intersection": "Plaça de Catalunya / Ronda Universitat",
                "road_corridor": "Plaça d'Espanya",
                "bus_corridor": "Sants Estació / Plaça dels Països Catalans",
                "curb_zone": "Plaça de Catalunya / Ronda Universitat",
                "risk_hotspot": "Plaça de Catalunya / Ronda Universitat",
            },
            "urban_logistics_black_friday": {
                "intersection": "Plaça Cerdà / Passeig de la Zona Franca",
                "road_corridor": "Paral·lel / Port Vell / salida 21 Ronda Litoral",
                "bus_corridor": "Plaça de Catalunya / Ronda Universitat",
                "curb_zone": "Plaça Cerdà / Passeig de la Zona Franca",
                "risk_hotspot": "Ronda del Port VI / Carrer 3 (Puertas 29-30)",
            },
            "airport_departure_bank_stress": {
                "intersection": "Plaça de Catalunya / Ronda Universitat",
                "road_corridor": "Aeropuerto Josep Tarradellas BCN-El Prat T1",
                "bus_corridor": "Aeropuerto Josep Tarradellas BCN-El Prat T2",
                "curb_zone": "Aeropuerto Josep Tarradellas BCN-El Prat T1",
                "risk_hotspot": "Aeropuerto Josep Tarradellas BCN-El Prat T2",
            },
            "port_truck_convoy_pressure": {
                "intersection": "Plaça Cerdà / Passeig de la Zona Franca",
                "road_corridor": "Ronda del Port VI / Carrer 3 (Puertas 29-30)",
                "bus_corridor": "Paral·lel / Port Vell / salida 21 Ronda Litoral",
                "curb_zone": "Moll Adossat / Port Creuers (Puerta 2)",
                "risk_hotspot": "Ronda del Port VI / Carrer 3 (Puertas 29-30)",
            },
            "stadium_event_release_plus_rain": {
                "intersection": "Plaça d'Espanya",
                "road_corridor": "Plaça de Catalunya / Ronda Universitat",
                "bus_corridor": "Sants Estació / Plaça dels Països Catalans",
                "curb_zone": "Plaça d'Espanya",
                "risk_hotspot": "Plaça d'Espanya",
            },
            "city_centre_tourism_weekend": {
                "intersection": "Plaça de Catalunya / Ronda Universitat",
                "road_corridor": "Paral·lel / Port Vell / salida 21 Ronda Litoral",
                "bus_corridor": "Plaça de Catalunya / Ronda Universitat",
                "curb_zone": "Plaça de Catalunya / Ronda Universitat",
                "risk_hotspot": "Paral·lel / Port Vell / salida 21 Ronda Litoral",
            },
            "works_plus_incident_chain": {
                "intersection": "Plaça de les Glòries Catalanes",
                "road_corridor": "Plaça d'Espanya",
                "bus_corridor": "Sants Estació / Plaça dels Països Catalans",
                "curb_zone": "Plaça Cerdà / Passeig de la Zona Franca",
                "risk_hotspot": "Plaça de les Glòries Catalanes",
            },
            "multimodal_hub_systemic_pressure": {
                "intersection": "Sants Estació / Plaça dels Països Catalans",
                "road_corridor": "Plaça de les Glòries Catalanes",
                "bus_corridor": "Sants Estació / Plaça dels Països Catalans",
                "curb_zone": "Plaça de Catalunya / Ronda Universitat",
                "risk_hotspot": "Sants Estació / Plaça dels Països Catalans",
            },
            "compound_extreme_day": {
                "intersection": "Plaça de Catalunya / Ronda Universitat",
                "road_corridor": "Plaça d'Espanya",
                "bus_corridor": "Sants Estació / Plaça dels Països Catalans",
                "curb_zone": "Plaça Cerdà / Passeig de la Zona Franca",
                "risk_hotspot": "Aeropuerto Josep Tarradellas BCN-El Prat T1",
            },
        }
        return mappings.get(self.scenario, mappings["corridor_congestion"])

    def _scenario_note(self) -> str:
        notes = {
            "corridor_congestion": "Scenario anchored to Glòries as a primary corridor/interchange hotspot, with support nodes at Plaça de Catalunya and Plaça d'Espanya.",
            "school_area_risk": "No school-specific hotspot exists in the CSV yet, so the scenario uses Plaça de Catalunya as a high-pedestrian proxy hotspot until a school-zone layer is added.",
            "urban_logistics_saturation": "Scenario anchored to Plaça Cerdà, Ronda del Port VI and Port Vell as Barcelona logistics and curbside pressure nodes.",
            "gateway_access_stress": "Scenario anchored to airport terminals T1/T2 and cruise/port access nodes as Barcelona gateway hotspots.",
            "event_mobility": "Scenario anchored to Plaça d'Espanya, Plaça de Catalunya and Sants as high-pressure event and intermodal redistribution nodes.",
            "corridor_congestion_multi_corridor": "High-complexity corridor scenario spanning Glòries, Espanya and Sants with coordinated congestion, bus regularity and city-centre pressure.",
            "school_peak_rain_visibility": "Safety-heavy scenario combining school peak conditions, reduced visibility and elevated pedestrian exposure in central Barcelona.",
            "urban_logistics_black_friday": "Black-Friday logistics scenario concentrated around Plaça Cerdà, Port Vell and the port logistics interface, with heavy curbside stress.",
            "airport_departure_bank_stress": "Airport departure bank scenario focused on T1/T2 access, curbside pressure and multimodal gateway coordination.",
            "port_truck_convoy_pressure": "Freight gateway scenario focused on Port access gates, heavy truck convoy pressure and spillback risk toward the urban network.",
            "stadium_event_release_plus_rain": "High-complexity event release scenario around Espanya and Sants, intensified by rain and post-event multimodal redistribution.",
            "city_centre_tourism_weekend": "Weekend tourism scenario centred on Plaça de Catalunya and Port Vell, with high pedestrian, transit and curbside pressure.",
            "works_plus_incident_chain": "Compound disruption scenario combining works-style capacity loss, incident propagation and corridor/bus degradation.",
            "multimodal_hub_systemic_pressure": "Systemic multimodal hub scenario around Sants and Glòries, coupling corridor, bus and interchange pressure.",
            "compound_extreme_day": "Extreme compound scenario combining gateway stress, central pressure, logistics overload and systemic operational degradation.",
        }
        return notes.get(self.scenario, notes["corridor_congestion"])

    def _attach_hotspots_to_twins(self) -> None:
        mapping = self._scenario_hotspot_names()
        note = self._scenario_note()
        for twin_id in ["intersection", "road_corridor", "bus_corridor", "curb_zone", "risk_hotspot"]:
            hotspot_name = mapping[twin_id]
            hotspot = self._hotspot(hotspot_name)
            meta: Dict[str, Any] = {
                "scenario_hotspot_name": hotspot_name,
                "scenario_note": note,
            }
            if hotspot is not None:
                meta.update({
                    "hotspot_name": hotspot.name,
                    "lat": hotspot.lat,
                    "lon": hotspot.lon,
                    "category": hotspot.category,
                    "streets": hotspot.streets,
                    "why": hotspot.why,
                })
            self.twins[twin_id].metadata.update(meta)

    def hotspot_dataframe(self) -> pd.DataFrame:
        mapping = self._scenario_hotspot_names()
        rows: List[Dict[str, Any]] = []
        for twin_id, hotspot_name in mapping.items():
            hotspot = self._hotspot(hotspot_name)
            if hotspot is None:
                continue
            rows.append({
                "twin_id": twin_id,
                "hotspot_name": hotspot.name,
                "lat": hotspot.lat,
                "lon": hotspot.lon,
                "category": hotspot.category,
                "streets": hotspot.streets,
                "why": hotspot.why,
                "scenario": self.scenario,
            })
        return pd.DataFrame(rows)

    def _mode_for_scenario(self) -> Mode:
        if self.scenario in {"school_area_risk", "school_peak_rain_visibility"}:
            return "safety"
        if self.scenario in {"urban_logistics_saturation", "urban_logistics_black_friday", "port_truck_convoy_pressure"}:
            return "logistics"
        if self.scenario in {"gateway_access_stress", "airport_departure_bank_stress"}:
            return "gateway"
        if self.scenario in {"event_mobility", "stadium_event_release_plus_rain", "city_centre_tourism_weekend", "compound_extreme_day"}:
            return "event"
        return "traffic"

    def _generate_base_context(self) -> ScenarioContext:
        mode = self._mode_for_scenario()
        hour = (self.step_id % 288) / 12.0
        peak = 1.0 if 7.0 <= hour <= 10.0 or 17.0 <= hour <= 20.0 else 0.0
        rain_intensity = 0.0
        visibility = 0.95
        corridor_flow = 3600.0 + 1200.0 * peak + 450.0 * np.sin(hour / 24.0 * 2 * np.pi) + self.rng.normal(0, 120)
        ped_flow = 550.0 + 320.0 * peak + 120.0 * np.sin((hour + 2.0) / 24.0 * 2 * np.pi) + self.rng.normal(0, 40)
        bike_flow = 280.0 + 120.0 * np.sin((hour - 1.5) / 24.0 * 2 * np.pi) + self.rng.normal(0, 25)
        headway_pressure = 0.35 + 0.25 * peak + self.rng.normal(0, 0.03)
        delivery_pressure = 0.30 + 0.22 * (10.0 <= hour <= 15.0) + self.rng.normal(0, 0.03)
        illegal_pressure = 0.18 + 0.10 * (11.0 <= hour <= 14.0) + self.rng.normal(0, 0.02)
        pickup_dropoff_pressure = 0.22 + 0.18 * peak + self.rng.normal(0, 0.02)
        gateway_surge = 0.15 + 0.18 * peak + self.rng.normal(0, 0.02)

        # scenario-level baseline modifiers for high-complexity cases
        if self.scenario == "corridor_congestion_multi_corridor":
            corridor_flow *= 1.22
            headway_pressure += 0.12
            pickup_dropoff_pressure += 0.06
        elif self.scenario == "school_peak_rain_visibility":
            ped_flow *= 1.45
            corridor_flow *= 1.08
            rain_intensity = 0.35
            visibility = 0.72
            bike_flow *= 0.92
        elif self.scenario == "urban_logistics_black_friday":
            delivery_pressure += 0.30
            illegal_pressure += 0.16
            pickup_dropoff_pressure += 0.10
            corridor_flow *= 1.10
        elif self.scenario == "airport_departure_bank_stress":
            gateway_surge += 0.36
            pickup_dropoff_pressure += 0.18
            corridor_flow *= 1.08
        elif self.scenario == "port_truck_convoy_pressure":
            gateway_surge += 0.28
            delivery_pressure += 0.18
            corridor_flow *= 1.14
        elif self.scenario == "stadium_event_release_plus_rain":
            corridor_flow *= 1.16
            ped_flow *= 1.30
            headway_pressure += 0.14
            rain_intensity = 0.42
            visibility = 0.68
        elif self.scenario == "city_centre_tourism_weekend":
            ped_flow *= 1.40
            pickup_dropoff_pressure += 0.16
            corridor_flow *= 1.06
        elif self.scenario == "works_plus_incident_chain":
            corridor_flow *= 1.12
            headway_pressure += 0.10
            gateway_surge += 0.08
        elif self.scenario == "multimodal_hub_systemic_pressure":
            corridor_flow *= 1.18
            headway_pressure += 0.16
            pickup_dropoff_pressure += 0.08
            gateway_surge += 0.12
        elif self.scenario == "compound_extreme_day":
            corridor_flow *= 1.25
            ped_flow *= 1.28
            headway_pressure += 0.18
            delivery_pressure += 0.18
            illegal_pressure += 0.12
            pickup_dropoff_pressure += 0.14
            gateway_surge += 0.22
            rain_intensity = 0.30
            visibility = 0.75

        return ScenarioContext(
            scenario=self.scenario,
            mode=mode,
            weather={"rain_intensity": float(np.clip(rain_intensity, 0.0, 1.0)), "visibility": float(np.clip(visibility, 0.2, 1.0))},
            demand={
                "corridor_flow_vph": float(max(1400.0, corridor_flow)),
                "ped_flow_pph": float(max(100.0, ped_flow)),
                "bike_flow_pph": float(max(60.0, bike_flow)),
            },
            bus_ops={
                "priority_requests": int(max(0, round(2 + 4 * peak + self.rng.normal(0, 1.0)))),
                "headway_pressure": float(np.clip(headway_pressure, 0.0, 1.0)),
            },
            curb_ops={
                "delivery_pressure": float(np.clip(delivery_pressure, 0.0, 1.0)),
                "illegal_parking_pressure": float(np.clip(illegal_pressure, 0.0, 1.0)),
                "pickup_dropoff_pressure": float(np.clip(pickup_dropoff_pressure, 0.0, 1.0)),
            },
            gateway_ops={"surge_factor": float(np.clip(gateway_surge, 0.0, 1.0))},
            active_events=[],
        )

    def _generate_events(self, ctx: ScenarioContext) -> None:
        events: List[ScenarioEvent] = []
        s = self.scenario

        # Base scenarios
        if s == "corridor_congestion":
            if self.step_id % 24 in range(7, 12):
                events.append(ScenarioEvent("demand_spike", 0.7, self.step_id, self.step_id, {}))
            if self.step_id % 31 in (15, 16):
                events.append(ScenarioEvent("bus_bunching", 0.6, self.step_id, self.step_id, {}))
        elif s == "school_area_risk":
            if self.step_id % 24 in range(7, 11):
                events.append(ScenarioEvent("school_peak", 0.9, self.step_id, self.step_id, {}))
            if self.step_id % 19 == 8:
                events.append(ScenarioEvent("rain_event", 0.4, self.step_id, self.step_id, {}))
        elif s == "urban_logistics_saturation":
            if self.step_id % 20 in range(8, 14):
                events.append(ScenarioEvent("delivery_wave", 0.85, self.step_id, self.step_id, {}))
            if self.step_id % 17 in (5, 6):
                events.append(ScenarioEvent("illegal_curb_occupation", 0.7, self.step_id, self.step_id, {}))
        elif s == "gateway_access_stress":
            if self.step_id % 22 in range(6, 11):
                events.append(ScenarioEvent("gateway_surge", 0.8, self.step_id, self.step_id, {}))
            if self.step_id % 29 == 12:
                events.append(ScenarioEvent("incident", 0.7, self.step_id, self.step_id, {}))
        elif s == "event_mobility":
            if self.step_id % 26 in range(12, 18):
                events.append(ScenarioEvent("event_release", 0.95, self.step_id, self.step_id, {}))
            if self.step_id % 18 in (9, 10):
                events.append(ScenarioEvent("bus_bunching", 0.65, self.step_id, self.step_id, {}))
            if self.step_id % 33 == 20:
                events.append(ScenarioEvent("rain_event", 0.45, self.step_id, self.step_id, {}))

        # High-complexity scenarios
        elif s == "corridor_congestion_multi_corridor":
            if self.step_id % 18 in range(6, 12):
                events.append(ScenarioEvent("demand_spike", 0.9, self.step_id, self.step_id, {}))
            if self.step_id % 20 in (8, 9, 10):
                events.append(ScenarioEvent("bus_bunching", 0.75, self.step_id, self.step_id, {}))
            if self.step_id % 36 == 14:
                events.append(ScenarioEvent("incident", 0.55, self.step_id, self.step_id, {}))
        elif s == "school_peak_rain_visibility":
            if self.step_id % 24 in range(7, 12):
                events.append(ScenarioEvent("school_peak", 0.95, self.step_id, self.step_id, {}))
            if self.step_id % 16 in (6, 7, 8):
                events.append(ScenarioEvent("rain_event", 0.65, self.step_id, self.step_id, {}))
            if self.step_id % 30 == 9:
                events.append(ScenarioEvent("incident", 0.35, self.step_id, self.step_id, {}))
        elif s == "urban_logistics_black_friday":
            if self.step_id % 14 in range(8, 13):
                events.append(ScenarioEvent("delivery_wave", 0.95, self.step_id, self.step_id, {}))
            if self.step_id % 15 in (6, 7, 8):
                events.append(ScenarioEvent("illegal_curb_occupation", 0.85, self.step_id, self.step_id, {}))
            if self.step_id % 24 in (11, 12):
                events.append(ScenarioEvent("demand_spike", 0.5, self.step_id, self.step_id, {}))
        elif s == "airport_departure_bank_stress":
            if self.step_id % 18 in range(5, 10):
                events.append(ScenarioEvent("gateway_surge", 0.95, self.step_id, self.step_id, {}))
            if self.step_id % 21 in (8, 9):
                events.append(ScenarioEvent("bus_bunching", 0.55, self.step_id, self.step_id, {}))
            if self.step_id % 34 == 13:
                events.append(ScenarioEvent("incident", 0.45, self.step_id, self.step_id, {}))
        elif s == "port_truck_convoy_pressure":
            if self.step_id % 16 in range(6, 11):
                events.append(ScenarioEvent("gateway_surge", 0.85, self.step_id, self.step_id, {}))
            if self.step_id % 17 in range(8, 12):
                events.append(ScenarioEvent("delivery_wave", 0.75, self.step_id, self.step_id, {}))
            if self.step_id % 28 == 10:
                events.append(ScenarioEvent("incident", 0.65, self.step_id, self.step_id, {}))
        elif s == "stadium_event_release_plus_rain":
            if self.step_id % 20 in range(11, 16):
                events.append(ScenarioEvent("event_release", 0.95, self.step_id, self.step_id, {}))
            if self.step_id % 20 in (11, 12, 13):
                events.append(ScenarioEvent("rain_event", 0.6, self.step_id, self.step_id, {}))
            if self.step_id % 22 in (12, 13):
                events.append(ScenarioEvent("bus_bunching", 0.75, self.step_id, self.step_id, {}))
        elif s == "city_centre_tourism_weekend":
            if self.step_id % 18 in range(10, 16):
                events.append(ScenarioEvent("demand_spike", 0.75, self.step_id, self.step_id, {}))
            if self.step_id % 19 in (12, 13):
                events.append(ScenarioEvent("bus_bunching", 0.5, self.step_id, self.step_id, {}))
            if self.step_id % 17 in (11, 12):
                events.append(ScenarioEvent("illegal_curb_occupation", 0.55, self.step_id, self.step_id, {}))
        elif s == "works_plus_incident_chain":
            if self.step_id % 15 in range(6, 11):
                events.append(ScenarioEvent("incident", 0.9, self.step_id, self.step_id, {}))
            if self.step_id % 18 in (7, 8):
                events.append(ScenarioEvent("demand_spike", 0.7, self.step_id, self.step_id, {}))
            if self.step_id % 22 in (9, 10):
                events.append(ScenarioEvent("bus_bunching", 0.55, self.step_id, self.step_id, {}))
        elif s == "multimodal_hub_systemic_pressure":
            if self.step_id % 18 in range(7, 12):
                events.append(ScenarioEvent("bus_bunching", 0.8, self.step_id, self.step_id, {}))
            if self.step_id % 20 in range(8, 12):
                events.append(ScenarioEvent("event_release", 0.65, self.step_id, self.step_id, {}))
            if self.step_id % 24 in (9, 10):
                events.append(ScenarioEvent("gateway_surge", 0.6, self.step_id, self.step_id, {}))
        elif s == "compound_extreme_day":
            if self.step_id % 14 in range(5, 10):
                events.append(ScenarioEvent("demand_spike", 0.85, self.step_id, self.step_id, {}))
            if self.step_id % 15 in (6, 7):
                events.append(ScenarioEvent("rain_event", 0.55, self.step_id, self.step_id, {}))
            if self.step_id % 16 in (8, 9):
                events.append(ScenarioEvent("delivery_wave", 0.8, self.step_id, self.step_id, {}))
            if self.step_id % 17 in (10, 11):
                events.append(ScenarioEvent("gateway_surge", 0.75, self.step_id, self.step_id, {}))
            if self.step_id % 18 in (12, 13):
                events.append(ScenarioEvent("bus_bunching", 0.7, self.step_id, self.step_id, {}))
            if self.step_id % 21 == 14:
                events.append(ScenarioEvent("incident", 0.6, self.step_id, self.step_id, {}))

        ctx.active_events = events
        for ev in events:
            if ev.event_type == "demand_spike":
                ctx.demand["corridor_flow_vph"] *= 1.18
                ctx.curb_ops["pickup_dropoff_pressure"] = min(1.0, ctx.curb_ops["pickup_dropoff_pressure"] + 0.05)
            elif ev.event_type == "incident":
                ctx.demand["corridor_flow_vph"] *= 1.08
                ctx.bus_ops["headway_pressure"] = min(1.0, ctx.bus_ops["headway_pressure"] + 0.08)
            elif ev.event_type == "school_peak":
                ctx.demand["ped_flow_pph"] *= 1.40
            elif ev.event_type == "rain_event":
                ctx.weather["rain_intensity"] = max(ctx.weather["rain_intensity"], 0.45)
                ctx.weather["visibility"] = min(ctx.weather["visibility"], 0.70)
                ctx.demand["bike_flow_pph"] *= 0.9
            elif ev.event_type == "bus_bunching":
                ctx.bus_ops["headway_pressure"] = min(1.0, ctx.bus_ops["headway_pressure"] + 0.25)
                ctx.bus_ops["priority_requests"] += 1
            elif ev.event_type == "illegal_curb_occupation":
                ctx.curb_ops["illegal_parking_pressure"] = min(1.0, ctx.curb_ops["illegal_parking_pressure"] + 0.35)
            elif ev.event_type == "delivery_wave":
                ctx.curb_ops["delivery_pressure"] = min(1.0, ctx.curb_ops["delivery_pressure"] + 0.35)
            elif ev.event_type == "gateway_surge":
                ctx.gateway_ops["surge_factor"] = min(1.0, ctx.gateway_ops["surge_factor"] + 0.45)
                ctx.curb_ops["pickup_dropoff_pressure"] = min(1.0, ctx.curb_ops["pickup_dropoff_pressure"] + 0.08)
            elif ev.event_type == "event_release":
                ctx.demand["corridor_flow_vph"] *= 1.12
                ctx.demand["ped_flow_pph"] *= 1.25
                ctx.bus_ops["priority_requests"] += 2
                ctx.gateway_ops["surge_factor"] = min(1.0, ctx.gateway_ops["surge_factor"] + 0.25)

    def get_context(self) -> ScenarioContext:
        ctx = self._generate_base_context()
        self._generate_events(ctx)
        return ctx

    def update_telemetry(self, ctx: ScenarioContext) -> None:
        dt_h = 5.0 / 60.0
        ctx_dict = {
            "weather": ctx.weather,
            "demand": ctx.demand,
            "bus_ops": ctx.bus_ops,
            "curb_ops": ctx.curb_ops,
            "gateway_ops": ctx.gateway_ops,
            "active_events": [asdict(e) for e in ctx.active_events],
        }
        for twin in self.twins.values():
            twin.ts = utc_now_iso()
        self.twins["intersection"].step(dt_h, ctx_dict)
        self.twins["road_corridor"].step(dt_h, ctx_dict)
        self.twins["bus_corridor"].step(dt_h, ctx_dict)
        self.twins["curb_zone"].step(dt_h, ctx_dict)
        self.twins["risk_hotspot"].step(dt_h, ctx_dict)

    def aggregate_state(self, ctx: ScenarioContext) -> Dict[str, Any]:
        inter = self.twins["intersection"]
        corridor = self.twins["road_corridor"]
        bus = self.twins["bus_corridor"]
        curb = self.twins["curb_zone"]
        risk = self.twins["risk_hotspot"]
        assert isinstance(inter, IntersectionTwin)
        assert isinstance(corridor, RoadCorridorTwin)
        assert isinstance(bus, BusCorridorTwin)
        assert isinstance(curb, CurbZoneTwin)
        assert isinstance(risk, RiskHotspotTwin)
        active_event = ctx.active_events[0].event_type if ctx.active_events else None
        network_speed_index = float(np.clip(corridor.avg_speed_kmh / 32.0, 0.0, 1.2))
        corridor_reliability_index = float(np.clip(1.0 / corridor.travel_time_index, 0.0, 1.2))
        curb_pressure_index = float(np.clip(0.55 * curb.occupancy_rate + 0.45 * curb.illegal_occupancy_rate, 0.0, 1.0))
        gateway_delay_index = float(np.clip(0.18 + 0.65 * ctx.gateway_ops["surge_factor"] + 0.12 * corridor.queue_spillback_risk, 0.0, 1.0))
        coordination_flag = bus.bunching_index > 0.28 and corridor.queue_spillback_risk > 0.35
        logistics_pressure_flag = curb.delivery_queue > 8.0 or curb.illegal_occupancy_rate > 0.22
        hotspot_map = self._scenario_hotspot_names()
        primary_name = hotspot_map["road_corridor"]
        primary_hotspot = self._hotspot(primary_name)
        return {
            "ts": utc_now_iso(),
            "mode": ctx.mode,
            "scenario": ctx.scenario,
            "scenario_note": self._scenario_note(),
            "active_event": active_event,
            "intersection_hotspot": hotspot_map["intersection"],
            "road_corridor_hotspot": hotspot_map["road_corridor"],
            "bus_corridor_hotspot": hotspot_map["bus_corridor"],
            "curb_zone_hotspot": hotspot_map["curb_zone"],
            "risk_hotspot_name": hotspot_map["risk_hotspot"],
            "primary_hotspot_name": primary_name,
            "primary_hotspot_lat": primary_hotspot.lat if primary_hotspot else 41.3851,
            "primary_hotspot_lon": primary_hotspot.lon if primary_hotspot else 2.1734,
            "network_speed_index": network_speed_index,
            "corridor_reliability_index": corridor_reliability_index,
            "corridor_delay_s": corridor.travel_time_index * 75.0,
            "bus_bunching_index": bus.bunching_index,
            "bus_commercial_speed_kmh": bus.commercial_speed_kmh,
            "bus_priority_requests": bus.priority_requests_active,
            "curb_occupancy_rate": curb.occupancy_rate,
            "illegal_curb_occupancy_rate": curb.illegal_occupancy_rate,
            "delivery_queue": curb.delivery_queue,
            "curb_pressure_index": curb_pressure_index,
            "risk_score": risk.risk_score,
            "near_miss_index": risk.near_miss_index,
            "pedestrian_exposure": risk.pedestrian_exposure,
            "bike_conflict_index": risk.bike_conflict_index,
            "gateway_delay_index": gateway_delay_index,
            "coordination_flag": coordination_flag,
            "logistics_pressure_flag": logistics_pressure_flag,
            "rain_flag": ctx.weather["rain_intensity"] > 0.20,
            "school_peak_flag": active_event == "school_peak",
            "incident_flag": active_event == "incident",
            "delivery_wave_flag": active_event == "delivery_wave",
            "gateway_surge_flag": active_event == "gateway_surge",
        }

    def build_problem(self, state: Dict[str, Any], ctx: ScenarioContext) -> MobilityDispatchProblem:
        discrete_vars = 8
        continuous_vars = 2
        event_bonus = 0.0
        if state["active_event"] in {"delivery_wave", "illegal_curb_occupation", "gateway_surge", "event_release", "bus_bunching"}:
            event_bonus += 1.5
        if state["active_event"] in {"school_peak", "rain_event"}:
            event_bonus += 0.8
        if state["incident_flag"]:
            event_bonus += 1.1
        coupling_bonus = 0.0
        if state["coordination_flag"]:
            coupling_bonus += 1.0
        if state["logistics_pressure_flag"]:
            coupling_bonus += 0.8
        if state["gateway_delay_index"] > 0.50:
            coupling_bonus += 0.9
        mode_bonus = {"traffic": 0.7, "safety": 0.4, "logistics": 1.0, "gateway": 1.0, "event": 1.2}[ctx.mode]
        complexity = discrete_vars * 0.55 + continuous_vars * 0.15 + event_bonus + coupling_bonus + mode_bonus
        discrete_ratio = discrete_vars / max(discrete_vars + continuous_vars, 1)
        constraints = {
            "network_speed_index": state["network_speed_index"],
            "corridor_reliability_index": state["corridor_reliability_index"],
            "bus_bunching_index": state["bus_bunching_index"],
            "curb_pressure_index": state["curb_pressure_index"],
            "risk_score": state["risk_score"],
            "gateway_delay_index": state["gateway_delay_index"],
        }
        objective_terms = {
            "delay_penalty_weight": 1.0,
            "bunching_penalty_weight": 1.0,
            "risk_penalty_weight": 1.2,
            "curb_penalty_weight": 0.9,
            "gateway_penalty_weight": 0.8,
        }
        metadata = {
            "active_event": state["active_event"],
            "risk_score": state["risk_score"],
            "bus_bunching_index": state["bus_bunching_index"],
            "curb_pressure_index": state["curb_pressure_index"],
            "gateway_delay_index": state["gateway_delay_index"],
            "coordination_flag": state["coordination_flag"],
            "logistics_pressure_flag": state["logistics_pressure_flag"],
            "incident_flag": state["incident_flag"],
            "rain_flag": state["rain_flag"],
            "school_peak_flag": state["school_peak_flag"],
            "primary_hotspot_name": state["primary_hotspot_name"],
            "intersection_hotspot": state["intersection_hotspot"],
            "road_corridor_hotspot": state["road_corridor_hotspot"],
            "bus_corridor_hotspot": state["bus_corridor_hotspot"],
            "curb_zone_hotspot": state["curb_zone_hotspot"],
            "risk_hotspot_name": state["risk_hotspot_name"],
        }
        return MobilityDispatchProblem(
            step_id=self.step_id,
            mode=ctx.mode,
            scenario=ctx.scenario,
            objective_name="min_delay_risk_and_logistics_conflict",
            constraints=constraints,
            objective_terms=objective_terms,
            complexity_score=complexity,
            discrete_ratio=discrete_ratio,
            horizon_steps=12,
            metadata=metadata,
        )

    def validate_dispatch(self, dispatch: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        dispatch = dict(dispatch)
        dispatch["bus_priority_level"] = int(np.clip(dispatch.get("bus_priority_level", 1), 0, 3))
        dispatch["signal_plan_id"] = int(np.clip(dispatch.get("signal_plan_id", 1), 0, 3))
        dispatch["curb_slot_policy"] = int(np.clip(dispatch.get("curb_slot_policy", 1), 0, 2))
        dispatch["enforcement_level"] = int(np.clip(dispatch.get("enforcement_level", 1), 0, 2))
        dispatch["ped_protection_mode"] = int(np.clip(dispatch.get("ped_protection_mode", 0), 0, 1))
        dispatch["speed_mitigation_mode"] = int(np.clip(dispatch.get("speed_mitigation_mode", 0), 0, 1))
        return dispatch

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        self.twins["intersection"].apply_dispatch(dispatch, dt_h)
        self.twins["road_corridor"].apply_dispatch(dispatch, dt_h)
        self.twins["bus_corridor"].apply_dispatch(dispatch, dt_h)
        self.twins["curb_zone"].apply_dispatch(dispatch, dt_h)
        self.twins["risk_hotspot"].apply_dispatch(dispatch, dt_h)

    def compute_record(self, state: Dict[str, Any], decision: Dict[str, Any], problem: MobilityDispatchProblem) -> MobilityExecRecord:
        step_operational_score = (
            0.30 * state["network_speed_index"] +
            0.20 * state["corridor_reliability_index"] +
            0.15 * (1.0 - state["bus_bunching_index"]) +
            0.15 * (1.0 - state["curb_pressure_index"]) +
            0.20 * (1.0 - state["risk_score"])
        )
        self.cumulative_operational_score += step_operational_score
        return MobilityExecRecord(
            step_id=self.step_id,
            ts=utc_now_iso(),
            mode=state["mode"],
            scenario=state["scenario"],
            active_event=state["active_event"],
            network_speed_index=state["network_speed_index"],
            corridor_reliability_index=state["corridor_reliability_index"],
            corridor_delay_s=state["corridor_delay_s"],
            bus_bunching_index=state["bus_bunching_index"],
            bus_commercial_speed_kmh=state["bus_commercial_speed_kmh"],
            bus_priority_requests=state["bus_priority_requests"],
            curb_occupancy_rate=state["curb_occupancy_rate"],
            illegal_curb_occupancy_rate=state["illegal_curb_occupancy_rate"],
            delivery_queue=state["delivery_queue"],
            risk_score=state["risk_score"],
            near_miss_index=state["near_miss_index"],
            pedestrian_exposure=state["pedestrian_exposure"],
            bike_conflict_index=state["bike_conflict_index"],
            gateway_delay_index=state["gateway_delay_index"],
            step_operational_score=step_operational_score,
            cumulative_operational_score=self.cumulative_operational_score,
            decision_route=decision["route"],
            decision_confidence=decision["confidence"],
            exec_ms=decision["exec_ms"],
            latency_breach=decision["latency_breach"],
            fallback_triggered=decision["fallback_triggered"],
            fallback_reasons=decision["fallback_reasons"],
            route_reason=decision["route_reason"],
            complexity_score=problem.complexity_score,
            discrete_ratio=problem.discrete_ratio,
            intersection_hotspot=state["intersection_hotspot"],
            road_corridor_hotspot=state["road_corridor_hotspot"],
            bus_corridor_hotspot=state["bus_corridor_hotspot"],
            curb_zone_hotspot=state["curb_zone_hotspot"],
            risk_hotspot_name=state["risk_hotspot_name"],
            primary_hotspot_name=state["primary_hotspot_name"],
            primary_hotspot_lat=state["primary_hotspot_lat"],
            primary_hotspot_lon=state["primary_hotspot_lon"],
            scenario_note=state["scenario_note"],
            qre_json=decision["qre_json"],
            result_json=decision["result_json"],
            dispatch_json=json.dumps(decision["dispatch"], ensure_ascii=False),
            objective_breakdown_json=json.dumps(decision["objective_breakdown"], ensure_ascii=False),
        )

    def step(self, dt_h: float = 5.0 / 60.0) -> MobilityExecRecord:
        self.step_id += 1
        ctx = self.get_context()
        self.update_telemetry(ctx)
        state = self.aggregate_state(ctx)
        problem = self.build_problem(state, ctx)
        decision = self.orchestrator.solve(state, problem)
        dispatch = self.validate_dispatch(decision["dispatch"], state)
        decision["dispatch"] = dispatch
        self.apply_dispatch(dispatch, dt_h)
        record = self.compute_record(state, decision, problem)
        self.records.append(record)
        return record

    def dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(r) for r in self.records])

    def latest_state(self) -> Dict[str, Any]:
        if not self.records:
            return {}
        return asdict(self.records[-1])

    def twin_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {k: v.snapshot() for k, v in self.twins.items()}

    def reset(self) -> None:
        scenario = self.scenario
        seed = self.seed
        hotspots_csv = self.hotspots_csv
        self.__init__(scenario=scenario, seed=seed, hotspots_csv=hotspots_csv)


def run_demo(steps: int = 48, scenario: ScenarioName = "corridor_congestion", seed: int = 42, hotspots_csv: Optional[str] = None) -> pd.DataFrame:
    rt = MobilityRuntime(scenario=scenario, seed=seed, hotspots_csv=hotspots_csv)
    for _ in range(steps):
        rt.step()
    return rt.dataframe()


if __name__ == "__main__":
    df = run_demo(steps=12, scenario="urban_logistics_saturation", seed=42)
    print(df.tail(3).to_string(index=False))
