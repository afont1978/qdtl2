from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple, Literal

Route = Literal["CLASSICAL", "QUANTUM", "FALLBACK_CLASSICAL"]


@dataclass
class RouteDecision:
    route: Route
    route_reason: str
    expected_value_of_hybrid: float


class RouteSelector:
    """
    Selects the execution route using situation, dominant subproblem, urgency,
    complexity and system pressure.
    """

    def choose_route(
        self,
        state: Dict[str, Any],
        problem: Dict[str, Any],
    ) -> RouteDecision:
        mode = state.get("mode", "traffic")
        risk = float(state.get("risk_score", 0.0))
        active_event = state.get("active_event")
        dominant_subproblem = problem.get("dominant_subproblem", "local_tactical_adjustment")
        complexity = float(problem.get("complexity_score", 0.0))
        discrete_ratio = float(problem.get("discrete_ratio", 0.0))
        urgency = problem.get("urgency", "low")
        expected_value_of_hybrid = 0.0

        if mode == "safety" and (risk > 0.58 or active_event in {"school_peak", "incident"}):
            return RouteDecision(
                route="CLASSICAL",
                route_reason="Classical selected because the step is in immediate safety protection mode.",
                expected_value_of_hybrid=0.12,
            )

        if complexity < 4.9 or discrete_ratio < 0.40:
            return RouteDecision(
                route="CLASSICAL",
                route_reason="Classical selected because the decision space is still limited.",
                expected_value_of_hybrid=0.18,
            )

        hybrid_friendly_subproblems = {
            "signal_coordination_problem",
            "bus_priority_problem",
            "curb_allocation_problem",
            "delivery_slot_problem",
            "gateway_resource_problem",
            "incident_response_portfolio_problem",
            "event_release_rebalancing_problem",
            "multimodal_redispatch_problem",
        }

        if dominant_subproblem in hybrid_friendly_subproblems and urgency != "immediate":
            expected_value_of_hybrid = min(0.75, 0.18 + 0.06 * complexity + 0.20 * discrete_ratio)
            return RouteDecision(
                route="QUANTUM",
                route_reason=f"Quantum selected because {dominant_subproblem.replace('_', ' ')} requires a more combinatorial coordination window.",
                expected_value_of_hybrid=float(round(expected_value_of_hybrid, 3)),
            )

        return RouteDecision(
            route="CLASSICAL",
            route_reason="Classical selected because deterministic coordination is sufficient for the current step.",
            expected_value_of_hybrid=0.16,
        )
