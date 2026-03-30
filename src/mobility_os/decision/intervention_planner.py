from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class InterventionPlan:
    action: str
    action_priority: str
    responsible_layer: str
    expected_impact: str
    dispatch_overrides: Dict[str, Any]


class InterventionPlanner:
    """
    Translates a subproblem into an operationally legible action.
    """

    def plan(self, state: Dict[str, Any], dominant_subproblem: str, route: str) -> InterventionPlan:
        hotspot = state.get("primary_hotspot_name", "selected hotspot")

        if dominant_subproblem == "pedestrian_protection_problem":
            return InterventionPlan(
                action=f"Activate pedestrian protection package around {hotspot}",
                action_priority="critical",
                responsible_layer="traffic_safety_control",
                expected_impact="Lower pedestrian exposure and slow down conflict escalation.",
                dispatch_overrides={
                    "ped_protection_mode": 1,
                    "speed_mitigation_mode": 1,
                    "preventive_alert_level": 2,
                },
            )
        if dominant_subproblem == "signal_coordination_problem":
            return InterventionPlan(
                action=f"Apply coordinated corridor signal plan at {hotspot}",
                action_priority="high",
                responsible_layer="corridor_traffic_control",
                expected_impact="Improve corridor speed and recover travel time reliability.",
                dispatch_overrides={
                    "signal_plan_id": 2,
                    "signal_coordination_mode": 2,
                    "offset_s": 8.0,
                },
            )
        if dominant_subproblem == "bus_priority_problem":
            return InterventionPlan(
                action=f"Reinforce bus priority and holding strategy at {hotspot}",
                action_priority="high",
                responsible_layer="transit_operations",
                expected_impact="Reduce bunching and stabilize bus headways.",
                dispatch_overrides={
                    "bus_priority_level": 2 if route == "CLASSICAL" else 3,
                    "holding_strategy": 1,
                    "dispatch_adjustment": 1,
                },
            )
        if dominant_subproblem in {"curb_allocation_problem", "delivery_slot_problem"}:
            return InterventionPlan(
                action=f"Reallocate curb rules and raise enforcement around {hotspot}",
                action_priority="high",
                responsible_layer="curbside_logistics_control",
                expected_impact="Reduce illegal occupancy and shorten delivery queues.",
                dispatch_overrides={
                    "curb_slot_policy": 2,
                    "enforcement_level": 2,
                    "access_window_mode": 2,
                },
            )
        if dominant_subproblem == "gateway_resource_problem":
            return InterventionPlan(
                action=f"Activate gateway metering and staging package at {hotspot}",
                action_priority="high",
                responsible_layer="gateway_flow_control",
                expected_impact="Contain access delay and smooth inbound pressure.",
                dispatch_overrides={
                    "diversion_mode": 2,
                    "signal_coordination_mode": 3,
                    "bus_priority_level": 2,
                },
            )
        if dominant_subproblem in {"incident_response_portfolio_problem", "event_release_rebalancing_problem", "multimodal_redispatch_problem"}:
            return InterventionPlan(
                action=f"Deploy coordinated incident/event response portfolio centred on {hotspot}",
                action_priority="high",
                responsible_layer="city_mobility_orchestration",
                expected_impact="Redistribute pressure across modes and prevent cascading degradation.",
                dispatch_overrides={
                    "diversion_mode": 2,
                    "signal_coordination_mode": 3,
                    "bus_priority_level": 2,
                    "preventive_alert_level": 1,
                },
            )

        return InterventionPlan(
            action=f"Maintain local tactical control at {hotspot}",
            action_priority="medium",
            responsible_layer="local_operations",
            expected_impact="Keep service quality within acceptable thresholds.",
            dispatch_overrides={},
        )
