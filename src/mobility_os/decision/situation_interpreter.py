from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

Mode = Literal["traffic", "safety", "logistics", "gateway", "event"]


@dataclass
class SituationSummary:
    situation_type: str
    severity: float
    urgency: str
    dominant_objective: str
    scope: str
    notes: str


class SituationInterpreter:
    """
    Reads the aggregated urban state and translates it into an operational
    interpretation that can be reasoned about by the rest of the decision stack.
    """

    def interpret(self, state: Dict[str, Any]) -> SituationSummary:
        active_event = state.get("active_event")
        risk = float(state.get("risk_score", 0.0))
        bunching = float(state.get("bus_bunching_index", 0.0))
        curb_pressure = float(state.get("curb_pressure_index", 0.0))
        gateway_delay = float(state.get("gateway_delay_index", 0.0))
        network_speed = float(state.get("network_speed_index", 1.0))
        mode: Mode = state.get("mode", "traffic")

        severity = max(
            risk,
            bunching,
            curb_pressure,
            gateway_delay,
            1.0 - min(network_speed, 1.0),
        )

        if active_event in {"incident", "school_peak"} or (mode == "safety" and risk >= 0.55):
            situation_type = "safety_protection"
            dominant_objective = "protect_vulnerable_users"
            urgency = "immediate"
            scope = "local" if active_event == "school_peak" else "network"
            notes = "Safety conditions dominate the decision stack."
        elif active_event in {"delivery_wave", "illegal_curb_occupation"} or curb_pressure >= 0.55 or mode == "logistics":
            situation_type = "logistics_pressure"
            dominant_objective = "restore_curbside_and_delivery_flow"
            urgency = "high"
            scope = "district"
            notes = "Urban logistics and curbside tension dominate the system."
        elif active_event in {"gateway_surge", "event_release"} or gateway_delay >= 0.55 or mode == "gateway":
            situation_type = "gateway_coordination"
            dominant_objective = "contain_access_delay_and_rebalance_arrivals"
            urgency = "high"
            scope = "gateway"
            notes = "Gateway access must be coordinated with the surrounding corridor network."
        elif bunching >= 0.32:
            situation_type = "transit_reliability"
            dominant_objective = "stabilize_bus_headways"
            urgency = "medium"
            scope = "corridor"
            notes = "Transit performance is degraded and requires tactical intervention."
        elif network_speed <= 0.62:
            situation_type = "network_congestion"
            dominant_objective = "reduce_delay_and_restore_flow"
            urgency = "medium"
            scope = "corridor"
            notes = "Traffic coordination is required to recover corridor performance."
        else:
            situation_type = "steady_state"
            dominant_objective = "maintain_service_quality"
            urgency = "low"
            scope = "local"
            notes = "The system remains manageable with limited intervention."

        return SituationSummary(
            situation_type=situation_type,
            severity=float(round(severity, 4)),
            urgency=urgency,
            dominant_objective=dominant_objective,
            scope=scope,
            notes=notes,
        )
