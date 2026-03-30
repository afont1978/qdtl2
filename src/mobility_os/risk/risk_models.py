from __future__ import annotations

from typing import Any, Dict

import numpy as np


def compute_risk_components(state: Dict[str, Any]) -> Dict[str, float]:
    """Compute multicomponent urban risk scores from aggregated city state."""
    pedestrian = float(np.clip(0.55 * state.get("pedestrian_exposure", 0.0) + 0.20 * state.get("risk_score", 0.0), 0.0, 1.0))
    bike = float(np.clip(0.70 * state.get("bike_conflict_index", 0.0) + 0.10 * state.get("risk_score", 0.0), 0.0, 1.0))
    motorcycle = float(np.clip(0.45 * state.get("risk_score", 0.0) + 0.15 * state.get("bus_bunching_index", 0.0) + 0.10 * state.get("rain_flag", False), 0.0, 1.0))
    bus_conflict = float(np.clip(0.55 * state.get("bus_bunching_index", 0.0) + 0.25 * (1.0 - state.get("network_speed_index", 1.0)), 0.0, 1.0))
    logistics_conflict = float(np.clip(0.50 * state.get("curb_pressure_index", 0.0) + 0.30 * state.get("illegal_curb_occupancy_rate", 0.0), 0.0, 1.0))
    gateway = float(np.clip(0.80 * state.get("gateway_delay_index", 0.0), 0.0, 1.0))
    weather = float(0.55 if state.get("rain_flag", False) else 0.08)
    return {
        "pedestrian_risk": pedestrian,
        "bike_risk": bike,
        "motorcycle_risk": motorcycle,
        "bus_conflict_risk": bus_conflict,
        "logistics_conflict_risk": logistics_conflict,
        "gateway_risk": gateway,
        "weather_risk": weather,
    }


def compute_risk_burden(components: Dict[str, float]) -> float:
    weights = {
        "pedestrian_risk": 0.22,
        "bike_risk": 0.10,
        "motorcycle_risk": 0.10,
        "bus_conflict_risk": 0.16,
        "logistics_conflict_risk": 0.16,
        "gateway_risk": 0.16,
        "weather_risk": 0.10,
    }
    return float(np.clip(sum(components[k] * weights[k] for k in weights), 0.0, 1.0))


def dominant_risk_type(components: Dict[str, float]) -> str:
    if not components:
        return "none"
    return max(components.items(), key=lambda kv: kv[1])[0]
