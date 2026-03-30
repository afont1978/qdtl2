
import json
import time
from typing import Any, Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from mobility_runtime import MobilityRuntime
from src.mobility_os.ui.live_monitor import render_live_monitor, live_focus_options

st.set_page_config(page_title="Hybrid Quantum-Classical Urban Mobility Control Room", layout="wide")

st.markdown(
    """
    <style>
    .block-container {max-width: 1600px; padding-top: 1rem; padding-bottom: 1.5rem;}
    .hero {padding:1rem 1.2rem; border:1px solid rgba(255,255,255,0.08); border-radius:18px;
           background: linear-gradient(135deg, rgba(20,30,48,0.96), rgba(9,14,28,0.96)); margin-bottom:1rem;}
    .hero-title {font-size:2rem; font-weight:700; color:#F4F7FB; margin-bottom:0.2rem;}
    .hero-subtitle {font-size:1rem; color:#C7D0DD;}
    .metric-card {padding:0.8rem 1rem; border-radius:16px; background:rgba(255,255,255,0.03);
                  border:1px solid rgba(255,255,255,0.06);}
    .hotspot-box {padding:0.8rem 1rem; border-radius:16px; background:rgba(255,255,255,0.03);
                  border:1px solid rgba(255,255,255,0.06); margin-bottom:0.8rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

SCENARIO_LABELS = {
    "corridor_congestion": "Corridor congestion",
    "school_area_risk": "School-area safety risk",
    "urban_logistics_saturation": "Urban logistics saturation",
    "gateway_access_stress": "Gateway access stress",
    "event_mobility": "Event mobility",
}
MODE_LABELS = {
    "traffic": "Traffic",
    "safety": "Safety",
    "logistics": "Logistics",
    "gateway": "Gateway",
    "event": "Event",
}
ROUTE_COLORS = {
    "CLASSICAL": "#4E79A7",
    "QUANTUM": "#9C6ADE",
    "FALLBACK_CLASSICAL": "#F28E2B",
}


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("scenario", "corridor_congestion")
    ss.setdefault("scenario_ui", ss["scenario"])
    ss.setdefault("seed", 42)
    ss.setdefault("seed_ui", int(ss["seed"]))
    ss.setdefault("running", False)
    ss.setdefault("sleep_s", 0.30)
    ss.setdefault("batch_steps", 4)
    ss.setdefault("live_window", 36)
    ss.setdefault("mobility_twin_sel", "intersection")
    ss.setdefault("live_focus", "Overview")
    ss.setdefault("rt", MobilityRuntime(scenario=ss["scenario"], seed=ss["seed"]))


def rebuild_runtime() -> None:
    ss = st.session_state
    ss["rt"] = MobilityRuntime(scenario=ss["scenario"], seed=int(ss["seed"]))
    ss["running"] = False


def get_df() -> pd.DataFrame:
    df = st.session_state["rt"].dataframe()
    return df.copy() if not df.empty else pd.DataFrame()


def latest_record(df: pd.DataFrame) -> Dict[str, Any]:
    return {} if df.empty else df.iloc[-1].to_dict()


def safe_json_loads(text: Any) -> Any:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(text)
    except Exception:
        return text


def route_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "decision_route" not in df.columns:
        return pd.DataFrame(columns=["route", "count"])
    vc = df["decision_route"].value_counts().reset_index()
    vc.columns = ["route", "count"]
    return vc


def event_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "active_event" not in df.columns:
        return pd.DataFrame(columns=["event", "count"])
    vc = df["active_event"].fillna("none").value_counts().reset_index()
    vc.columns = ["event", "count"]
    return vc


def make_line_chart(df: pd.DataFrame, x: str, y_cols: list[str], title: str, y_title: str = "", key: str = "") -> go.Figure:
    fig = go.Figure()
    for col in y_cols:
        if col in df.columns:
            fig.add_trace(go.Scatter(x=df[x], y=df[col], mode="lines", name=col, line=dict(width=2)))
    fig.update_layout(
        title=title,
        template="plotly_dark",
        margin=dict(l=20, r=20, t=50, b=20),
        height=320,
        legend=dict(orientation="h"),
        xaxis_title="Step",
        yaxis_title=y_title,
        uirevision=key or title,
    )
    return fig


def make_overview_performance(df: pd.DataFrame, key: str = "") -> go.Figure:
    fig = go.Figure()
    for col, name in [
        ("network_speed_index", "Network speed index"),
        ("corridor_reliability_index", "Corridor reliability"),
        ("step_operational_score", "Operational score"),
    ]:
        if col in df.columns:
            fig.add_trace(go.Scatter(x=df["step_id"], y=df[col], mode="lines", name=name, line=dict(width=3 if col == "step_operational_score" else 2)))
    fig.update_layout(
        title="System performance",
        template="plotly_dark",
        margin=dict(l=20, r=20, t=50, b=20),
        height=340,
        legend=dict(orientation="h"),
        xaxis_title="Step",
        yaxis_title="Index",
        uirevision=key or "overview_perf",
    )
    return fig


def make_route_chart(df: pd.DataFrame, key: str = "") -> go.Figure:
    rc = route_counts(df)
    fig = px.bar(rc, x="route", y="count", color="route", color_discrete_map=ROUTE_COLORS, template="plotly_dark", title="Decision mix")
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=260, showlegend=False, uirevision=key or "routes")
    return fig


def make_event_chart(df: pd.DataFrame, key: str = "") -> go.Figure:
    ev = event_counts(df)
    fig = px.bar(ev, x="event", y="count", template="plotly_dark", title="Event frequency")
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=260, showlegend=False, uirevision=key or "events")
    return fig


def kpi_block(label: str, value: str, delta: str = "") -> None:
    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
    st.metric(label, value, delta)
    st.markdown("</div>", unsafe_allow_html=True)


def hotspot_map(lat: Any, lon: Any, label: str = "Hotspot") -> None:
    try:
        if lat is None or lon is None:
            st.caption("No geolocation available for this hotspot.")
            return
        lat_f = float(lat)
        lon_f = float(lon)
        st.map(pd.DataFrame({"lat": [lat_f], "lon": [lon_f]}), zoom=12)
        st.caption(f"{label}: {lat_f:.4f}, {lon_f:.4f}")
    except Exception:
        st.caption("No geolocation available for this hotspot.")


def render_hotspot_card(name: Any, streets: Any = None, category: Any = None, why: Any = None, lat: Any = None, lon: Any = None, note: Any = None) -> None:
    st.markdown('<div class="hotspot-box">', unsafe_allow_html=True)
    st.markdown(f"### {name or 'No hotspot assigned'}")
    if category:
        st.write(f"**Category:** {category}")
    if streets:
        st.write(f"**Streets / environment:** {streets}")
    if why:
        st.write(f"**Operational relevance:** {why}")
    if note:
        st.caption(str(note))
    st.markdown("</div>", unsafe_allow_html=True)
    hotspot_map(lat, lon, label=str(name or "Hotspot"))


def extract_twin_hotspot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    md = snapshot.get("metadata", {}) if isinstance(snapshot, dict) else {}
    return {
        "name": md.get("hotspot_name") or md.get("scenario_hotspot_name") or snapshot.get("primary_hotspot_name"),
        "lat": md.get("lat"),
        "lon": md.get("lon"),
        "category": md.get("category"),
        "streets": md.get("streets"),
        "why": md.get("why"),
        "note": md.get("scenario_note"),
    }

def fmt_pct(x: Any) -> str:
    try:
        return f"{float(x)*100:.1f}%"
    except Exception:
        return "—"


def fmt_num(x: Any, suffix: str = "") -> str:
    try:
        return f"{float(x):.2f}{suffix}"
    except Exception:
        return "—"


def safe_get(d: Dict[str, Any], key: str, default: Any = "—") -> Any:
    return d.get(key, default) if isinstance(d, dict) else default


def render_info_table(title: str, rows: list[tuple[str, str]]) -> None:
    st.markdown(f"### {title}")
    clean_rows = [{"Campo": k, "Valor": v} for k, v in rows if v not in [None, "", "—"]]
    if clean_rows:
        st.dataframe(pd.DataFrame(clean_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("Sin datos disponibles.")


def format_route(route: str) -> str:
    return {
        "CLASSICAL": "Classical",
        "QUANTUM": "Quantum",
        "FALLBACK_CLASSICAL": "Fallback → Classical",
    }.get(route, str(route))


def render_twin_summary(twin_sel: str, snapshot: dict, latest_row: dict) -> None:
    hotspot_name = safe_get(snapshot.get("metadata", {}), "hotspot_name", safe_get(snapshot, "hotspot_name", "No asignado"))
    streets = safe_get(snapshot.get("metadata", {}), "streets", "No disponible")
    category = safe_get(snapshot.get("metadata", {}), "category", "No disponible")
    why = safe_get(snapshot.get("metadata", {}), "why", "No disponible")

    route = format_route(str(latest_row.get("decision_route", ""))) if latest_row else "—"
    route_reason = latest_row.get("route_reason", "—") if latest_row else "—"

    title_map = {
        "intersection": "Estado actual del cruce",
        "road_corridor": "Estado actual del corredor",
        "bus_corridor": "Estado actual del corredor bus",
        "curb_zone": "Estado actual de la zona curbside",
        "risk_hotspot": "Estado actual del hotspot de riesgo",
    }

    st.markdown(f"## {title_map.get(twin_sel, 'Estado actual del activo')}")

    c1, c2 = st.columns([1, 1])
    with c1:
        render_info_table(
            "Identificación",
            [
                ("Activo", twin_sel.replace("_", " ").title()),
                ("Hotspot", hotspot_name),
                ("Categoría", category),
                ("Calles / entorno", streets),
            ],
        )

    with c2:
        render_info_table(
            "Decisión actual del sistema",
            [
                ("Ruta elegida", route),
                ("Motivo", route_reason),
                ("Evento activo", latest_row.get("active_event", "none") if latest_row else "—"),
            ],
        )

    if twin_sel == "intersection":
        render_info_table(
            "Indicadores clave",
            [
                ("Cola NS", fmt_num(snapshot.get("queue_ns"), " veh")),
                ("Cola EO", fmt_num(snapshot.get("queue_ew"), " veh")),
                ("Retraso medio", fmt_num(snapshot.get("avg_delay_s"), " s")),
                ("Espera peatonal", fmt_num(snapshot.get("ped_wait_s"), " s")),
                ("Riesgo", fmt_num(snapshot.get("risk_score"))),
                ("Throughput", fmt_num(snapshot.get("throughput_vph"), " veh/h")),
            ],
        )
    elif twin_sel == "road_corridor":
        render_info_table(
            "Indicadores clave",
            [
                ("Velocidad media", fmt_num(snapshot.get("avg_speed_kmh"), " km/h")),
                ("Travel time index", fmt_num(snapshot.get("travel_time_index"))),
                ("Densidad", fmt_num(snapshot.get("density_proxy"))),
                ("Riesgo de spillback", fmt_num(snapshot.get("queue_spillback_risk"))),
                ("Emisiones proxy", fmt_num(snapshot.get("emission_proxy"))),
                ("Ruido proxy", fmt_num(snapshot.get("noise_proxy"))),
            ],
        )
    elif twin_sel == "bus_corridor":
        render_info_table(
            "Indicadores clave",
            [
                ("Headway real", fmt_num(snapshot.get("headway_real_s"), " s")),
                ("Headway objetivo", fmt_num(snapshot.get("headway_target_s"), " s")),
                ("Bunching index", fmt_num(snapshot.get("bunching_index"))),
                ("Velocidad comercial", fmt_num(snapshot.get("commercial_speed_kmh"), " km/h")),
                ("Ocupación", fmt_num(snapshot.get("occupancy_proxy"))),
                ("Solicitudes de prioridad", str(snapshot.get("priority_requests_active", "—"))),
            ],
        )
    elif twin_sel == "curb_zone":
        render_info_table(
            "Indicadores clave",
            [
                ("Ocupación", fmt_pct(snapshot.get("occupancy_rate"))),
                ("Ocupación ilegal", fmt_pct(snapshot.get("illegal_occupancy_rate"))),
                ("Tiempo medio de estancia", fmt_num(snapshot.get("avg_dwell_time_min"), " min")),
                ("Cola de entregas", fmt_num(snapshot.get("delivery_queue"))),
                ("Presión pick-up/drop-off", fmt_num(snapshot.get("pickup_dropoff_pressure"))),
                ("Conflicto peatonal", fmt_num(snapshot.get("pedestrian_conflict_score"))),
            ],
        )
    elif twin_sel == "risk_hotspot":
        render_info_table(
            "Indicadores clave",
            [
                ("Riesgo", fmt_num(snapshot.get("risk_score"))),
                ("Near-miss index", fmt_num(snapshot.get("near_miss_index"))),
                ("Exposición peatonal", fmt_num(snapshot.get("pedestrian_exposure"))),
                ("Conflicto bici", fmt_num(snapshot.get("bike_conflict_index"))),
                ("Visibilidad", fmt_num(snapshot.get("visibility_proxy"))),
                ("Riesgo motocicleta", fmt_num(snapshot.get("motorcycle_risk_proxy"))),
            ],
        )

    st.markdown("### Relevancia operativa")
    st.write(why)


def render_overview(df_local: pd.DataFrame, latest_local: Dict[str, Any], render_id: str = "base") -> None:
    if df_local.empty:
        st.info("No simulation data yet. Press Step or Start.")
        return

    live_df = df_local.tail(int(st.session_state["live_window"])).copy()
    q_share = (df_local["decision_route"] == "QUANTUM").mean() * 100.0 if len(df_local) else 0.0
    fb_rate = df_local["fallback_triggered"].mean() * 100.0 if len(df_local) else 0.0
    avg_latency = float(df_local["exec_ms"].tail(24).mean()) if len(df_local) else 0.0
    mean_conf = float(df_local["decision_confidence"].tail(24).mean() * 100.0) if len(df_local) else 0.0

    row1 = st.columns(6)
    with row1[0]:
        kpi_block("Mode", MODE_LABELS.get(str(latest_local.get("mode", "")), str(latest_local.get("mode", ""))))
    with row1[1]:
        kpi_block("Network speed", f"{latest_local.get('network_speed_index', 0.0):.2f}")
    with row1[2]:
        kpi_block("Corridor reliability", f"{latest_local.get('corridor_reliability_index', 0.0):.2f}")
    with row1[3]:
        kpi_block("Bus bunching", f"{latest_local.get('bus_bunching_index', 0.0):.2f}")
    with row1[4]:
        kpi_block("Curb occupancy", f"{latest_local.get('curb_occupancy_rate', 0.0)*100:.1f}%")
    with row1[5]:
        kpi_block("Risk score", f"{latest_local.get('risk_score', 0.0):.2f}")

    row2 = st.columns(6)
    with row2[0]:
        kpi_block("Near-miss index", f"{latest_local.get('near_miss_index', 0.0):.2f}")
    with row2[1]:
        kpi_block("Gateway delay", f"{latest_local.get('gateway_delay_index', 0.0):.2f}")
    with row2[2]:
        kpi_block("Operational score", f"{latest_local.get('step_operational_score', 0.0):.2f}")
    with row2[3]:
        kpi_block("Quantum share", f"{q_share:.1f}%")
    with row2[4]:
        kpi_block("Fallback rate", f"{fb_rate:.1f}%")
    with row2[5]:
        kpi_block("Avg latency", f"{avg_latency:.0f} ms", f"Conf {mean_conf:.1f}%")

    left, right = st.columns([2.0, 1.0])
    with left:
        st.plotly_chart(make_overview_performance(live_df, key=f"mob_perf_{render_id}"), use_container_width=True, key=f"plot_mob_perf_{render_id}")
        c_a, c_b = st.columns(2)
        with c_a:
            st.plotly_chart(
                make_line_chart(live_df, "step_id", ["bus_bunching_index", "bus_commercial_speed_kmh"], "Transit performance", y_title="index / km/h", key=f"transit_perf_{render_id}"),
                use_container_width=True,
                key=f"plot_transit_perf_{render_id}",
            )
        with c_b:
            st.plotly_chart(
                make_line_chart(live_df, "step_id", ["curb_occupancy_rate", "illegal_curb_occupancy_rate", "delivery_queue"], "Logistics and curb", y_title="ratio / queue", key=f"curb_perf_{render_id}"),
                use_container_width=True,
                key=f"plot_curb_perf_{render_id}",
            )
    with right:
        st.plotly_chart(make_route_chart(df_local, key=f"route_mix_{render_id}"), use_container_width=True, key=f"plot_route_mix_{render_id}")
        st.plotly_chart(make_event_chart(df_local, key=f"event_mix_{render_id}"), use_container_width=True, key=f"plot_event_mix_{render_id}")
        st.markdown("### Current decision")
        st.write(f"**Route:** {latest_local.get('decision_route', '')}")
        st.write(f"**Confidence:** {latest_local.get('decision_confidence', 0.0)*100:.1f}%")
        st.write(f"**Latency:** {latest_local.get('exec_ms', 0)} ms")
        st.write(f"**Fallback:** {'Yes' if latest_local.get('fallback_triggered', False) else 'No'}")
        st.write(f"**Active event:** {latest_local.get('active_event', 'none') or 'none'}")
        st.markdown("### Why this route")
        st.caption(str(latest_local.get("route_reason", "No route reason available.")))

    st.markdown("### Active Barcelona hotspot")
    c1, c2 = st.columns([1.2, 1.0])
    with c1:
        render_hotspot_card(
            latest_local.get("primary_hotspot_name"),
            note=latest_local.get("scenario_note"),
            lat=latest_local.get("primary_hotspot_lat"),
            lon=latest_local.get("primary_hotspot_lon"),
        )
    with c2:
        st.markdown("#### Scenario-linked hotspots")
        hotspot_cols = [c for c in ["intersection_hotspot", "road_corridor_hotspot", "bus_corridor_hotspot", "curb_zone_hotspot", "risk_hotspot_name"] if c in latest_local]
        for col in hotspot_cols:
            st.write(f"**{col.replace('_', ' ').title()}:** {latest_local.get(col)}")

    snap_cols = [
        "step_id", "mode", "scenario", "active_event", "primary_hotspot_name",
        "network_speed_index", "corridor_reliability_index", "bus_bunching_index",
        "curb_occupancy_rate", "risk_score", "gateway_delay_index", "decision_route"
    ]
    snap_cols = [c for c in snap_cols if c in live_df.columns]
    st.dataframe(live_df[snap_cols].tail(12), use_container_width=True, height=320)


def render_twins_panel(df_local: pd.DataFrame, snapshots: Dict[str, Dict[str, Any]], twin_sel: str, render_id: str = "base") -> None:
    if df_local.empty:
        st.info("No simulation data yet.")
        return

    snapshot = snapshots.get(twin_sel, {})
    hotspot = extract_twin_hotspot(snapshot)

    c_top1, c_top2 = st.columns([1.0, 1.2])
    with c_top1:
        render_hotspot_card(
            hotspot.get("name"),
            streets=hotspot.get("streets"),
            category=hotspot.get("category"),
            why=hotspot.get("why"),
            lat=hotspot.get("lat"),
            lon=hotspot.get("lon"),
            note=hotspot.get("note"),
        )
    with c_top2:
        latest_row = df_local.iloc[-1].to_dict() if not df_local.empty else {}
        render_twin_summary(twin_sel, snapshot, latest_row)

    live_df = df_local.tail(int(st.session_state["live_window"])).copy()

    if twin_sel == "intersection":
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["corridor_delay_s"], "Intersection / corridor delay", "s", f"int_delay_{render_id}"), use_container_width=True, key=f"plot_int_delay_{render_id}")
        with c2:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["risk_score"], "Intersection risk", "index", f"int_risk_{render_id}"), use_container_width=True, key=f"plot_int_risk_{render_id}")
    elif twin_sel == "road_corridor":
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["network_speed_index", "corridor_reliability_index"], "Corridor performance", "index", f"corr_perf_{render_id}"), use_container_width=True, key=f"plot_corr_perf_{render_id}")
        with c2:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["gateway_delay_index"], "Gateway propagation", "index", f"corr_gate_{render_id}"), use_container_width=True, key=f"plot_corr_gate_{render_id}")
    elif twin_sel == "bus_corridor":
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["bus_bunching_index"], "Bus bunching", "index", f"bus_bunch_{render_id}"), use_container_width=True, key=f"plot_bus_bunch_{render_id}")
        with c2:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["bus_commercial_speed_kmh", "bus_priority_requests"], "Bus speed and priority requests", "km/h / count", f"bus_speed_{render_id}"), use_container_width=True, key=f"plot_bus_speed_{render_id}")
    elif twin_sel == "curb_zone":
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["curb_occupancy_rate", "illegal_curb_occupancy_rate"], "Curb occupancy", "ratio", f"curb_occ_{render_id}"), use_container_width=True, key=f"plot_curb_occ_{render_id}")
        with c2:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["delivery_queue"], "Delivery queue", "count", f"curb_queue_{render_id}"), use_container_width=True, key=f"plot_curb_queue_{render_id}")
    elif twin_sel == "risk_hotspot":
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["risk_score", "near_miss_index"], "Risk and near-miss", "index", f"risk_main_{render_id}"), use_container_width=True, key=f"plot_risk_main_{render_id}")
        with c2:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["pedestrian_exposure", "bike_conflict_index"], "VRU exposure", "index", f"risk_vru_{render_id}"), use_container_width=True, key=f"plot_risk_vru_{render_id}")


def render_risk_panel(df_local: pd.DataFrame, latest_local: Dict[str, Any], render_id: str = "base") -> None:
    if df_local.empty:
        st.info("No simulation data yet.")
        return

    live_df = df_local.tail(int(st.session_state["live_window"])).copy()
    c1, c2 = st.columns([1.6, 1.0])
    with c1:
        c11, c12 = st.columns(2)
        with c11:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["risk_score", "near_miss_index"], "Risk and early-warning state", "index", f"risk_tab_main_{render_id}"), use_container_width=True, key=f"plot_risk_tab_main_{render_id}")
        with c12:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["pedestrian_exposure", "bike_conflict_index"], "Exposure of vulnerable users", "index", f"risk_tab_vru_{render_id}"), use_container_width=True, key=f"plot_risk_tab_vru_{render_id}")
        risk_view = live_df[[c for c in ["step_id", "active_event", "primary_hotspot_name", "risk_score", "near_miss_index", "pedestrian_exposure", "bike_conflict_index", "route_reason"] if c in live_df.columns]].tail(20)
        st.dataframe(risk_view, use_container_width=True, height=320)
    with c2:
        st.markdown("### Current risk hotspot")
        render_hotspot_card(
            latest_local.get("risk_hotspot_name") or latest_local.get("primary_hotspot_name"),
            note=latest_local.get("scenario_note"),
            lat=latest_local.get("primary_hotspot_lat"),
            lon=latest_local.get("primary_hotspot_lon"),
        )



def render_overview_live_compact(df_local: pd.DataFrame, latest_local: Dict[str, Any], render_id: str = "live") -> None:
    if df_local.empty:
        st.info("No simulation data yet.")
        return
    live_df = df_local.tail(int(st.session_state["live_window"])).copy()
    row = st.columns(5)
    with row[0]:
        kpi_block("Mode", MODE_LABELS.get(str(latest_local.get("mode", "")), str(latest_local.get("mode", ""))))
    with row[1]:
        kpi_block("Network speed", f"{latest_local.get('network_speed_index', 0.0):.2f}")
    with row[2]:
        kpi_block("Bus bunching", f"{latest_local.get('bus_bunching_index', 0.0):.2f}")
    with row[3]:
        kpi_block("Curb occupancy", f"{latest_local.get('curb_occupancy_rate', 0.0)*100:.1f}%")
    with row[4]:
        kpi_block("Risk score", f"{latest_local.get('risk_score', 0.0):.2f}")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(make_overview_performance(live_df, key=f"overview_compact_{render_id}"), use_container_width=True, key=f"plot_overview_compact_{render_id}")
    with c2:
        st.plotly_chart(make_line_chart(live_df, "step_id", ["bus_bunching_index", "curb_occupancy_rate", "risk_score"], "Live indicators", "index / ratio", f"overview_live_ind_{render_id}"), use_container_width=True, key=f"plot_overview_live_ind_{render_id}")
    st.caption(str(latest_local.get("route_reason", "")))


def render_twins_live_compact(df_local: pd.DataFrame, twin_sel: str, render_id: str = "live") -> None:
    if df_local.empty:
        st.info("No simulation data yet.")
        return
    live_df = df_local.tail(int(st.session_state["live_window"])).copy()
    st.markdown(f"### Live twin view: {twin_sel.replace('_', ' ').title()}")
    if twin_sel == "intersection":
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["corridor_delay_s"], "Delay", "s", f"int_delay_compact_{render_id}"), use_container_width=True, key=f"plot_int_delay_compact_{render_id}")
        with c2:
            st.plotly_chart(make_line_chart(live_df, "step_id", ["risk_score"], "Risk", "index", f"int_risk_compact_{render_id}"), use_container_width=True, key=f"plot_int_risk_compact_{render_id}")
    elif twin_sel == "road_corridor":
        st.plotly_chart(make_line_chart(live_df, "step_id", ["network_speed_index", "corridor_reliability_index", "gateway_delay_index"], "Road corridor", "index", f"road_compact_{render_id}"), use_container_width=True, key=f"plot_road_compact_{render_id}")
    elif twin_sel == "bus_corridor":
        st.plotly_chart(make_line_chart(live_df, "step_id", ["bus_bunching_index", "bus_commercial_speed_kmh"], "Bus corridor", "index / km/h", f"bus_compact_{render_id}"), use_container_width=True, key=f"plot_bus_compact_{render_id}")
    elif twin_sel == "curb_zone":
        st.plotly_chart(make_line_chart(live_df, "step_id", ["curb_occupancy_rate", "illegal_curb_occupancy_rate", "delivery_queue"], "Curb zone", "ratio / queue", f"curb_compact_{render_id}"), use_container_width=True, key=f"plot_curb_compact_{render_id}")
    elif twin_sel == "risk_hotspot":
        st.plotly_chart(make_line_chart(live_df, "step_id", ["risk_score", "near_miss_index", "pedestrian_exposure", "bike_conflict_index"], "Risk hotspot", "index", f"risk_compact_{render_id}"), use_container_width=True, key=f"plot_risk_compact_{render_id}")


def render_risk_live_compact(df_local: pd.DataFrame, latest_local: Dict[str, Any], render_id: str = "live") -> None:
    if df_local.empty:
        st.info("No simulation data yet.")
        return
    live_df = df_local.tail(int(st.session_state["live_window"])).copy()
    row = st.columns(4)
    with row[0]:
        kpi_block("Risk", f"{latest_local.get('risk_score', 0.0):.2f}")
    with row[1]:
        kpi_block("Near-miss", f"{latest_local.get('near_miss_index', 0.0):.2f}")
    with row[2]:
        kpi_block("Ped exposure", f"{latest_local.get('pedestrian_exposure', 0.0):.2f}")
    with row[3]:
        kpi_block("Bike conflict", f"{latest_local.get('bike_conflict_index', 0.0):.2f}")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(make_line_chart(live_df, "step_id", ["risk_score", "near_miss_index"], "Risk & near-miss", "index", f"risk_compact_main_{render_id}"), use_container_width=True, key=f"plot_risk_compact_main_{render_id}")
    with c2:
        st.plotly_chart(make_line_chart(live_df, "step_id", ["pedestrian_exposure", "bike_conflict_index"], "Exposure", "index", f"risk_compact_exposure_{render_id}"), use_container_width=True, key=f"plot_risk_compact_exposure_{render_id}")
    st.caption(str(latest_local.get("primary_hotspot_name", "")))

def render_audit_panel(df_local: pd.DataFrame) -> None:
    if df_local.empty:
        st.info("No records yet.")
        return

    cols_to_show = [
        "step_id", "ts", "mode", "scenario", "active_event", "primary_hotspot_name", "decision_route",
        "route_reason", "exec_ms", "decision_confidence", "fallback_triggered",
        "network_speed_index", "bus_bunching_index", "curb_occupancy_rate", "risk_score"
    ]
    cols_to_show = [c for c in cols_to_show if c in df_local.columns]
    st.dataframe(df_local[cols_to_show].tail(50), use_container_width=True, height=320)
    idx = st.number_input("Record index (0-based)", min_value=0, max_value=max(0, len(df_local) - 1), value=max(0, len(df_local) - 1), step=1, key="audit_idx")
    row = df_local.iloc[int(idx)]
    c1, c2 = st.columns([1.2, 1.0])
    with c1:
        st.markdown("### Decision summary")
        st.json({
            "step_id": int(row["step_id"]),
            "mode": row["mode"],
            "scenario": row["scenario"],
            "active_event": row["active_event"],
            "primary_hotspot_name": row.get("primary_hotspot_name"),
            "decision_route": row["decision_route"],
            "route_reason": row["route_reason"],
            "exec_ms": int(row["exec_ms"]),
            "confidence": float(row["decision_confidence"]),
            "fallback_triggered": bool(row["fallback_triggered"]),
            "fallback_reasons": row["fallback_reasons"],
        })
        st.markdown("### Urban state snapshot")
        st.json({
            "network_speed_index": float(row["network_speed_index"]),
            "corridor_reliability_index": float(row["corridor_reliability_index"]),
            "bus_bunching_index": float(row["bus_bunching_index"]),
            "curb_occupancy_rate": float(row["curb_occupancy_rate"]),
            "risk_score": float(row["risk_score"]),
            "gateway_delay_index": float(row["gateway_delay_index"]),
            "complexity_score": float(row["complexity_score"]),
            "discrete_ratio": float(row["discrete_ratio"]),
        })
    with c2:
        render_hotspot_card(
            row.get("primary_hotspot_name"),
            note=row.get("scenario_note"),
            lat=row.get("primary_hotspot_lat"),
            lon=row.get("primary_hotspot_lon"),
        )
    b1, b2 = st.columns(2)
    with b1:
        st.markdown("### Dispatch")
        st.json(safe_json_loads(row.get("dispatch_json")))
        st.markdown("### Objective breakdown")
        st.json(safe_json_loads(row.get("objective_breakdown_json")))
    with b2:
        st.markdown("### Quantum Request Envelope")
        qre = safe_json_loads(row.get("qre_json"))
        st.json(qre if qre else {"info": "No QRE generated on this step."})
        st.markdown("### Quantum Result")
        result = safe_json_loads(row.get("result_json"))
        st.json(result if result else {"info": "No quantum result on this step."})
    csv_bytes = df_local.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", data=csv_bytes, file_name="mobility_control_room_run.csv", mime="text/csv", key="dl_mobility_csv")


def _native_line(df_local: pd.DataFrame, cols: dict[str, str]) -> pd.DataFrame:
    if df_local.empty:
        return pd.DataFrame()
    available = {k: v for k, v in cols.items() if k in df_local.columns}
    if not available:
        return pd.DataFrame()
    out = df_local[list(available.keys())].copy()
    out.columns = list(available.values())
    return out


@st.fragment(run_every=0.7)
def detailed_overview_live_fragment() -> None:
    df_local = get_df()
    latest_local = latest_record(df_local)
    if df_local.empty:
        st.caption('No live trend data yet.')
        return
    live_df = df_local.tail(max(18, min(int(st.session_state["live_window"]), 30))).copy()
    st.markdown('### Live mini-trends')
    row = st.columns(4)
    row[0].metric('Network speed', f"{latest_local.get('network_speed_index', 0.0):.2f}")
    row[1].metric('Bus bunching', f"{latest_local.get('bus_bunching_index', 0.0):.2f}")
    row[2].metric('Curb occupancy', f"{latest_local.get('curb_occupancy_rate', 0.0)*100:.1f}%")
    row[3].metric('Risk score', f"{latest_local.get('risk_score', 0.0):.2f}")
    c1, c2 = st.columns(2)
    with c1:
        st.line_chart(_native_line(live_df.set_index('step_id'), {
            'network_speed_index': 'Network speed',
            'corridor_reliability_index': 'Corridor reliability',
        }), height=220, use_container_width=True)
    with c2:
        st.line_chart(_native_line(live_df.set_index('step_id'), {
            'bus_bunching_index': 'Bus bunching',
            'risk_score': 'Risk score',
        }), height=220, use_container_width=True)


@st.fragment(run_every=0.7)
def detailed_twin_live_fragment(twin_sel: str) -> None:
    df_local = get_df()
    latest_local = latest_record(df_local)
    if df_local.empty:
        st.caption('No live trend data yet.')
        return
    live_df = df_local.tail(max(18, min(int(st.session_state["live_window"]), 30))).copy().set_index('step_id')
    st.markdown('### Live mini-trends')
    st.caption(f"Focused asset: {twin_sel.replace('_', ' ').title()} | Route: {format_route(str(latest_local.get('decision_route', '')))}")
    c1, c2 = st.columns(2)
    if twin_sel == 'intersection':
        with c1:
            st.line_chart(_native_line(live_df, {'corridor_delay_s': 'Delay s'}), height=220, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {'risk_score': 'Risk score'}), height=220, use_container_width=True)
    elif twin_sel == 'road_corridor':
        with c1:
            st.line_chart(_native_line(live_df, {
                'network_speed_index': 'Network speed',
                'corridor_reliability_index': 'Reliability',
            }), height=220, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {'gateway_delay_index': 'Gateway delay'}), height=220, use_container_width=True)
    elif twin_sel == 'bus_corridor':
        with c1:
            st.line_chart(_native_line(live_df, {'bus_bunching_index': 'Bunching'}), height=220, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {
                'bus_commercial_speed_kmh': 'Commercial speed',
                'bus_priority_requests': 'Priority requests',
            }), height=220, use_container_width=True)
    elif twin_sel == 'curb_zone':
        with c1:
            st.line_chart(_native_line(live_df, {
                'curb_occupancy_rate': 'Occupancy',
                'illegal_curb_occupancy_rate': 'Illegal occupancy',
            }), height=220, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {'delivery_queue': 'Delivery queue'}), height=220, use_container_width=True)
    else:
        with c1:
            st.line_chart(_native_line(live_df, {
                'risk_score': 'Risk score',
                'near_miss_index': 'Near-miss',
            }), height=220, use_container_width=True)
        with c2:
            st.line_chart(_native_line(live_df, {
                'pedestrian_exposure': 'Pedestrian exposure',
                'bike_conflict_index': 'Bike conflict',
            }), height=220, use_container_width=True)


@st.fragment(run_every=0.7)
def detailed_risk_live_fragment() -> None:
    df_local = get_df()
    latest_local = latest_record(df_local)
    if df_local.empty:
        st.caption('No live trend data yet.')
        return
    live_df = df_local.tail(max(18, min(int(st.session_state["live_window"]), 30))).copy().set_index('step_id')
    st.markdown('### Live mini-trends')
    row = st.columns(4)
    row[0].metric('Risk', f"{latest_local.get('risk_score', 0.0):.2f}")
    row[1].metric('Near-miss', f"{latest_local.get('near_miss_index', 0.0):.2f}")
    row[2].metric('Ped exposure', f"{latest_local.get('pedestrian_exposure', 0.0):.2f}")
    row[3].metric('Bike conflict', f"{latest_local.get('bike_conflict_index', 0.0):.2f}")
    c1, c2 = st.columns(2)
    with c1:
        st.line_chart(_native_line(live_df, {
            'risk_score': 'Risk score',
            'near_miss_index': 'Near-miss',
        }), height=220, use_container_width=True)
    with c2:
        st.line_chart(_native_line(live_df, {
            'pedestrian_exposure': 'Pedestrian exposure',
            'bike_conflict_index': 'Bike conflict',
        }), height=220, use_container_width=True)


init_state()
ss = st.session_state

def apply_runtime_config() -> None:
    ss = st.session_state
    new_scenario = ss.get("scenario_ui", ss["scenario"])
    new_seed = int(ss.get("seed_ui", ss["seed"]))
    changed = (new_scenario != ss["scenario"]) or (new_seed != int(ss["seed"]))
    ss["running"] = False
    if changed:
        ss["scenario"] = new_scenario
        ss["seed"] = new_seed
        rebuild_runtime()

with st.sidebar:
    st.markdown("## Control Panel")

    with st.form("runtime_config_form", clear_on_submit=False):
        st.selectbox(
            "Scenario",
            options=list(SCENARIO_LABELS.keys()),
            format_func=lambda x: SCENARIO_LABELS[x],
            index=list(SCENARIO_LABELS.keys()).index(ss.get("scenario_ui", ss["scenario"])),
            key="scenario_ui",
            help="Changes are only applied when you press Apply scenario / seed.",
        )
        st.number_input(
            "Simulation seed",
            min_value=1,
            max_value=999999,
            value=int(ss.get("seed_ui", ss["seed"])),
            step=1,
            key="seed_ui",
            help="Changes are only applied when you press Apply scenario / seed.",
        )
        applied = st.form_submit_button("Apply scenario / seed", use_container_width=True)
        if applied:
            apply_runtime_config()

    if ss.get("scenario_ui", ss["scenario"]) != ss["scenario"] or int(ss.get("seed_ui", ss["seed"])) != int(ss["seed"]):
        st.caption("Pending configuration change. Press Apply scenario / seed.")

    st.divider()
    ss["live_window"] = st.slider("Visible live window (steps)", 12, 96, int(ss["live_window"]), step=6)
    _live_opts = live_focus_options()
    if ss["live_focus"] not in _live_opts:
        ss["live_focus"] = _live_opts[0]
    ss["live_focus"] = st.selectbox("Live focus", _live_opts, index=_live_opts.index(ss["live_focus"]))

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ Start", use_container_width=True):
            ss["running"] = True
            st.rerun()
    with c2:
        if st.button("⏸ Pause", use_container_width=True):
            ss["running"] = False
            st.rerun()

    c3, c4 = st.columns(2)
    with c3:
        if st.button("⏭ Step", use_container_width=True):
            ss["rt"].step()
            ss["running"] = False
            st.rerun()
    with c4:
        if st.button("⏹ Reset", use_container_width=True):
            rebuild_runtime()
            st.rerun()

st.markdown(
    """
    <div class="hero">
        <div class="hero-title">Hybrid Quantum-Classical Urban Mobility Control Room</div>
        <div class="hero-subtitle">Barcelona corridor safety, transit and urban logistics orchestrator.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

@st.fragment(run_every=0.25)
def live_fragment() -> None:
    if ss["running"]:
        ss["rt"].step()
    frag_df = get_df()
    frag_latest = latest_record(frag_df)
    render_live_monitor(frag_df, frag_latest, ss["live_focus"])

live_fragment()

df = get_df()
latest = latest_record(df)
if latest.get("scenario_note"):
    st.caption(str(latest.get("scenario_note")))

st.markdown("### Detailed views (stable snapshots)")
st.caption("These tabs are kept stable to minimize flicker. The live evolution is shown above in Live Monitor.")

tab_overview, tab_twins, tab_risk, tab_audit = st.tabs(
    ["Overview", "Mobility Twins", "Risk & Prevention", "Audit & Orchestration"]
)

snapshots = ss["rt"].twin_snapshot()

with tab_overview:
    detailed_overview_live_fragment()
    render_overview(df, latest, render_id="static")

with tab_twins:
    st.selectbox(
        "Select twin",
        ["intersection", "road_corridor", "bus_corridor", "curb_zone", "risk_hotspot"],
        index=["intersection", "road_corridor", "bus_corridor", "curb_zone", "risk_hotspot"].index(ss["mobility_twin_sel"]),
        key="mobility_twin_sel",
    )
    detailed_twin_live_fragment(ss["mobility_twin_sel"])
    render_twins_panel(df, snapshots, ss["mobility_twin_sel"], render_id="static")

with tab_risk:
    detailed_risk_live_fragment()
    render_risk_panel(df, latest, render_id="static")

with tab_audit:
    render_audit_panel(df)
