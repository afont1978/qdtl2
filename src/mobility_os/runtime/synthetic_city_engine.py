
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np

from ..utils.io import load_json_data


@dataclass
class SyntheticCityEngine:
    seed: int = 42
    policy_profile: str = "balanced"

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self.demand_profiles = load_json_data('demand_profiles.json', default={})
        self.policy_profiles = load_json_data('policy_profiles.json', default={})

    def _is_in_window(self, hour: float, start: float, end: float) -> bool:
        if start <= end:
            return start <= hour <= end
        return hour >= start or hour <= end

    def generate_base_context(self, scenario: str, step_id: int, mode: str) -> Dict[str, Any]:
        hour = (step_id % 288) / 12.0
        default_profiles = self.demand_profiles.get('default', {})
        zones = self.demand_profiles.get('zones', {})

        zone_key = {
            'corridor_congestion': 'intermodal_core',
            'school_area_risk': 'city_centre',
            'urban_logistics_saturation': 'logistics_belt',
            'gateway_access_stress': 'gateway_access',
            'event_mobility': 'intermodal_core',
        }.get(scenario, 'intermodal_core')
        zone = zones.get(zone_key, {'corridor_base': 3600, 'ped_base': 550, 'bike_base': 220})

        peak = 1.0 if self._is_in_window(hour, 7.0, 10.0) or self._is_in_window(hour, 17.0, 20.0) else 0.0
        school_bonus = default_profiles.get('school_window', {}).get('pedestrian_bonus', 0.0) if self._is_in_window(hour, 7.0, 9.0) else 0.0
        logistics_bonus = default_profiles.get('logistics_window', {}).get('delivery_bonus', 0.0) if self._is_in_window(hour, 10.0, 15.0) else 0.0
        tourism_cfg = default_profiles.get('tourism_window', {})
        tourism_ped_bonus = tourism_cfg.get('pedestrian_bonus', 0.0) if self._is_in_window(hour, 11.0, 19.0) else 0.0
        tourism_pickup_bonus = tourism_cfg.get('pickup_dropoff_bonus', 0.0) if self._is_in_window(hour, 11.0, 19.0) else 0.0
        night_mult = default_profiles.get('night', {}).get('traffic_multiplier', 1.0) if self._is_in_window(hour, 22.0, 5.0) else 1.0

        corridor_flow = (zone['corridor_base'] + 1200.0 * peak + 420.0 * np.sin(hour / 24.0 * 2 * np.pi) + self.rng.normal(0, 110)) * night_mult
        ped_flow = zone['ped_base'] + 260.0 * peak + 180.0 * school_bonus + 110.0 * tourism_ped_bonus + 120.0 * np.sin((hour + 2.0) / 24.0 * 2 * np.pi) + self.rng.normal(0, 35)
        bike_flow = zone['bike_base'] + 110.0 * np.sin((hour - 1.5) / 24.0 * 2 * np.pi) + self.rng.normal(0, 22)

        headway_pressure = 0.34 + 0.24 * peak + self.rng.normal(0, 0.03)
        delivery_pressure = 0.28 + logistics_bonus + self.rng.normal(0, 0.03)
        illegal_pressure = 0.17 + 0.10 * (1.0 if self._is_in_window(hour, 11.0, 14.0) else 0.0) + self.rng.normal(0, 0.02)
        pickup_dropoff_pressure = 0.22 + 0.18 * peak + tourism_pickup_bonus + self.rng.normal(0, 0.02)
        gateway_surge = 0.14 + 0.17 * peak + self.rng.normal(0, 0.02)

        return {
            'hour': hour,
            'zone_key': zone_key,
            'weather': {'rain_intensity': 0.0, 'visibility': 0.95},
            'demand': {
                'corridor_flow_vph': float(max(1200.0, corridor_flow)),
                'ped_flow_pph': float(max(100.0, ped_flow)),
                'bike_flow_pph': float(max(60.0, bike_flow)),
            },
            'bus_ops': {
                'priority_requests': int(max(0, round(2 + 4 * peak + self.rng.normal(0, 1.0)))),
                'headway_pressure': float(np.clip(headway_pressure, 0.0, 1.0)),
            },
            'curb_ops': {
                'delivery_pressure': float(np.clip(delivery_pressure, 0.0, 1.0)),
                'illegal_parking_pressure': float(np.clip(illegal_pressure, 0.0, 1.0)),
                'pickup_dropoff_pressure': float(np.clip(pickup_dropoff_pressure, 0.0, 1.0)),
            },
            'gateway_ops': {'surge_factor': float(np.clip(gateway_surge, 0.0, 1.0))},
            'meta': {'policy_profile': self.policy_profile, 'zone_key': zone_key, 'hour': hour},
        }
