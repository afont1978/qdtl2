
from __future__ import annotations

from typing import Any, Dict

import numpy as np

from ..twins.traffic_twins import IntersectionTwin, RoadCorridorTwin
from ..twins.transit_twins import BusCorridorTwin
from ..twins.logistics_twins import CurbZoneTwin
from ..twins.risk_twins import RiskHotspotTwin
from ..twins.gateway_twins import GatewayClusterTwin
from ..twins.rail_twins import MetroStationTwin, MetroLineTwin, RodaliesStationTwin, RodaliesLineTwin, FGCStationTwin, FGCLineTwin
from ..twins.interchange_twins import InterchangeNodeTwin
from ..risk.risk_models import compute_risk_components, compute_risk_burden, dominant_risk_type
from ..risk.risk_state_machine import determine_risk_phase
from ..risk.risk_forecast import forecast_risk_short
from ..risk.prevention_policy import recommend_prevention


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
    metro_station = twins.get("metro_station")
    metro_line = twins.get("metro_line")
    rod_station = twins.get("rodalies_station")
    rod_line = twins.get("rodalies_line")
    fgc_station = twins.get("fgc_station")
    fgc_line = twins.get("fgc_line")
    interchange = twins.get("interchange_node")

    assert isinstance(corridor, RoadCorridorTwin)
    assert isinstance(bus, BusCorridorTwin)
    assert isinstance(curb, CurbZoneTwin)
    assert isinstance(risk, RiskHotspotTwin)
    assert isinstance(intersection, IntersectionTwin)
    if gateway is not None:
        assert isinstance(gateway, GatewayClusterTwin)
    if metro_station is not None:
        assert isinstance(metro_station, MetroStationTwin)
    if metro_line is not None:
        assert isinstance(metro_line, MetroLineTwin)
    if rod_station is not None:
        assert isinstance(rod_station, RodaliesStationTwin)
    if rod_line is not None:
        assert isinstance(rod_line, RodaliesLineTwin)
    if fgc_station is not None:
        assert isinstance(fgc_station, FGCStationTwin)
    if fgc_line is not None:
        assert isinstance(fgc_line, FGCLineTwin)
    if interchange is not None:
        assert isinstance(interchange, InterchangeNodeTwin)

    # 1st pass dependencies from context to twins before stepping again
    gateway_pressure = float(ctx.gateway_ops.get("surge_factor", 0.0))
    corridor.connected_gateway_pressure = gateway_pressure
    intersection.connected_corridor_pressure = float(np.clip(corridor.queue_spillback_risk, 0.0, 1.0))
    bus.connected_corridor_delay = float(np.clip(corridor.travel_time_index * 15.0, 0.0, 100.0))
    curb.connected_gateway_pressure = gateway_pressure
    risk.connected_curb_conflict = float(np.clip(curb.pedestrian_conflict_score, 0.0, 1.0))
    risk.connected_intersection_risk = float(np.clip(intersection.risk_score, 0.0, 1.0))
    if interchange is not None:
        interchange.connected_corridor_pressure = float(np.clip(corridor.queue_spillback_risk, 0.0, 1.0))
        interchange.connected_gateway_pressure = gateway_pressure
    if metro_station is not None:
        metro_station.connected_interchange_pressure = float(np.clip((interchange.overall_interchange_load if interchange is not None else 0.2), 0.0, 1.0))
        metro_station.connected_gateway_pressure = gateway_pressure
    if rod_station is not None:
        rod_station.connected_gateway_pressure = gateway_pressure
    if gateway is not None and interchange is not None:
        gateway.connected_interchange_pressure = float(np.clip(interchange.overall_interchange_load, 0.0, 1.0))


