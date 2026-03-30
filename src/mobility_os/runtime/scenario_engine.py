
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ..utils.io import load_json_data


@dataclass
class ScenarioEngine:
    def __post_init__(self) -> None:
        base_library = load_json_data('scenario_library.json', default={})
        advanced_library = load_json_data('scenario_library_high_complexity_v2.json', default={})
        self.scenario_library = {**base_library, **advanced_library}

    def mode_for_scenario(self, scenario: str) -> str:
        return self.scenario_library.get(scenario, {}).get('mode', 'traffic')

    def build_events(self, scenario: str, step_id: int):
        return self.scenario_library.get(scenario, {}).get('event_schedule', {})

    def apply(self, scenario: str, step_id: int, ctx: Any, event_factory):
        config = self.scenario_library.get(scenario, {})
        schedule = config.get('event_schedule', {})
        shocks = config.get('shocks', {})
        events: List[Any] = []
        for event_type, rule in schedule.items():
            mod = int(rule.get('mod', 1))
            active = False
            if 'range' in rule:
                start, end = rule['range']
                active = (step_id % mod) in range(start, end + 1)
            elif 'points' in rule:
                active = (step_id % mod) in set(rule['points'])
            if not active:
                continue
            events.append(event_factory(event_type, float(rule.get('severity', 0.5)), step_id, step_id, {}))
            shock = shocks.get(event_type, {})
            if 'corridor_flow_multiplier' in shock:
                ctx.demand['corridor_flow_vph'] *= shock['corridor_flow_multiplier']
            if 'ped_flow_multiplier' in shock:
                ctx.demand['ped_flow_pph'] *= shock['ped_flow_multiplier']
            if 'bike_flow_multiplier' in shock:
                ctx.demand['bike_flow_pph'] *= shock['bike_flow_multiplier']
            if 'headway_pressure_add' in shock:
                ctx.bus_ops['headway_pressure'] = min(1.0, ctx.bus_ops['headway_pressure'] + shock['headway_pressure_add'])
            if 'priority_requests_add' in shock:
                ctx.bus_ops['priority_requests'] += int(shock['priority_requests_add'])
            if 'delivery_pressure_add' in shock:
                ctx.curb_ops['delivery_pressure'] = min(1.0, ctx.curb_ops['delivery_pressure'] + shock['delivery_pressure_add'])
            if 'illegal_parking_pressure_add' in shock:
                ctx.curb_ops['illegal_parking_pressure'] = min(1.0, ctx.curb_ops['illegal_parking_pressure'] + shock['illegal_parking_pressure_add'])
            if 'pickup_dropoff_pressure_add' in shock:
                ctx.curb_ops['pickup_dropoff_pressure'] = min(1.0, ctx.curb_ops['pickup_dropoff_pressure'] + shock['pickup_dropoff_pressure_add'])
            if 'gateway_surge_add' in shock:
                ctx.gateway_ops['surge_factor'] = min(1.0, ctx.gateway_ops['surge_factor'] + shock['gateway_surge_add'])

            if 'metro_load_add' in shock:
                ctx.rail_ops['metro_load'] = min(1.0, ctx.rail_ops['metro_load'] + shock['metro_load_add'])
            if 'rodalies_load_add' in shock:
                ctx.rail_ops['rodalies_load'] = min(1.0, ctx.rail_ops['rodalies_load'] + shock['rodalies_load_add'])
            if 'fgc_load_add' in shock:
                ctx.rail_ops['fgc_load'] = min(1.0, ctx.rail_ops['fgc_load'] + shock['fgc_load_add'])
            if 'interchange_pressure_add' in shock:
                ctx.rail_ops['interchange_pressure'] = min(1.0, ctx.rail_ops['interchange_pressure'] + shock['interchange_pressure_add'])
            if 'airport_rail_pressure_add' in shock:
                ctx.rail_ops['airport_rail_pressure'] = min(1.0, ctx.rail_ops['airport_rail_pressure'] + shock['airport_rail_pressure_add'])
            if 'pedestrian_wave_add' in shock:
                ctx.interchange_ops['pedestrian_wave'] = min(1.0, ctx.interchange_ops['pedestrian_wave'] + shock['pedestrian_wave_add'])
            if 'crowd_management_readiness_add' in shock:
                ctx.interchange_ops['crowd_management_readiness'] = min(1.0, ctx.interchange_ops['crowd_management_readiness'] + shock['crowd_management_readiness_add'])
            if 'rain_intensity' in shock:
                ctx.weather['rain_intensity'] = shock['rain_intensity']
            if 'visibility' in shock:
                ctx.weather['visibility'] = shock['visibility']
        ctx.active_events = events
        return ctx
