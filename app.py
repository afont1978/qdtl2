from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from mobility_runtime import MobilityRuntime

st.set_page_config(page_title="Barcelona Mobility Control Room", layout="wide")

st.markdown(
    """
    <style>
    .block-container {max-width: 1600px; padding-top: 1rem; padding-bottom: 1.5rem;}
    .hero {padding: 1rem 1.2rem; border: 1px solid rgba(255,255,255,0.08); border-radius: 18px;
           background: linear-gradient(135deg, rgba(20,30,48,0.96), rgba(9,14,28,0.96)); margin-bottom: 1rem;}
    .hero-title {font-size: 2rem; font-weight: 700; color: #F4F7FB; margin-bottom: 0.2rem;}
    .hero-subtitle {font-size: 1rem; color: #C7D0DD;}
    .metric-card {padding: 0.75rem 0.95rem; border-radius: 16px; background: rgba(255,255,255,0.03);
                  border: 1px solid rgba(255,255,255,0.06);}
    .section-card {padding: 0.85rem 1rem; border-radius: 16px; background: rgba(255,255,255,0.03);
                   border: 1px solid rgba(255,255,255,0.06);}
    .small-muted {color:#A8B5C7; font-size:0.9rem;}
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
ROUTE_LABELS = {
    "CLASSICAL": "Classical",
    "QUANTUM": "Quantum",
    "FALLBACK_CLASSICAL": "Fallback → Classical",
}
ROUTE_COLORS = {
    "CLASSICAL": "#4E79A7",
    "QUANTUM": "#9C6ADE",
    "FALLBACK_CLASSICAL": "#F28E2B",
}
DATA_PATH = Path(__file__).with_name("barcelona_mobility_hotspots.csv")


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("scenario", "corridor_congestion")
    ss.setdefault("seed", 42)
    ss.setdefault("pending_scenario", ss["scenario"])
    ss.setdefault("pending_seed", int(ss["seed"]))
    ss.setdefault("running", False)
    ss.setdefault("steps_per_run", 1)
    ss.setdefault("sleep_s", 0.25)
    ss.setdefault("live_window", 36)
    ss.setdefault("twin_sel", "intersection")
    ss.setdefault("rt", MobilityRuntime(scenario=ss["scenario"], seed=int(ss["seed"])))


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


def load_hotspots() -> pd.DataFrame:
    try:
        df = pd.read_csv(DATA_PATH)
        return df
    except Exception:
        return pd.DataFrame(columns=["name", "lat", "lon", "category", "streets", "why"])


def kpi_block(label: str, value: str, delta: str = "") -> None:
    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
    st.metric(label, value, delta)
    st.markdown("</div>", unsafe_allow_html=True)


def build_map_df(hotspots_df: pd.DataFrame, latest: Dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if hotspots_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    base = hotspots_df.copy()
    base["color"] = [[70, 130, 180, 160]] * len(base)
    base["radius"] = 110

    current_name = latest.get("primary_hotspot_name") if latest else None
    selected_name = latest.get("primary_hotspot_name") if latest else None
    current = base[base["name"] == current_name].copy() if current_name else pd.DataFrame(columns=base.columns)
    if not current.empty:
        current["color"] = [[230, 60, 60, 220]] * len(current)
        current["radius"] = 260
    return base, current


def render_city_map(hotspots_df: pd.DataFrame, latest: Dict[str, Any], height: int = 520) -> None:
    base, current = build_map_df(hotspots_df, latest)
    if base.empty:
        st.info("No hotspot data available.")
        return

    layers = [
        pdk.Layer(
            "ScatterplotLayer",
            data=base,
            get_position='[lon, lat]',
            get_fill_color="color",
            get_radius="radius",
            pickable=True,
            auto_highlight=True,
        )
    ]
    if not current.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=current,
                get_position='[lon, lat]',
                get_fill_color="color",
                get_radius="radius",
                pickable=True,
                auto_highlight=True,
            )
        )

    view_state = pdk.ViewState(latitude=41.3851, longitude=2.1734, zoom=11.8, pitch=0)
    deck = pdk.Deck(
        map_provider="carto",
        map_style="dark",
        initial_view_state=view_state,
        layers=layers,
        tooltip={"html": "<b>{name}</b><br/>{category}<br/>{streets}"},
    )
    try:
        st.pydeck_chart(deck, use_container_width=True, height=height)
    except Exception:
        st.info("The interactive basemap could not be rendered in this environment. Showing hotspot coordinates instead.")
        st.dataframe(base[["name", "category", "streets", "lat", "lon"]], use_container_width=True, hide_index=True)


def route_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "decision_route" not in df.columns:
        return pd.DataFrame(columns=["route", "count"])
    vc = df["decision_route"].value_counts().reset_index()
    vc.columns = ["route", "count"]
    return vc


def make_line(df: pd.DataFrame, cols: list[str], title: str, y_title: str = "Index") -> go.Figure:
    fig = go.Figure()
    for col in cols:
        if col in df.columns:
            fig.add_trace(go.Scatter(x=df["step_id"], y=df[col], mode="lines", name=col, line=dict(width=2)))
    fig.update_layout(
        title=title,
        template="plotly_dark",
        margin=dict(l=20, r=20, t=50, b=20),
        height=300,
        xaxis_title="Step",
        yaxis_title=y_title,
        legend=dict(orientation="h"),
    )
    return fig


def make_routes(df: pd.DataFrame) -> go.Figure:
    rc = route_counts(df)
    fig = px.bar(rc, x="route", y="count", color="route", color_discrete_map=ROUTE_COLORS, template="plotly_dark", title="Decision mix")
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=250, showlegend=False)
    return fig


def render_hotspot_summary(latest: Dict[str, Any], hotspots_df: pd.DataFrame) -> None:
    if not latest:
        st.info("No active hotspot yet.")
        return
    name = latest.get("primary_hotspot_name")
    if not name or hotspots_df.empty:
        st.info("No hotspot information available.")
        return
    row = hotspots_df[hotspots_df["name"] == name]
    if row.empty:
        st.info("No hotspot information available.")
        return
    row = row.iloc[0]
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown(f"### {row['name']}")
    st.write(f"**Category:** {row['category']}")
    st.write(f"**Streets / environment:** {row['streets']}")
    st.write(f"**Operational relevance:** {row['why']}")
    note = latest.get("scenario_note")
    if note:
        st.caption(str(note))
    st.markdown("</div>", unsafe_allow_html=True)


def render_summary_table(rows: list[tuple[str, Any]], title: str) -> None:
    df = pd.DataFrame([{"Field": k, "Value": v} for k, v in rows])
    st.markdown(f"### {title}")
    st.dataframe(df, use_container_width=True, hide_index=True)


init_state()
ss = st.session_state
hotspots_df = load_hotspots()

with st.sidebar:
    st.markdown("## Control panel")
    with st.form("scenario_form"):
        scenario_choice = st.selectbox(
            "Scenario",
            options=list(SCENARIO_LABELS.keys()),
            format_func=lambda x: SCENARIO_LABELS[x],
            index=list(SCENARIO_LABELS.keys()).index(ss["scenario"]),
        )
        seed_choice = st.number_input("Simulation seed", min_value=1, max_value=999999, value=int(ss["seed"]), step=1)
        submitted = st.form_submit_button("Apply scenario / seed", use_container_width=True)
        if submitted:
            ss["scenario"] = scenario_choice
            ss["seed"] = int(seed_choice)
            rebuild_runtime()
            st.success("Configuration applied.")

    st.divider()
    ss["live_window"] = st.slider("Visible live window", 12, 96, int(ss["live_window"]), step=6)
    ss["steps_per_run"] = st.slider("Steps per run", 1, 4, int(ss["steps_per_run"]), step=1)
    ss["sleep_s"] = st.slider("Delay between runs (s)", 0.10, 0.80, float(ss["sleep_s"]), step=0.05)

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

    st.divider()
    st.caption(f"Current scenario: {SCENARIO_LABELS[ss['scenario']]}")
    st.caption(f"Seed: {ss['seed']}")

if ss["running"]:
    for _ in range(int(ss["steps_per_run"])):
        ss["rt"].step()
    time.sleep(float(ss["sleep_s"]))
    st.rerun()

df = get_df()
latest = latest_record(df)

st.markdown(
    """
    <div class="hero">
      <div class="hero-title">Barcelona Mobility Control Room</div>
      <div class="hero-subtitle">Version 2 — central city map, real Barcelona hotspots, stable scenario switching and a cleaner operator layout.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not df.empty:
    row1 = st.columns(6)
    with row1[0]:
        kpi_block("Mode", MODE_LABELS.get(str(latest.get("mode", "")), str(latest.get("mode", "—"))))
    with row1[1]:
        kpi_block("Network speed", f"{latest.get('network_speed_index', 0.0):.2f}")
    with row1[2]:
        kpi_block("Corridor reliability", f"{latest.get('corridor_reliability_index', 0.0):.2f}")
    with row1[3]:
        kpi_block("Bus bunching", f"{latest.get('bus_bunching_index', 0.0):.2f}")
    with row1[4]:
        kpi_block("Risk", f"{latest.get('risk_score', 0.0):.2f}")
    with row1[5]:
        kpi_block("Gateway delay", f"{latest.get('gateway_delay_index', 0.0):.2f}")

    row2 = st.columns(5)
    with row2[0]:
        kpi_block("Decision route", ROUTE_LABELS.get(str(latest.get("decision_route", "")), "—"))
    with row2[1]:
        kpi_block("Confidence", f"{float(latest.get('decision_confidence', 0.0))*100:.1f}%")
    with row2[2]:
        kpi_block("Latency", f"{int(latest.get('exec_ms', 0))} ms")
    with row2[3]:
        q_share = (df["decision_route"] == "QUANTUM").mean() * 100.0 if "decision_route" in df.columns else 0.0
        kpi_block("Quantum share", f"{q_share:.1f}%")
    with row2[4]:
        fb_rate = df["fallback_triggered"].mean() * 100.0 if "fallback_triggered" in df.columns else 0.0
        kpi_block("Fallback rate", f"{fb_rate:.1f}%")
else:
    st.info("No simulation data yet. Press Step or Start.")

tab_overview, tab_map, tab_twins, tab_risk, tab_audit = st.tabs([
    "Overview",
    "Map & Layers",
    "Mobility Twins",
    "Risk & Prevention",
    "Audit & Orchestration",
])

with tab_overview:
    if df.empty:
        st.info("No simulation data yet.")
    else:
        live_df = df.tail(int(ss["live_window"])).copy()
        left, right = st.columns([1.7, 1.0])
        with left:
            render_city_map(hotspots_df, latest, height=560)
        with right:
            render_hotspot_summary(latest, hotspots_df)
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown("### Current decision")
            st.write(f"**Route:** {ROUTE_LABELS.get(str(latest.get('decision_route', '')), '—')}")
            st.write(f"**Reason:** {latest.get('route_reason', '—')}")
            st.write(f"**Active event:** {latest.get('active_event', 'none') or 'none'}")
            st.markdown("</div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(make_line(live_df, ["network_speed_index", "corridor_reliability_index", "step_operational_score"], "Urban performance"), use_container_width=True)
        with c2:
            st.plotly_chart(make_line(live_df, ["bus_bunching_index", "curb_occupancy_rate", "risk_score", "gateway_delay_index"], "Pressure indicators"), use_container_width=True)

with tab_map:
    st.markdown("## Central map")
    if df.empty:
        st.info("No simulation data yet.")
    else:
        render_city_map(hotspots_df, latest, height=680)
        st.markdown("### Hotspot catalogue")
        st.dataframe(hotspots_df, use_container_width=True, height=320)

with tab_twins:
    if df.empty:
        st.info("No simulation data yet.")
    else:
        snapshots = ss["rt"].twin_snapshot()
        twin_options = ["intersection", "road_corridor", "bus_corridor", "curb_zone", "risk_hotspot"]
        ss["twin_sel"] = st.selectbox("Select twin", twin_options, index=twin_options.index(ss.get("twin_sel", "intersection")))
        twin_sel = ss["twin_sel"]
        snap = snapshots.get(twin_sel, {})
        md = snap.get("metadata", {}) if isinstance(snap, dict) else {}
        cols = st.columns([1.2, 1.0])
        with cols[0]:
            render_summary_table([
                ("Twin", twin_sel.replace("_", " ").title()),
                ("Hotspot", md.get("hotspot_name", "—")),
                ("Category", md.get("category", "—")),
                ("Streets", md.get("streets", "—")),
                ("Scenario note", md.get("scenario_note", latest.get("scenario_note", "—"))),
            ], "Active twin")
            numeric_rows = []
            for k, v in snap.items():
                if k not in {"metadata", "alarms", "name", "ts", "twin_id", "asset_type", "enabled"} and isinstance(v, (int, float, bool)):
                    numeric_rows.append((k, v))
            render_summary_table(numeric_rows[:10], "Key state variables")
        with cols[1]:
            render_hotspot_summary({"primary_hotspot_name": md.get("hotspot_name") or latest.get("primary_hotspot_name"), "scenario_note": md.get("scenario_note") or latest.get("scenario_note")}, hotspots_df)
        if twin_sel == "intersection":
            st.plotly_chart(make_line(df.tail(ss["live_window"]), ["corridor_delay_s", "risk_score"], "Intersection-oriented trend", "Index / seconds"), use_container_width=True)
        elif twin_sel == "road_corridor":
            st.plotly_chart(make_line(df.tail(ss["live_window"]), ["network_speed_index", "corridor_reliability_index", "gateway_delay_index"], "Road corridor trend"), use_container_width=True)
        elif twin_sel == "bus_corridor":
            st.plotly_chart(make_line(df.tail(ss["live_window"]), ["bus_bunching_index", "bus_commercial_speed_kmh"], "Bus corridor trend", "Index / km/h"), use_container_width=True)
        elif twin_sel == "curb_zone":
            st.plotly_chart(make_line(df.tail(ss["live_window"]), ["curb_occupancy_rate", "illegal_curb_occupancy_rate", "delivery_queue"], "Curbside trend", "Rate / queue"), use_container_width=True)
        elif twin_sel == "risk_hotspot":
            st.plotly_chart(make_line(df.tail(ss["live_window"]), ["risk_score", "near_miss_index", "pedestrian_exposure", "bike_conflict_index"], "Risk hotspot trend"), use_container_width=True)

with tab_risk:
    if df.empty:
        st.info("No simulation data yet.")
    else:
        live_df = df.tail(int(ss["live_window"])).copy()
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(make_line(live_df, ["risk_score", "near_miss_index"], "Risk evolution"), use_container_width=True)
        with c2:
            st.plotly_chart(make_line(live_df, ["pedestrian_exposure", "bike_conflict_index", "gateway_delay_index"], "Exposure and conflict"), use_container_width=True)
        render_hotspot_summary(latest, hotspots_df)
        st.dataframe(live_df[[c for c in ["step_id", "active_event", "risk_score", "near_miss_index", "pedestrian_exposure", "bike_conflict_index", "decision_route"] if c in live_df.columns]].tail(12), use_container_width=True)

with tab_audit:
    if df.empty:
        st.info("No simulation data yet.")
    else:
        cols = [c for c in ["step_id", "mode", "scenario", "active_event", "primary_hotspot_name", "decision_route", "route_reason", "exec_ms", "decision_confidence", "fallback_triggered"] if c in df.columns]
        st.dataframe(df[cols].tail(50), use_container_width=True, height=280)
        idx = st.number_input("Record index", min_value=0, max_value=max(0, len(df)-1), value=max(0, len(df)-1), step=1)
        row = df.iloc[int(idx)]
        c1, c2 = st.columns(2)
        with c1:
            render_summary_table([
                ("Step", int(row["step_id"])),
                ("Mode", MODE_LABELS.get(str(row.get("mode", "")), str(row.get("mode", "—")))),
                ("Scenario", SCENARIO_LABELS.get(str(row.get("scenario", "")), str(row.get("scenario", "—")))),
                ("Hotspot", row.get("primary_hotspot_name", "—")),
                ("Decision route", ROUTE_LABELS.get(str(row.get("decision_route", "")), str(row.get("decision_route", "—")))),
                ("Route reason", row.get("route_reason", "—")),
                ("Latency", f"{int(row.get('exec_ms', 0))} ms"),
            ], "Decision summary")
        with c2:
            render_summary_table([
                ("Network speed", row.get("network_speed_index", "—")),
                ("Corridor reliability", row.get("corridor_reliability_index", "—")),
                ("Bus bunching", row.get("bus_bunching_index", "—")),
                ("Curb occupancy", row.get("curb_occupancy_rate", "—")),
                ("Risk", row.get("risk_score", "—")),
                ("Gateway delay", row.get("gateway_delay_index", "—")),
            ], "Urban state snapshot")
        render_hotspot_summary({"primary_hotspot_name": row.get("primary_hotspot_name"), "scenario_note": row.get("scenario_note")}, hotspots_df)
        st.markdown("### Technical detail")
        with st.expander("Show dispatch / objective / hybrid detail"):
            st.markdown("**Dispatch**")
            st.json(safe_json_loads(row.get("dispatch_json")))
            st.markdown("**Objective breakdown**")
            st.json(safe_json_loads(row.get("objective_breakdown_json")))
            st.markdown("**Quantum Request Envelope**")
            qre = safe_json_loads(row.get("qre_json"))
            st.json(qre if qre else {"info": "No QRE generated on this step."})
            st.markdown("**Quantum Result**")
            result = safe_json_loads(row.get("result_json"))
            st.json(result if result else {"info": "No quantum result on this step."})

