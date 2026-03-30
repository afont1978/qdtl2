from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

import numpy as np
import pandas as pd

from ..twins.base import TwinBase
from ..twins.traffic_twins import IntersectionTwin, RoadCorridorTwin
from ..twins.transit_twins import BusCorridorTwin
from ..twins.logistics_twins import CurbZoneTwin
from ..twins.risk_twins import RiskHotspotTwin
from ..twins.gateway_twins import GatewayClusterTwin
from ..utils.io import Hotspot, load_hotspots_csv
from .state_aggregator import aggregate_city_state, propagate_twin_dependencies
from ..decision.situation_interpreter import SituationInterpreter
from ..decision.problem_decomposer import ProblemDecomposer
from ..decision.priority_arbiter import PriorityArbiter
from ..decision.route_selector import RouteSelector
from ..decision.intervention_planner import InterventionPlanner
from ..decision.validator import Validator
from ..decision.decision_memory import DecisionMemory

Mode = Literal["traffic", "safety", "logistics", "gateway", "event"]
ScenarioName = Literal[
    "corridor_congestion",
    "school_area_risk",
    "urban_logistics_saturation",
    "gateway_access_stress",
    "event_mobility",
]
Route = Literal["CLASSICAL", "QUANTUM", "FALLBACK_CLASSICAL"]
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
    situation_type: str = ""
    urgency: str = "low"
    dominant_objective: str = ""
    subproblem_type: str = ""


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
    situation_type: str = ""
    dominant_objective: str = ""
    subproblem_type: str = ""
    recommended_action: str = ""
    action_priority: str = ""
    responsible_layer: str = ""
    expected_impact: str = ""
    validation_status: str = ""
    expected_value_of_hybrid: float = 0.0
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
        self.route_selector = RouteSelector()

    def choose_route(self, state: Dict[str, Any], problem: MobilityDispatchProblem):
        problem_view = {
            "dominant_subproblem": problem.subproblem_type,
            "complexity_score": problem.complexity_score,
            "discrete_ratio": problem.discrete_ratio,
            "urgency": problem.urgency,
        }
        return self.route_selector.choose_route(state, problem_view)

    def solve(self, state: Dict[str, Any], problem: MobilityDispatchProblem) -> Dict[str, Any]:
        route_decision = self.choose_route(state, problem)
        route = route_decision.route
        reason = route_decision.route_reason

        if route == "CLASSICAL":
            dispatch, breakdown, confidence = self.classical.solve(state, problem)
            return {
                "route": "CLASSICAL",
                "route_reason": reason,
                "expected_value_of_hybrid": route_decision.expected_value_of_hybrid,
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
                "expected_value_of_hybrid": route_decision.expected_value_of_hybrid,
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
            "expected_value_of_hybrid": route_decision.expected_value_of_hybrid,
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
        self.hotspots: Dict[str, Hotspot] = load_hotspots_csv(hotspots_csv)
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
            "gateway_cluster": GatewayClusterTwin("gateway_cluster", "gateway_cluster", "Gateway Cluster", ts),
            "city_mobility_system": CityMobilitySystemTwin("city_mobility_system", "city_mobility_system", "City Mobility System", ts),
        }
        self._attach_hotspots_to_twins()

    def _hotspot(self, name: str) -> Optional[Hotspot]:
        return self.hotspots.get(name)

    def _scenario_hotspot_names(self) -> Dict[str, str]:
        mappings: Dict[ScenarioName, Dict[str, str]] = {
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
        }
        return mappings[self.scenario]

    def _scenario_note(self) -> str:
        notes = {
            "corridor_congestion": "Scenario anchored to Glòries as a primary corridor/interchange hotspot, with support nodes at Plaça de Catalunya and Plaça d'Espanya.",
            "school_area_risk": "No school-specific hotspot exists in the CSV yet, so the scenario uses Plaça de Catalunya as a high-pedestrian proxy hotspot until a school-zone layer is added.",
            "urban_logistics_saturation": "Scenario anchored to Plaça Cerdà, Ronda del Port VI and Port Vell as Barcelona logistics and curbside pressure nodes.",
            "gateway_access_stress": "Scenario anchored to airport terminals T1/T2 and cruise/port access nodes as Barcelona gateway hotspots.",
            "event_mobility": "Scenario anchored to Plaça d'Espanya, Plaça de Catalunya and Sants as high-pressure event and intermodal redistribution nodes.",
        }
        return notes[self.scenario]

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
        if self.scenario == "school_area_risk":
            return "safety"
        if self.scenario == "urban_logistics_saturation":
            return "logistics"
        if self.scenario == "gateway_access_stress":
            return "gateway"
        if self.scenario == "event_mobility":
            return "event"
        return "traffic"

    def _generate_base_context(self) -> ScenarioContext:
        mode = self._mode_for_scenario()
        hour = (self.step_id % 288) / 12.0
        peak = 1.0 if 7.0 <= hour <= 10.0 or 17.0 <= hour <= 20.0 else 0.0
        corridor_flow = 3600.0 + 1200.0 * peak + 450.0 * np.sin(hour / 24.0 * 2 * np.pi) + self.rng.normal(0, 120)
        ped_flow = 550.0 + 320.0 * peak + 120.0 * np.sin((hour + 2.0) / 24.0 * 2 * np.pi) + self.rng.normal(0, 40)
        bike_flow = 280.0 + 120.0 * np.sin((hour - 1.5) / 24.0 * 2 * np.pi) + self.rng.normal(0, 25)
        headway_pressure = 0.35 + 0.25 * peak + self.rng.normal(0, 0.03)
        delivery_pressure = 0.30 + 0.22 * (10.0 <= hour <= 15.0) + self.rng.normal(0, 0.03)
        illegal_pressure = 0.18 + 0.10 * (11.0 <= hour <= 14.0) + self.rng.normal(0, 0.02)
        pickup_dropoff_pressure = 0.22 + 0.18 * peak + self.rng.normal(0, 0.02)
        gateway_surge = 0.15 + 0.18 * peak + self.rng.normal(0, 0.02)
        return ScenarioContext(
            scenario=self.scenario,
            mode=mode,
            weather={"rain_intensity": 0.0, "visibility": 0.95},
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
        if self.scenario == "corridor_congestion":
            if self.step_id % 24 in range(7, 12):
                events.append(ScenarioEvent("demand_spike", 0.7, self.step_id, self.step_id, {}))
            if self.step_id % 31 in (15, 16):
                events.append(ScenarioEvent("bus_bunching", 0.6, self.step_id, self.step_id, {}))
        elif self.scenario == "school_area_risk":
            if self.step_id % 24 in range(7, 11):
                events.append(ScenarioEvent("school_peak", 0.9, self.step_id, self.step_id, {}))
            if self.step_id % 19 == 8:
                events.append(ScenarioEvent("rain_event", 0.4, self.step_id, self.step_id, {}))
        elif self.scenario == "urban_logistics_saturation":
            if self.step_id % 20 in range(8, 14):
                events.append(ScenarioEvent("delivery_wave", 0.85, self.step_id, self.step_id, {}))
            if self.step_id % 17 in (5, 6):
                events.append(ScenarioEvent("illegal_curb_occupation", 0.7, self.step_id, self.step_id, {}))
        elif self.scenario == "gateway_access_stress":
            if self.step_id % 22 in range(6, 11):
                events.append(ScenarioEvent("gateway_surge", 0.8, self.step_id, self.step_id, {}))
            if self.step_id % 29 == 12:
                events.append(ScenarioEvent("incident", 0.7, self.step_id, self.step_id, {}))
        elif self.scenario == "event_mobility":
            if self.step_id % 26 in range(12, 18):
                events.append(ScenarioEvent("event_release", 0.95, self.step_id, self.step_id, {}))
            if self.step_id % 18 in (9, 10):
                events.append(ScenarioEvent("bus_bunching", 0.65, self.step_id, self.step_id, {}))
            if self.step_id % 33 == 20:
                events.append(ScenarioEvent("rain_event", 0.45, self.step_id, self.step_id, {}))
        ctx.active_events = events
        for ev in events:
            if ev.event_type == "demand_spike":
                ctx.demand["corridor_flow_vph"] *= 1.18
            elif ev.event_type == "incident":
                ctx.demand["corridor_flow_vph"] *= 1.08
            elif ev.event_type == "school_peak":
                ctx.demand["ped_flow_pph"] *= 1.40
            elif ev.event_type == "rain_event":
                ctx.weather["rain_intensity"] = 0.45
                ctx.weather["visibility"] = 0.70
            elif ev.event_type == "bus_bunching":
                ctx.bus_ops["headway_pressure"] = min(1.0, ctx.bus_ops["headway_pressure"] + 0.25)
            elif ev.event_type == "illegal_curb_occupation":
                ctx.curb_ops["illegal_parking_pressure"] = min(1.0, ctx.curb_ops["illegal_parking_pressure"] + 0.35)
            elif ev.event_type == "delivery_wave":
                ctx.curb_ops["delivery_pressure"] = min(1.0, ctx.curb_ops["delivery_pressure"] + 0.35)
            elif ev.event_type == "gateway_surge":
                ctx.gateway_ops["surge_factor"] = min(1.0, ctx.gateway_ops["surge_factor"] + 0.45)
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

        situation = self.situation_interpreter.interpret(state)
        subproblems = self.problem_decomposer.decompose(state, situation)
        arbitration = self.priority_arbiter.arbitrate(state, situation, subproblems)
        dominant_subproblem = arbitration["dominant_subproblem"]

        constraints = {
            "network_speed_index": state["network_speed_index"],
            "corridor_reliability_index": state["corridor_reliability_index"],
            "bus_bunching_index": state["bus_bunching_index"],
            "curb_pressure_index": state["curb_pressure_index"],
            "risk_score": state["risk_score"],
            "gateway_delay_index": state["gateway_delay_index"],
        }
        objective_terms = {
            "delay_penalty_weight": arbitration["objective_weights"]["delay"],
            "bunching_penalty_weight": arbitration["objective_weights"]["transit"],
            "risk_penalty_weight": arbitration["objective_weights"]["risk"],
            "curb_penalty_weight": arbitration["objective_weights"]["logistics"],
            "gateway_penalty_weight": arbitration["objective_weights"]["gateway"],
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
            "subproblems": [sp.subproblem_type for sp in subproblems],
            "situation_notes": situation.notes,
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
            situation_type=situation.situation_type,
            urgency=situation.urgency,
            dominant_objective=situation.dominant_objective,
            subproblem_type=dominant_subproblem,
        )

    def validate_dispatch(self, dispatch: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        result = self.validator.validate(state, dispatch)
        return result.dispatch

    def apply_dispatch(self, dispatch: Dict[str, Any], dt_h: float) -> None:
        self.twins["intersection"].apply_dispatch(dispatch, dt_h)
        self.twins["road_corridor"].apply_dispatch(dispatch, dt_h)
        self.twins["bus_corridor"].apply_dispatch(dispatch, dt_h)
        self.twins["curb_zone"].apply_dispatch(dispatch, dt_h)
        self.twins["risk_hotspot"].apply_dispatch(dispatch, dt_h)

    def compute_record(
        self,
        state: Dict[str, Any],
        decision: Dict[str, Any],
        problem: MobilityDispatchProblem,
        intervention_plan,
        validation_result,
    ) -> MobilityExecRecord:
        step_operational_score = (
            0.30 * state["network_speed_index"]
            + 0.20 * state["corridor_reliability_index"]
            + 0.15 * (1.0 - state["bus_bunching_index"])
            + 0.15 * (1.0 - state["curb_pressure_index"])
            + 0.20 * (1.0 - state["risk_score"])
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
            city_pressure_score=state.get("city_pressure_score", 0.0),
            intersection_operational_status=state.get("intersection_operational_status", ""),
            road_corridor_operational_status=state.get("road_corridor_operational_status", ""),
            bus_corridor_operational_status=state.get("bus_corridor_operational_status", ""),
            curb_zone_operational_status=state.get("curb_zone_operational_status", ""),
            risk_hotspot_operational_status=state.get("risk_hotspot_operational_status", ""),
            intersection_pressure_level=state.get("intersection_pressure_level", ""),
            road_corridor_pressure_level=state.get("road_corridor_pressure_level", ""),
            bus_corridor_pressure_level=state.get("bus_corridor_pressure_level", ""),
            curb_zone_pressure_level=state.get("curb_zone_pressure_level", ""),
            risk_hotspot_pressure_level=state.get("risk_hotspot_pressure_level", ""),
            intersection_trend_state=state.get("intersection_trend_state", ""),
            road_corridor_trend_state=state.get("road_corridor_trend_state", ""),
            bus_corridor_trend_state=state.get("bus_corridor_trend_state", ""),
            curb_zone_trend_state=state.get("curb_zone_trend_state", ""),
            risk_hotspot_trend_state=state.get("risk_hotspot_trend_state", ""),
            step_operational_score=step_operational_score,
            cumulative_operational_score=self.cumulative_operational_score,
            decision_route=decision["route"],
            decision_confidence=decision["confidence"],
            exec_ms=decision["exec_ms"],
            latency_breach=decision["latency_breach"],
            fallback_triggered=decision["fallback_triggered"],
            fallback_reasons=decision["fallback_reasons"],
            route_reason=decision["route_reason"],
            situation_type=problem.situation_type,
            dominant_objective=problem.dominant_objective,
            subproblem_type=problem.subproblem_type,
            recommended_action=intervention_plan.action,
            action_priority=intervention_plan.action_priority,
            responsible_layer=intervention_plan.responsible_layer,
            expected_impact=intervention_plan.expected_impact,
            validation_status=validation_result.validation_status,
            expected_value_of_hybrid=decision.get("expected_value_of_hybrid", 0.0),
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

        intervention_plan = self.intervention_planner.plan(
            state=state,
            dominant_subproblem=problem.subproblem_type,
            route=decision["route"],
        )
        dispatch = {**decision["dispatch"], **intervention_plan.dispatch_overrides}
        validation_result = self.validator.validate(state, dispatch)
        dispatch = validation_result.dispatch

        decision["dispatch"] = dispatch
        self.apply_dispatch(dispatch, dt_h)
        record = self.compute_record(state, decision, problem, intervention_plan, validation_result)
        self.records.append(record)
        self.decision_memory.remember(
            {
                "step_id": self.step_id,
                "recommended_action": intervention_plan.action,
                "decision_route": decision["route"],
                "subproblem_type": problem.subproblem_type,
                "primary_hotspot_name": state["primary_hotspot_name"],
            }
        )
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
