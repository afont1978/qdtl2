from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .situation_interpreter import SituationSummary


@dataclass
class Subproblem:
    subproblem_type: str
    weight: float
    explanation: str


class ProblemDecomposer:
    """
    Splits a mobility situation into one or more concrete optimization/control
    subproblems. The strongest one becomes the dominant subproblem.
    """

    def decompose(self, state: Dict[str, Any], situation: SituationSummary) -> List[Subproblem]:
        active_event = state.get("active_event")
        subproblems: List[Subproblem] = []

        if situation.situation_type == "safety_protection":
            subproblems.append(Subproblem(
                "pedestrian_protection_problem",
                1.0,
                "Protect vulnerable users with immediate signal and calming measures."
            ))
            if active_event == "incident":
                subproblems.append(Subproblem(
                    "incident_response_portfolio_problem",
                    0.92,
                    "Coordinate diversion, signal protection and safety actions around the incident."
                ))

        if situation.situation_type in {"network_congestion", "transit_reliability"} or state.get("coordination_flag", False):
            subproblems.append(Subproblem(
                "signal_coordination_problem",
                0.82,
                "Coordinate signal plans and offsets to improve corridor performance."
            ))

        if state.get("bus_bunching_index", 0.0) >= 0.28:
            subproblems.append(Subproblem(
                "bus_priority_problem",
                0.86,
                "Improve bus headway regularity using tactical priority and holding."
            ))

        if situation.situation_type == "logistics_pressure" or state.get("logistics_pressure_flag", False):
            subproblems.append(Subproblem(
                "curb_allocation_problem",
                0.88,
                "Reallocate curbside rules and enforcement under logistics pressure."
            ))
            subproblems.append(Subproblem(
                "delivery_slot_problem",
                0.78,
                "Sequence urban deliveries to reduce curb conflict and queueing."
            ))

        if situation.situation_type == "gateway_coordination":
            subproblems.append(Subproblem(
                "gateway_resource_problem",
                0.90,
                "Coordinate gateway inflow, staging and access metering."
            ))
            subproblems.append(Subproblem(
                "airport_access_multimodal_problem",
                0.84,
                "Coordinate gateway, rail and bus access around airport/port pressure."
            ))
            subproblems.append(Subproblem(
                "multimodal_redispatch_problem",
                0.76,
                "Rebalance arrivals across modes and surrounding corridors."
            ))

        if active_event == "event_release":
            subproblems.append(Subproblem(
                "event_release_rebalancing_problem",
                0.88,
                "Disperse post-event demand through tactical multimodal measures."
            ))
            subproblems.append(Subproblem(
                "event_evacuation_multimodal_problem",
                0.80,
                "Use rail, bus and pedestrian management to evacuate demand through interchanges."
            ))

        if state.get("urban_rail_burden", 0.0) > 0.48 or state.get("interchange_pressure_index", 0.0) > 0.50:
            subproblems.append(Subproblem(
                "interchange_overload_problem",
                0.84,
                "Manage transfer load, pedestrian waves and multimodal access at major hubs."
            ))
            subproblems.append(Subproblem(
                "rail_load_balancing_problem",
                0.78,
                "Redistribute rail demand and relieve the most pressured subsystem."
            ))
        if state.get("rail_disruption_pressure", 0.0) > 0.32:
            subproblems.append(Subproblem(
                "rail_disruption_response_problem",
                0.82,
                "Coordinate tactical mitigation for degraded rail operations."
            ))

        if not subproblems:
            subproblems.append(Subproblem(
                "local_tactical_adjustment",
                0.55,
                "Apply limited deterministic adjustment to maintain service quality."
            ))

        subproblems.sort(key=lambda sp: sp.weight, reverse=True)
        return subproblems
