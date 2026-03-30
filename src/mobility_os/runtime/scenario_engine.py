from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..utils.io import load_json_data


@dataclass
class ScenarioEngine:
    """
    Loads the base scenario library and, if present, an additional high-complexity
    scenario library. Both catalogs are merged in memory so the project can keep
    them as separate JSON files.

    Merge policy:
    - base library is loaded first
    - high-complexity library is loaded second
    - if a scenario key exists in both, the high-complexity version wins
    """
    base_library_filename: str = "scenario_library.json"
    extra_library_filename: str = "scenario_library_high_complexity_v2.json"
    scenario_library: Dict[str, Any] = field(init=False, default_factory=dict)
    scenario_sources: Dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.scenario_library, self.scenario_sources = self._load_merged_library()

    def _load_merged_library(self) -> tuple[Dict[str, Any], Dict[str, str]]:
        merged: Dict[str, Any] = {}
        sources: Dict[str, str] = {}

        base = load_json_data(self.base_library_filename, default={})
        if isinstance(base, dict):
            merged.update(base)
            for key in base.keys():
                sources[key] = self.base_library_filename

        extra = load_json_data(self.extra_library_filename, default={})
        if isinstance(extra, dict):
            merged.update(extra)
            for key in extra.keys():
                sources[key] = self.extra_library_filename

        return merged, sources

    def list_available_scenarios(self) -> List[str]:
        return sorted(self.scenario_library.keys())

    def scenario_source(self, scenario: str) -> str:
        return self.scenario_sources.get(scenario, self.base_library_filename)

    def mode_for_scenario(self, scenario: str) -> str:
        return self.scenario_library.get(scenario, {}).get("mode", "traffic")

    def build_events(self, scenario: str, step_id: int):
        return self.scenario_library.get(scenario, {}).get("event_schedule", {})

    def apply(self, scenario: str, step_id: int, ctx: Any, event_factory):
        config = self.scenario_library.get(scenario, {})
        schedule = config.get("event_schedule", {})
        shocks = config.get("shocks", {})
        events: List[Any] = []

        for event_type, rule in schedule.items():
            mod = int(rule.get("mod", 1))
            active = False

            if "range" in rule:
                start, end = rule["range"]
                active = (step_id % mod) in range(start, end + 1)
            elif "points" in rule:
                active = (step_id % mod) in set(rule["points"])

            if not active:
                continue

            events.append(
                event_factory(
                    event_type,
                    float(rule.get("severity", 0.5)),
                    step_id,
                    step_id,
                    {},
                )
            )

            shock = shocks.get(event_type, {})

            if "corridor_flow_multiplier" in shock:
                ctx.demand["corridor_flow_vph"] *= shock["corridor_flow_multiplier"]
            if "ped_flow_multiplier" in shock:
                ctx.demand["ped_flow_pph"] *= shock["ped_flow_multiplier"]
            if "bike_flow_multiplier" in shock:
                ctx.demand["bike_flow_pph"] *= shock["bike_flow_multiplier"]

            if "headway_pressure_add" in shock:
                ctx.bus_ops["headway_pressure"] = min(
                    1.0,
                    ctx.bus_ops["headway_pressure"] + shock["headway_pressure_add"],
                )
            if "priority_requests_add" in shock:
                ctx.bus_ops["priority_requests"] += int(shock["priority_requests_add"])

            if "delivery_pressure_add" in shock:
                ctx.curb_ops["delivery_pressure"] = min(
                    1.0,
                    ctx.curb_ops["delivery_pressure"] + shock["delivery_pressure_add"],
                )
            if "illegal_parking_pressure_add" in shock:
                ctx.curb_ops["illegal_parking_pressure"] = min(
                    1.0,
                    ctx.curb_ops["illegal_parking_pressure"] + shock["illegal_parking_pressure_add"],
                )
            if "pickup_dropoff_pressure_add" in shock:
                ctx.curb_ops["pickup_dropoff_pressure"] = min(
                    1.0,
                    ctx.curb_ops["pickup_dropoff_pressure"] + shock["pickup_dropoff_pressure_add"],
                )

            if "gateway_surge_add" in shock:
                ctx.gateway_ops["surge_factor"] = min(
                    1.0,
                    ctx.gateway_ops["surge_factor"] + shock["gateway_surge_add"],
                )

            if "rain_intensity" in shock:
                ctx.weather["rain_intensity"] = shock["rain_intensity"]
            if "visibility" in shock:
                ctx.weather["visibility"] = shock["visibility"]

        ctx.active_events = events
        return ctx
