
import json
import time
from typing import Any, Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from mobility_runtime import MobilityRuntime

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
                  border:1px solid rgba(255,255,255,0.06); margin-bottom: 0.8rem;}
    .small-note {color:#AEB8C7; font-size:0.92rem;}
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
    ss.setdefault("seed", 42)
    ss.setdefault("running", False)
    ss.setdefault("sleep_s", 0.30)
    ss.setdefault("batch_steps", 4)
    ss.setdefault("live_window", 36)
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
    hotspot_map(lat, lon, label=str(name or 'Hotspot'))


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


init_state()
ss = st.session_state

with st.sidebar:
    st.markdown("## Control Panel")
    selected_scenario = st.selectbox(
        "Scenario",
        options=list(SCENARIO_LABELS.keys()),
        format_func=lambda x: SCENARIO_LABELS[x],
        index=list(SCENARIO_LABELS.keys()).index(ss["scenario"]),
    )
    if selected_scenario != ss["scenario"]:
        ss["scenario"] = selected_scenario
        rebuild_runtime()
        st.rerun()
    seed = st.number_input("Simulation seed", min_value=1, max_value=999999, value=int(ss["seed"]), step=1)
    if int(seed) != int(ss["seed"]):
        ss["seed"] = int(seed)
        rebuild_runtime()
        st.rerun()
    st.divider()
    ss["live_window"] = st.slider("Visible live window (steps)", 12, 96, int(ss["live_window"]), step=6)
    ss["batch_steps"] = st.slider("Steps per visible run", 1, 24, int(ss["batch_steps"]), step=1)
    ss["sleep_s"] = st.slider("Delay between visible steps (s)", 0.05, 1.00, float(ss["sleep_s"]), step=0.05)
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ Start", use_container_width=True):
            ss["running"] = True
    with c2:
        if st.button("⏸ Pause", use_container_width=True):
            ss["running"] = False
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

df = get_df()
latest = latest_record(df)


def render_overview(df_local: pd.DataFrame, latest_local: Dict[str, Any], render_id: str = "base") -> None:
    if df_local.empty:
        st.info("No simulation data yet. Press Step or Start.")
        return

    live_df = df_local.tail(int(ss["live_window"])).copy()
    q_share = (df_local["decision_route"] == "QUANTUM").mean() * 100.0 if len(df_local) else 0.0
    fb_rate = df_local["fallback_triggered"].mean() * 100.0 if len(df_local) else 0.0
    avg_latency = float(df_local["exec_ms"].tail(24).mean())
    mean_conf = float(df_local["decision_confidence"].tail(24).mean() * 100.0)

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

st.markdown(
    """
    <div class="hero">
        <div class="hero-title">Hybrid Quantum-Classical Urban Mobility Control Room</div>
        <div class="hero-subtitle">Barcelona corridor safety, transit and urban logistics orchestrator.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if latest.get("scenario_note"):
    st.caption(str(latest.get("scenario_note")))

tab_overview, tab_twins, tab_risk, tab_audit = st.tabs(["Overview", "Mobility Twins", "Risk & Prevention", "Audit & Orchestration"])

with tab_overview:
    overview_placeholder = st.empty()
    if not ss["running"]:
        with overview_placeholder.container():
            render_overview(df, latest, render_id="static")
    else:
        frame_df = df.copy()
        frame_latest = latest.copy()
        for frame in range(int(ss["batch_steps"])):
            ss["rt"].step()
            frame_df = get_df()
            frame_latest = latest_record(frame_df)
            with overview_placeholder.container():
                render_overview(frame_df, frame_latest, render_id=f"live_{frame}")
            time.sleep(float(ss["sleep_s"]))
        st.rerun()

with tab_twins:
    snapshots = ss["rt"].twin_snapshot()
    twin_sel = st.selectbox("Select twin", ["intersection", "road_corridor", "bus_corridor", "curb_zone", "risk_hotspot"], index=0)
    if df.empty:
        st.info("No simulation data yet.")
    else:
        snapshot = snapshots.get(twin_sel, {})
        hotspot = extract_twin_hotspot(snapshot)

        c_top1, c_top2 = st.columns([1.2, 1.0])
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
            st.markdown("### Current twin snapshot")
            st.json(snapshot)

        if twin_sel == "intersection":
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(make_line_chart(df, "step_id", ["corridor_delay_s"], "Intersection / corridor delay", "s", "int_delay"), use_container_width=True, key="plot_int_delay")
            with c2:
                st.plotly_chart(make_line_chart(df, "step_id", ["risk_score"], "Intersection risk", "index", "int_risk"), use_container_width=True, key="plot_int_risk")
        elif twin_sel == "road_corridor":
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(make_line_chart(df, "step_id", ["network_speed_index", "corridor_reliability_index"], "Corridor performance", "index", "corr_perf"), use_container_width=True, key="plot_corr_perf")
            with c2:
                st.plotly_chart(make_line_chart(df, "step_id", ["gateway_delay_index"], "Gateway propagation", "index", "corr_gate"), use_container_width=True, key="plot_corr_gate")
        elif twin_sel == "bus_corridor":
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(make_line_chart(df, "step_id", ["bus_bunching_index"], "Bus bunching", "index", "bus_bunch"), use_container_width=True, key="plot_bus_bunch")
            with c2:
                st.plotly_chart(make_line_chart(df, "step_id", ["bus_commercial_speed_kmh", "bus_priority_requests"], "Bus speed and priority requests", "km/h / count", "bus_speed"), use_container_width=True, key="plot_bus_speed")
        elif twin_sel == "curb_zone":
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(make_line_chart(df, "step_id", ["curb_occupancy_rate", "illegal_curb_occupancy_rate"], "Curb occupancy", "ratio", "curb_occ"), use_container_width=True, key="plot_curb_occ")
            with c2:
                st.plotly_chart(make_line_chart(df, "step_id", ["delivery_queue"], "Delivery queue", "count", "curb_queue"), use_container_width=True, key="plot_curb_queue")
        elif twin_sel == "risk_hotspot":
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(make_line_chart(df, "step_id", ["risk_score", "near_miss_index"], "Risk and near-miss", "index", "risk_main"), use_container_width=True, key="plot_risk_main")
            with c2:
                st.plotly_chart(make_line_chart(df, "step_id", ["pedestrian_exposure", "bike_conflict_index"], "VRU exposure", "index", "risk_vru"), use_container_width=True, key="plot_risk_vru")

with tab_risk:
    if df.empty:
        st.info("No simulation data yet.")
    else:
        c1, c2 = st.columns([1.6, 1.0])
        with c1:
            c11, c12 = st.columns(2)
            with c11:
                st.plotly_chart(make_line_chart(df, "step_id", ["risk_score", "near_miss_index"], "Risk and early-warning state", "index", "risk_tab_main"), use_container_width=True, key="plot_risk_tab_main")
            with c12:
                st.plotly_chart(make_line_chart(df, "step_id", ["pedestrian_exposure", "bike_conflict_index"], "Exposure of vulnerable users", "index", "risk_tab_vru"), use_container_width=True, key="plot_risk_tab_vru")
            risk_view = df[[c for c in ["step_id", "active_event", "primary_hotspot_name", "risk_score", "near_miss_index", "pedestrian_exposure", "bike_conflict_index", "route_reason"] if c in df.columns]].tail(20)
            st.dataframe(risk_view, use_container_width=True, height=320)
        with c2:
            st.markdown("### Current risk hotspot")
            render_hotspot_card(
                latest.get("risk_hotspot_name") or latest.get("primary_hotspot_name"),
                note=latest.get("scenario_note"),
                lat=latest.get("primary_hotspot_lat"),
                lon=latest.get("primary_hotspot_lon"),
            )

with tab_audit:
    if df.empty:
        st.info("No records yet.")
    else:
        cols_to_show = [
            "step_id", "ts", "mode", "scenario", "active_event", "primary_hotspot_name", "decision_route",
            "route_reason", "exec_ms", "decision_confidence", "fallback_triggered",
            "network_speed_index", "bus_bunching_index", "curb_occupancy_rate", "risk_score"
        ]
        cols_to_show = [c for c in cols_to_show if c in df.columns]
        st.dataframe(df[cols_to_show].tail(50), use_container_width=True, height=320)
        idx = st.number_input("Record index (0-based)", min_value=0, max_value=max(0, len(df) - 1), value=max(0, len(df) - 1), step=1)
        row = df.iloc[int(idx)]
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
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data=csv_bytes, file_name="mobility_control_room_run.csv", mime="text/csv", key="dl_mobility_csv")
