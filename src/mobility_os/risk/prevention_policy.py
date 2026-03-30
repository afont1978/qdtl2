from __future__ import annotations

from typing import Any, Dict


def recommend_prevention(state: Dict[str, Any], components: Dict[str, float], phase: str) -> Dict[str, str]:
    dominant = max(components.items(), key=lambda kv: kv[1])[0] if components else "none"
    hotspot = state.get("primary_hotspot_name", "selected hotspot")

    if phase in {"critical", "active"} and dominant == "pedestrian_risk":
        return {
            "preventive_action_recommended": f"Activate pedestrian protection and speed mitigation at {hotspot}",
            "preventive_priority": "high",
            "preventive_layer": "safety",
        }
    if phase in {"active", "emerging"} and dominant == "bus_conflict_risk":
        return {
            "preventive_action_recommended": f"Increase coordinated bus priority and holding discipline around {hotspot}",
            "preventive_priority": "medium",
            "preventive_layer": "transit",
        }
    if phase in {"active", "emerging"} and dominant == "logistics_conflict_risk":
        return {
            "preventive_action_recommended": f"Tighten curbside enforcement and reallocate DUM slots near {hotspot}",
            "preventive_priority": "medium",
            "preventive_layer": "logistics",
        }
    if phase in {"active", "critical"} and dominant == "gateway_risk":
        return {
            "preventive_action_recommended": f"Activate metering and staging package for gateway flows linked to {hotspot}",
            "preventive_priority": "high",
            "preventive_layer": "gateway",
        }
    if phase == "stabilizing":
        return {
            "preventive_action_recommended": f"Maintain current preventive measures and monitor stabilization at {hotspot}",
            "preventive_priority": "watch",
            "preventive_layer": "orchestration",
        }
    return {
        "preventive_action_recommended": f"Continue monitoring {hotspot}; no extra preventive action required now",
        "preventive_priority": "low",
        "preventive_layer": "monitoring",
    }
