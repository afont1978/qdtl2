
from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import streamlit as st


def _fmt_num(x: Any, suffix: str = "") -> str:
    try:
        return f"{float(x):.2f}{suffix}"
    except Exception:
        return "—"


def _fmt_pct(x: Any) -> str:
    try:
        return f"{float(x) * 100:.1f}%"
    except Exception:
        return "—"


def _native_line(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for col, label in mapping.items():
        if col in df.columns:
            out[label] = df[col]
    return out


def live_focus_options() -> list[str]:
    return ["Overview", "Traffic", "Transit", "Risk", "Logistics", "Gateway", "Orchestration"]


def render_live_monitor(df_local: pd.DataFrame, latest_local: Dict[str, Any], focus: str) -> None:
    st.markdown("## Live Monitor")
    if df_local.empty:
        st.info("No simulation data yet. Press Step or Start.")
        return

    live_df = df_local.tail(30).copy().set_index("step_id")

    row1 = st.columns(6)
    row1[0].metric("Mode", str(latest_local.get("mode", "—")).title())
    row1[1].metric("City pressure", _fmt_num(latest_local.get("city_pressure_score", 0.0)))
    row1[2].metric("Risk burden", _fmt_num(latest_local.get("risk_burden", 0.0)))
    row1[3].metric("Dominant risk", str(latest_local.get("dominant_risk_type", "—")).replace("_", " ").title())
    row1[4].metric("Route", str(latest_local.get("decision_route", "—")))
    row1[5].metric("Latency", _fmt_num(latest_local.get("exec_ms", 0), " ms"))

    row2 = st.columns(4)
    row2[0].metric("Active hotspot", str(latest_local.get("primary_hotspot_name", "—")))
    row2[1].metric("Action priority", str(latest_local.get("action_priority", "—")).title())
    row2[2].metric("Responsible layer", str(latest_local.get("responsible_layer", "—")))
    row2[3].metric("Event", str(latest_local.get("active_event", "none") or "none"))

    st.markdown("### Next best action")
    c1, c2 = st.columns([1.2, 1.0])
    with c1:
        st.info(str(latest_local.get("recommended_action", "No action available.")))
        impact = str(latest_local.get("expected_impact", "No expected impact available."))
        if impact and impact != "None":
            st.caption(impact)
    with c2:
        st.write(f"**Route reason:** {latest_local.get('route_reason', '—')}")
        prev = latest_local.get("preventive_action_recommended", "")
        if prev:
            st.write(f"**Preventive action:** {prev}")
        st.write(f"**Validation:** {latest_local.get('validation_status', '—')}")

    if focus == "Traffic":
        c1, c2 = st.columns(2)
        with c1:
            st.line_chart(_native_line(live_df, {
                "network_speed_index": "Network speed",
                "corridor_reliability_index": "Corridor reliability",
                "city_pressure_score": "City pressure",
            }), height=260, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {
                "corridor_delay_s": "Corridor delay s",
                "gateway_delay_index": "Gateway delay",
            }), height=260, use_container_width=True)
    elif focus == "Transit":
        c1, c2 = st.columns(2)
        with c1:
            st.line_chart(_native_line(live_df, {
                "bus_bunching_index": "Bus bunching",
                "bus_commercial_speed_kmh": "Commercial speed",
            }), height=260, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {
                "bus_priority_requests": "Priority requests",
                "corridor_reliability_index": "Corridor reliability",
            }), height=260, use_container_width=True)
    elif focus == "Risk":
        c1, c2 = st.columns(2)
        with c1:
            st.line_chart(_native_line(live_df, {
                "risk_burden": "Risk burden",
                "risk_score": "Risk score",
                "near_miss_index": "Near-miss",
            }), height=260, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {
                "pedestrian_risk": "Pedestrian",
                "bike_risk": "Bike",
                "motorcycle_risk": "Motorcycle",
            }), height=260, use_container_width=True)
    elif focus == "Logistics":
        c1, c2 = st.columns(2)
        with c1:
            st.line_chart(_native_line(live_df, {
                "curb_occupancy_rate": "Curb occupancy",
                "illegal_curb_occupancy_rate": "Illegal occupancy",
            }), height=260, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {
                "delivery_queue": "Delivery queue",
                "logistics_conflict_risk": "Logistics risk",
            }), height=260, use_container_width=True)
    elif focus == "Gateway":
        c1, c2 = st.columns(2)
        with c1:
            st.line_chart(_native_line(live_df, {
                "gateway_delay_index": "Gateway delay",
                "gateway_risk": "Gateway risk",
            }), height=260, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {
                "network_speed_index": "Network speed",
                "city_pressure_score": "City pressure",
            }), height=260, use_container_width=True)
    elif focus == "Orchestration":
        c1, c2 = st.columns(2)
        with c1:
            st.line_chart(_native_line(live_df, {
                "decision_confidence": "Decision confidence",
                "expected_value_of_hybrid": "Expected value of hybrid",
            }), height=260, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {
                "risk_burden": "Risk burden",
                "city_pressure_score": "City pressure",
            }), height=260, use_container_width=True)
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.line_chart(_native_line(live_df, {
                "network_speed_index": "Network speed",
                "bus_bunching_index": "Bus bunching",
                "risk_burden": "Risk burden",
            }), height=260, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {
                "curb_occupancy_rate": "Curb occupancy",
                "gateway_delay_index": "Gateway delay",
                "city_pressure_score": "City pressure",
            }), height=260, use_container_width=True)
