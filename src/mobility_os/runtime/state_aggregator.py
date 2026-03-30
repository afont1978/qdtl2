
from __future__ import annotations

from typing import Any, Dict

import numpy as np

from ..twins.traffic_twins import IntersectionTwin, RoadCorridorTwin
from ..twins.transit_twins import BusCorridorTwin
from ..twins.logistics_twins import CurbZoneTwin
from ..twins.risk_twins import RiskHotspotTwin
from ..twins.gateway_twins import GatewayClusterTwin


def propagate_twin_dependencies(twins: Dict[str, Any], ctx: Any) -> None:
    """
    Lightweight propagation layer for Sprint 3.
    It does not simulate a full graph yet; it propagates pressure proxies between core twins.
    """
    corridor = twins["road_corridor"]
    bus = twins["bus_corridor"]
    curb = twins["curb_zone"]
    risk = twins["risk_hotspot"]
    intersection = twins["intersection"]
    gateway = twins.get("gateway_cluster")

    assert isinstance(corridor, RoadCorridorTwin)
    assert isinstance(bus, BusCorridorTwin)
    assert isinstance(curb, CurbZoneTwin)
    assert isinstance(risk, RiskHotspotTwin)
    assert isinstance(intersection, IntersectionTwin)
    if gateway is not None:
        assert isinstance(gateway, GatewayClusterTwin)

    # 1st pass dependencies from context to twins before stepping again
    gateway_pressure = float(ctx.gateway_ops.get("surge_factor", 0.0))
    corridor.connected_gateway_pressure = gateway_pressure
    intersection.connected_corridor_pressure = float(np.clip(corridor.queue_spillback_risk, 0.0, 1.0))
    bus.connected_corridor_delay = float(np.clip(corridor.travel_time_index * 15.0, 0.0, 100.0))
    curb.connected_gateway_pressure = gateway_pressure
    risk.connected_curb_conflict = float(np.clip(curb.pedestrian_conflict_score, 0.0, 1.0))
    risk.connected_intersection_risk = float(np.clip(intersection.risk_score, 0.0, 1.0))


def aggregate_city_state(runtime: Any, ctx: Any) -> Dict[str, Any]:
    inter = runtime.twins["intersection"]
    corridor = runtime.twins["road_corridor"]
    bus = runtime.twins["bus_corridor"]
    curb = runtime.twins["curb_zone"]
    risk = runtime.twins["risk_hotspot"]
    gateway = runtime.twins.get("gateway_cluster")

    assert isinstance(inter, IntersectionTwin)
    assert isinstance(corridor, RoadCorridorTwin)
    assert isinstance(bus, BusCorridorTwin)
    assert isinstance(curb, CurbZoneTwin)
    assert isinstance(risk, RiskHotspotTwin)
    if gateway is not None:
        assert isinstance(gateway, GatewayClusterTwin)

    active_event = ctx.active_events[0].event_type if ctx.active_events else None
    network_speed_index = float(np.clip(corridor.avg_speed_kmh / 32.0, 0.0, 1.2))
    corridor_reliability_index = float(np.clip(1.0 / corridor.travel_time_index, 0.0, 1.2))
    curb_pressure_index = float(np.clip(0.55 * curb.occupancy_rate + 0.45 * curb.illegal_occupancy_rate, 0.0, 1.0))
    gateway_delay_index = float(gateway.delay_index if gateway is not None else np.clip(0.18 + 0.65 * ctx.gateway_ops["surge_factor"] + 0.12 * corridor.queue_spillback_risk, 0.0, 1.0))
    coordination_flag = bus.bunching_index > 0.28 and corridor.queue_spillback_risk > 0.35
    logistics_pressure_flag = curb.delivery_queue > 8.0 or curb.illegal_occupancy_rate > 0.22
    hotspot_map = runtime._scenario_hotspot_names()
    primary_name = hotspot_map["road_corridor"]
    primary_hotspot = runtime._hotspot(primary_name)

    city_pressure_score = float(np.clip(
        0.24 * (1.0 - network_speed_index)
        + 0.18 * bus.bunching_index
        + 0.18 * curb_pressure_index
        + 0.22 * risk.risk_score
        + 0.18 * gateway_delay_index,
        0.0,
        1.0,
    ))

    return {
        "ts": runtime.utc_now_iso() if hasattr(runtime, "utc_now_iso") else "",
        "mode": ctx.mode,
        "scenario": ctx.scenario,
        "scenario_note": runtime._scenario_note(),
        "active_event": active_event,
        "intersection_hotspot": hotspot_map["intersection"],
        "road_corridor_hotspot": hotspot_map["road_corridor"],
        "bus_corridor_hotspot": hotspot_map["bus_corridor"],
        "curb_zone_hotspot": hotspot_map["curb_zone"],
        "risk_hotspot_name": hotspot_map["risk_hotspot"],
        "primary_hotspot_name": primary_name,
        "primary_hotspot_lat": primary_hotspot.lat if primary_hotspot else 41.3851,
        "primary_hotspot_lon": primary_hotspot.lon if primary_hotspot else 2.1734,
        "network_speed_index": network_speed_index,
        "corridor_reliability_index": corridor_reliability_index,
        "corridor_delay_s": corridor.travel_time_index * 75.0,
        "bus_bunching_index": bus.bunching_index,
        "bus_commercial_speed_kmh": bus.commercial_speed_kmh,
        "bus_priority_requests": bus.priority_requests_active,
        "curb_occupancy_rate": curb.occupancy_rate,
        "illegal_curb_occupancy_rate": curb.illegal_occupancy_rate,
        "delivery_queue": curb.delivery_queue,
        "curb_pressure_index": curb_pressure_index,
        "risk_score": risk.risk_score,
        "near_miss_index": risk.near_miss_index,
        "pedestrian_exposure": risk.pedestrian_exposure,
        "bike_conflict_index": risk.bike_conflict_index,
        "gateway_delay_index": gateway_delay_index,
        "coordination_flag": coordination_flag,
        "logistics_pressure_flag": logistics_pressure_flag,
        "rain_flag": ctx.weather["rain_intensity"] > 0.20,
        "school_peak_flag": active_event == "school_peak",
        "incident_flag": active_event == "incident",
        "delivery_wave_flag": active_event == "delivery_wave",
        "gateway_surge_flag": active_event == "gateway_surge",
        "city_pressure_score": city_pressure_score,
        "intersection_operational_status": inter.operational_status,
        "road_corridor_operational_status": corridor.operational_status,
        "bus_corridor_operational_status": bus.operational_status,
        "curb_zone_operational_status": curb.operational_status,
        "risk_hotspot_operational_status": risk.operational_status,
        "intersection_pressure_level": inter.pressure_level,
        "road_corridor_pressure_level": corridor.pressure_level,
        "bus_corridor_pressure_level": bus.pressure_level,
        "curb_zone_pressure_level": curb.pressure_level,
        "risk_hotspot_pressure_level": risk.pressure_level,
        "intersection_trend_state": inter.trend_state,
        "road_corridor_trend_state": corridor.trend_state,
        "bus_corridor_trend_state": bus.trend_state,
        "curb_zone_trend_state": curb.trend_state,
        "risk_hotspot_trend_state": risk.trend_state,
    }