def aggregate_city_state(runtime: Any, ctx: Any) -> Dict[str, Any]:
    inter = runtime.twins["intersection"]
    corridor = runtime.twins["road_corridor"]
    bus = runtime.twins["bus_corridor"]
    curb = runtime.twins["curb_zone"]
    risk = runtime.twins["risk_hotspot"]
    gateway = runtime.twins.get("gateway_cluster")
    metro_station = runtime.twins.get("metro_station")
    metro_line = runtime.twins.get("metro_line")
    rod_station = runtime.twins.get("rodalies_station")
    rod_line = runtime.twins.get("rodalies_line")
    fgc_station = runtime.twins.get("fgc_station")
    fgc_line = runtime.twins.get("fgc_line")
    interchange = runtime.twins.get("interchange_node")

    assert isinstance(inter, IntersectionTwin)
    assert isinstance(corridor, RoadCorridorTwin)
    assert isinstance(bus, BusCorridorTwin)
    assert isinstance(curb, CurbZoneTwin)
    assert isinstance(risk, RiskHotspotTwin)
    if gateway is not None:
        assert isinstance(gateway, GatewayClusterTwin)
    if metro_station is not None:
        assert isinstance(metro_station, MetroStationTwin)
    if metro_line is not None:
        assert isinstance(metro_line, MetroLineTwin)
    if rod_station is not None:
        assert isinstance(rod_station, RodaliesStationTwin)
    if rod_line is not None:
        assert isinstance(rod_line, RodaliesLineTwin)
    if fgc_station is not None:
        assert isinstance(fgc_station, FGCStationTwin)
    if fgc_line is not None:
        assert isinstance(fgc_line, FGCLineTwin)
    if interchange is not None:
        assert isinstance(interchange, InterchangeNodeTwin)

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

    risk_components = compute_risk_components({
        "pedestrian_exposure": risk.pedestrian_exposure,
        "bike_conflict_index": risk.bike_conflict_index,
        "risk_score": risk.risk_score,
        "bus_bunching_index": bus.bunching_index,
        "network_speed_index": network_speed_index,
        "curb_pressure_index": curb_pressure_index,
        "illegal_curb_occupancy_rate": curb.illegal_occupancy_rate,
        "gateway_delay_index": gateway_delay_index,
        "rain_flag": ctx.weather["rain_intensity"] > 0.20,
    })
    risk_burden = compute_risk_burden(risk_components)
    risk_phase = determine_risk_phase(risk.risk_score, risk.prev_risk_score, incident=active_event == "incident")
    forecast = forecast_risk_short(risk.risk_score, risk.prev_risk_score, risk_phase)
    prevention = recommend_prevention({
        "primary_hotspot_name": primary_name,
    }, risk_components, risk_phase)

    metro_pressure_index = float(metro_station.platform_crowding_index if metro_station is not None else ctx.rail_ops.get('metro_load', 0.0))
    rodalies_pressure_index = float(rod_station.platform_pressure if rod_station is not None else ctx.rail_ops.get('rodalies_load', 0.0))
    fgc_pressure_index = float(fgc_station.platform_pressure if fgc_station is not None else ctx.rail_ops.get('fgc_load', 0.0))
    interchange_pressure_index = float(interchange.overall_interchange_load if interchange is not None else ctx.rail_ops.get('interchange_pressure', 0.0))
    rail_disruption_pressure = float(np.clip((1 - (metro_line.reliability_proxy if metro_line is not None else 0.9)) * 0.35 + (1 - (rod_line.reliability_proxy if rod_line is not None else 0.85)) * 0.45 + (1 - (fgc_line.reliability_proxy if fgc_line is not None else 0.9)) * 0.20, 0.0, 1.0))
    airport_rail_access_pressure = float(np.clip(ctx.rail_ops.get('airport_rail_pressure', 0.0), 0.0, 1.0))
    urban_rail_burden = float(np.clip(0.35 * metro_pressure_index + 0.40 * rodalies_pressure_index + 0.25 * fgc_pressure_index, 0.0, 1.0))
    dominant_rail_subsystem = max(
        {'metro': metro_pressure_index, 'rodalies': rodalies_pressure_index, 'fgc': fgc_pressure_index},
        key=lambda k: {'metro': metro_pressure_index, 'rodalies': rodalies_pressure_index, 'fgc': fgc_pressure_index}[k]
    )
    dominant_interchange = interchange.metadata.get('hotspot_name', '') if interchange is not None else primary_name
    rail_assisted_mitigation_potential = float(np.clip(0.55 + 0.35 * (1.0 - urban_rail_burden) - 0.20 * rail_disruption_pressure, 0.0, 1.0))

    city_pressure_score = float(np.clip(
        0.16 * (1.0 - network_speed_index)
        + 0.12 * bus.bunching_index
        + 0.12 * curb_pressure_index
        + 0.16 * risk.risk_score
        + 0.12 * gateway_delay_index
        + 0.12 * risk_burden
        + 0.10 * urban_rail_burden
        + 0.10 * interchange_pressure_index,
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
        "pedestrian_risk": risk_components["pedestrian_risk"],
        "bike_risk": risk_components["bike_risk"],
        "motorcycle_risk": risk_components["motorcycle_risk"],
        "bus_conflict_risk": risk_components["bus_conflict_risk"],
        "logistics_conflict_risk": risk_components["logistics_conflict_risk"],
        "gateway_risk": risk_components["gateway_risk"],
        "weather_risk": risk_components["weather_risk"],
        "risk_burden": risk_burden,
        "dominant_risk_type": dominant_risk_type(risk_components),
        "risk_phase": risk_phase,
        "risk_forecast_score": forecast["risk_forecast_score"],
        "escalation_probability": forecast["escalation_probability"],
        "risk_forecast_trend": forecast["risk_forecast_trend"],
        "preventive_action_recommended": prevention["preventive_action_recommended"],
        "preventive_priority": prevention["preventive_priority"],
        "preventive_layer": prevention["preventive_layer"],
        "gateway_delay_index": gateway_delay_index,
        "coordination_flag": coordination_flag,
        "logistics_pressure_flag": logistics_pressure_flag,
        "rain_flag": ctx.weather["rain_intensity"] > 0.20,
        "school_peak_flag": active_event == "school_peak",
        "incident_flag": active_event == "incident",
        "delivery_wave_flag": active_event == "delivery_wave",
        "gateway_surge_flag": active_event == "gateway_surge",
        "city_pressure_score": city_pressure_score,
        "urban_rail_burden": urban_rail_burden,
        "metro_pressure_index": metro_pressure_index,
        "rodalies_pressure_index": rodalies_pressure_index,
        "fgc_pressure_index": fgc_pressure_index,
        "interchange_pressure_index": interchange_pressure_index,
        "rail_disruption_pressure": rail_disruption_pressure,
        "airport_rail_access_pressure": airport_rail_access_pressure,
        "city_intermodal_score": float(np.clip(1.0 - 0.60 * interchange_pressure_index - 0.40 * rail_disruption_pressure, 0.0, 1.0)),
        "dominant_rail_subsystem": dominant_rail_subsystem,
        "dominant_interchange": dominant_interchange,
        "rail_assisted_mitigation_potential": rail_assisted_mitigation_potential,
        "metro_station_operational_status": metro_station.operational_status if metro_station is not None else "",
        "rodalies_station_operational_status": rod_station.operational_status if rod_station is not None else "",
        "fgc_station_operational_status": fgc_station.operational_status if fgc_station is not None else "",
        "interchange_node_operational_status": interchange.operational_status if interchange is not None else "",
        "metro_station_pressure_level": metro_station.pressure_level if metro_station is not None else "",
        "rodalies_station_pressure_level": rod_station.pressure_level if rod_station is not None else "",
        "fgc_station_pressure_level": fgc_station.pressure_level if fgc_station is not None else "",
        "interchange_node_pressure_level": interchange.pressure_level if interchange is not None else "",
        "metro_station_trend_state": metro_station.trend_state if metro_station is not None else "",
        "rodalies_station_trend_state": rod_station.trend_state if rod_station is not None else "",
        "fgc_station_trend_state": fgc_station.trend_state if fgc_station is not None else "",
        "interchange_node_trend_state": interchange.trend_state if interchange is not None else "",
        "metro_station_hotspot": metro_station.metadata.get('hotspot_name', '') if metro_station is not None else "",
        "rodalies_station_hotspot": rod_station.metadata.get('hotspot_name', '') if rod_station is not None else "",
        "fgc_station_hotspot": fgc_station.metadata.get('hotspot_name', '') if fgc_station is not None else "",
        "interchange_node_hotspot": interchange.metadata.get('hotspot_name', '') if interchange is not None else "",
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
