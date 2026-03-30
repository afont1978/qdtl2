
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ..utils.io import load_json_data


def _normalize_library(raw: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    # Base library already comes as {scenario_id: config}
    if 'scenarios' not in raw:
        return {k: v for k, v in raw.items() if isinstance(v, dict)}
    # Advanced library comes as metadata + scenarios: [ ... ]
    out: Dict[str, Dict[str, Any]] = {}
    scenarios = raw.get('scenarios', [])
    if isinstance(scenarios, list):
        for item in scenarios:
            if not isinstance(item, dict):
                continue
            sid = item.get('id')
            if sid:
                out[str(sid)] = item
    return out


@dataclass
class ScenarioEngine:
    def __post_init__(self) -> None:
        base_library_raw = load_json_data('scenario_library.json', default={})
        advanced_library_raw = load_json_data('scenario_library_high_complexity_v2.json', default={})
        base_library = _normalize_library(base_library_raw)
        advanced_library = _normalize_library(advanced_library_raw)
        self.scenario_library: Dict[str, Dict[str, Any]] = {**base_library, **advanced_library}

    def list_available_scenarios(self) -> List[str]:
        return list(self.scenario_library.keys())

    def scenario_source(self, scenario: str) -> str:
        cfg = self.scenario_library.get(scenario, {})
        return 'advanced' if 'complexity' in cfg or 'primary_hotspots' in cfg else 'base'

    def mode_for_scenario(self, scenario: str) -> str:
        cfg = self.scenario_library.get(scenario, {})
        if 'mode' in cfg:
            return cfg.get('mode', 'traffic')
        # infer mode for advanced scenarios
        sid = str(scenario)
        if any(k in sid for k in ['school', 'visibility']):
            return 'safety'
        if any(k in sid for k in ['logistics', 'truck', 'port']):
            return 'logistics'
        if any(k in sid for k in ['airport', 'gateway']):
            return 'gateway'
        if any(k in sid for k in ['event', 'tourism', 'extreme']):
            return 'event'
        return 'traffic'

    def build_events(self, scenario: str, step_id: int):
        return self.scenario_library.get(scenario, {}).get('event_schedule', {})

    def apply(self, scenario: str, step_id: int, ctx: Any, event_factory):
        config = self.scenario_library.get(scenario, {})
        schedule = config.get('event_schedule', {})
        shocks = config.get('shocks', {})
        # derive schedule/shocks from advanced format if needed
        if not schedule and 'trigger_events' in config:
            for idx, ev in enumerate(config.get('trigger_events', [])):
                if isinstance(ev, str):
                    schedule[ev] = {'mod': max(12, 18 + idx * 3), 'points': [6 + idx], 'severity': 0.6}
        if not shocks and 'disturbances' in config:
            dist = config.get('disturbances', {}) or {}
            shocks = {k: v for k, v in dist.items() if isinstance(v, (int, float))}
        events: List[Any] = []
        for event_type, rule in schedule.items():
            if not isinstance(rule, dict):
                continue
            mod = int(rule.get('mod', 1))
            active = False
            if 'range' in rule:
                start, end = rule['range']
                active = (step_id % mod) in range(start, end + 1)
            elif 'points' in rule:
                active = (step_id % mod) in set(rule['points'])
            if not active:
                continue
            events.append(event_factory(event_type, float(rule.get('severity', 0.5)), step_id, step_id, rule))
        # apply shocks multiplicatively to matching keys when present
        for key, factor in shocks.items():
            if not isinstance(factor, (int, float)):
                continue
            if key in getattr(ctx, 'demand', {}):
                ctx.demand[key] *= float(factor)
            elif key in getattr(ctx, 'bus_ops', {}):
                ctx.bus_ops[key] *= float(factor)
            elif key in getattr(ctx, 'curb_ops', {}):
                ctx.curb_ops[key] *= float(factor)
            elif key in getattr(ctx, 'gateway_ops', {}):
                ctx.gateway_ops[key] *= float(factor)
            elif key in getattr(ctx, 'rail_ops', {}):
                ctx.rail_ops[key] *= float(factor)
            elif key in getattr(ctx, 'interchange_ops', {}):
                ctx.interchange_ops[key] *= float(factor)
        ctx.active_events = events
        return ctx
