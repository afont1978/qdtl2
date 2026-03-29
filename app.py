
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

st.set_page_config(page_title="Barcelona Mobility Control Room v3", layout="wide")

st.markdown(
    """
    <style>
    .block-container {max-width: 1640px; padding-top: 1rem; padding-bottom: 1.2rem;}
    .hero {padding: 1rem 1.2rem; border: 1px solid rgba(255,255,255,0.08); border-radius: 18px;
           background: linear-gradient(135deg, rgba(18,28,45,0.96), rgba(8,13,24,0.96)); margin-bottom: 1rem;}
    .hero-title {font-size: 2rem; font-weight: 700; color: #F4F7FB; margin-bottom: 0.2rem;}
    .hero-subtitle {font-size: 1rem; color: #C7D0DD;}
    .metric-card {padding: 0.75rem 0.95rem; border-radius: 16px; background: rgba(255,255,255,0.03);
                  border: 1px solid rgba(255,255,255,0.06);}
    .section-card {padding: 0.85rem 1rem; border-radius: 16px; background: rgba(255,255,255,0.03);
                   border: 1px solid rgba(255,255,255,0.06);}
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
LAYER_COLORS = {
    "Intermodal / public transport": [55, 126, 184, 170],
    "Urban core / tourism": [77, 175, 74, 170],
    "Logistics / curb / port": [255, 127, 0, 170],
    "Airport / gateway": [152, 78, 163, 170],
}
DATA_PATH = Path(__file__).with_name("barcelona_mobility_hotspots.csv")


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("scenario", "corridor_congestion")
    ss.setdefault("seed", 42)
    ss.setdefault("running", False)
    ss.setdefault("steps_per_run", 1)
    ss.setdefault("sleep_s", 0.25)
    ss.setdefault("live_window", 36)
    ss.setdefault("twin_sel", "intersection")
    ss.setdefault("map_layers", [
        "Intermodal / public transport",
        "Urban core / tourism",
        "Logistics / curb / port",
        "Airport / gateway",
    ])
    ss.setdefault("focus_hotspot_mode", "Auto (scenario hotspot)")
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
    except Exception:
        return pd.DataFrame(columns=["name", "lat", "lon", "category", "streets", "why", "layer_group"])
    df["layer_group"] = df["category"].apply(layer_group)
    return df


def layer_group(category: str) -> str:
    cat = str(category).lower()
    if "aeroport" in cat or "gateway" in cat:
        return "Airport / gateway"
    if "port" in cat or "logístic" in cat or "logistic" in cat or "mercanc" in cat or "curb" in cat:
        return "Logistics / curb / port"
    if "intermodal" in cat or "bus" in cat or "metro" in cat or "tranv" in cat:
        return "Intermodal / public transport"
    return "Urban core / tourism"


def kpi_block(label: str, value: str, delta: str = "") -> None:
    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
    st.metric(label, value, delta)
    st.markdown("</div>", unsafe_allow_html=True)


def route_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "decision_route" not in df.columns:
        return pd.DataFrame(columns=["route", "count"])
    vc = df["decision_route"].value_counts().reset_index()
    vc.columns = ["route", "count"]
    return vc


def selected_hotspot_name(latest: Dict[str, Any]) -> str | None:
    mode = st.session_state.get("focus_hotspot_mode", "Auto (scenario hotspot)")
    if mode == "Auto (scenario hotspot)":
        return latest.get("primary_hotspot_name") if latest else None
    return mode


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
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=260, showlegend=False)
    return fig


def build_map_data(hotspots_df: pd.DataFrame, latest: Dict[str, Any], layer_filter: list[str], focused_name: str | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if hotspots_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    base = hotspots_df[hotspots_df["layer_group"].isin(layer_filter)].copy()
    if base.empty:
        return pd.DataFrame(), pd.DataFrame()
    base["color"] = base["layer_group"].map(LAYER_COLORS)
    base["radius"] = 140
    focus_name = focused_name or (latest.get("primary_hotspot_name") if latest else None)
    current = base[base["name"] == focus_name].copy() if focus_name else pd.DataFrame(columns=base.columns)
    if not current.empty:
        current["color"] = [[230, 60, 60, 220]] * len(current)
        current["radius"] = 320
    return base, current


def render_city_map(hotspots_df: pd.DataFrame, latest: Dict[str, Any], height: int = 520, focused_name: str | None = None) -> None:
    base, current = build_map_data(hotspots_df, latest, st.session_state.get("map_layers", []), focused_name)
    if base.empty:
        st.info("No hotspot data available for the selected layers.")
        return

    center_lat, center_lon, zoom = 41.3851, 2.1734, 11.8
    if not current.empty:
        row = current.iloc[0]
        center_lat, center_lon, zoom = float(row["lat"]), float(row["lon"]), 12.7

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

    deck = pdk.Deck(
        map_provider="carto",
        map_style="dark",
        initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=zoom, pitch=0),
        layers=layers,
        tooltip={"html": "<b>{name}</b><br/>{category}<br/>{streets}"},
    )
    try:
        st.pydeck_chart(deck, use_container_width=True, height=height)
    except Exception:
        st.info("The interactive basemap could not be rendered in this environment. Showing hotspot coordinates instead.")
        st.dataframe(base[["name", "layer_group", "category", "streets", "lat", "lon"]], use_container_width=True, hide_index=True)


def hotspot_details(name: str | None, hotspots_df: pd.DataFrame) -> dict[str, Any] | None:
    if not name or hotspots_df.empty:
        return None
    row = hotspots_df[hotspots_df["name"] == name]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def render_hotspot_summary(name: str | None, hotspots_df: pd.DataFrame, scenario_note: str | None = None, title: str = "Hotspot") -> None:
    details = hotspot_details(name, hotspots_df)
    if not details:
        st.info("No hotspot information available.")
        return
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown(f"### {title}: {details['name']}")
    st.write(f"**Layer group:** {details['layer_group']}")
    st.write(f"**Category:** {details['category']}")
    st.write(f"**Streets / environment:** {details['streets']}")
    st.write(f"**Operational relevance:** {details['why']}")
    st.caption(f"Coordinates: {details['lat']:.4f}, {details['lon']:.4f}")
    if scenario_note:
        st.caption(str(scenario_note))
    st.markdown("</div>", unsafe_allow_html=True)


def render_summary_table(rows: list[tuple[str, Any]], title: str) -> None:
    df = pd.DataFrame([{"Field": k, "Value": v} for k, v in rows])
    st.markdown(f"### {title}")
    st.dataframe(df, use_container_width=True, hide_index=True)


def twin_snapshot_fields(snapshot: dict) -> list[tuple[str, Any]]:
    rows = []
    for k, v in snapshot.items():
        if k in {"metadata", "alarms", "name", "ts", "twin_id", "asset_type", "enabled"}:
            continue
        if isinstance(v, (int, float, bool)):
            rows.append((k, v))
    return rows[:12]


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

    st.divider()
    ss["map_layers"] = st.multiselect(
        "Visible map layers",
        options=list(LAYER_COLORS.keys()),
        default=ss.get("map_layers", list(LAYER_COLORS.keys())),
    )
    hotspot_options = ["Auto (scenario hotspot)"] + ([] if hotspots_df.empty else hotspots_df["name"].tolist())
    default_focus = ss.get("focus_hotspot_mode", "Auto (scenario hotspot)")
    default_index = hotspot_options.index(default_focus) if default_focus in hotspot_options else 0
    ss["focus_hotspot_mode"] = st.selectbox("Focus hotspot", hotspot_options, index=default_index)

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
focus_name = selected_hotspot_name(latest)

st.markdown(
    """
    <div class="hero">
      <div class="hero-title">Barcelona Mobility Control Room</div>
      <div class="hero-subtitle">Version 3 — central layered map, direct hotspot focus and clearer navigation between overview, twins, risk and audit.</div>
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
        left, right = st.columns([1.8, 1.0])
        with left:
            render_city_map(hotspots_df, latest, height=560, focused_name=focus_name)
        with right:
            render_hotspot_summary(focus_name, hotspots_df, latest.get("scenario_note"), title="Focused hotspot")
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown("### Current decision")
            st.write(f"**Route:** {ROUTE_LABELS.get(str(latest.get('decision_route', '')), '—')}")
            st.write(f"**Reason:** {latest.get('route_reason', '—')}")
            st.write(f"**Active event:** {latest.get('active_event', 'none') or 'none'}")
            st.write(f"**Scenario:** {SCENARIO_LABELS.get(str(latest.get('scenario', '')), '—')}")
            st.markdown("</div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(make_line(live_df, ["network_speed_index", "corridor_reliability_index", "step_operational_score"], "Urban performance"), use_container_width=True)
        with c2:
            st.plotly_chart(make_line(live_df, ["bus_bunching_index", "curb_occupancy_rate", "risk_score", "gateway_delay_index"], "Pressure indicators"), use_container_width=True)

with tab_map:
    st.markdown("## Map & layers")
    if df.empty:
        st.info("No simulation data yet.")
    else:
        top = st.columns([1.8, 1.0])
        with top[0]:
            render_city_map(hotspots_df, latest, height=700, focused_name=focus_name)
        with top[1]:
            render_hotspot_summary(focus_name, hotspots_df, latest.get("scenario_note"), title="Selected hotspot")
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown("### Active layer filters")
            st.write(", ".join(ss.get("map_layers", [])) or "No layers selected")
            st.write(f"**Focus mode:** {ss.get('focus_hotspot_mode', 'Auto (scenario hotspot)')}")
            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("### Hotspot catalogue")
        catalogue = hotspots_df[["name", "layer_group", "category", "streets", "lat", "lon"]].copy() if not hotspots_df.empty else hotspots_df
        st.dataframe(catalogue, use_container_width=True, height=340)

with tab_twins:
    if df.empty:
        st.info("No simulation data yet.")
    else:
        snapshots = ss["rt"].twin_snapshot()
        twin_options = ["intersection", "road_corridor", "bus_corridor", "curb_zone", "risk_hotspot"]
        default_twin = ss.get("twin_sel", "intersection")
        ss["twin_sel"] = st.selectbox("Select twin", twin_options, index=twin_options.index(default_twin) if default_twin in twin_options else 0)
        twin_sel = ss["twin_sel"]
        snap = snapshots.get(twin_sel, {})
        md = snap.get("metadata", {}) if isinstance(snap, dict) else {}

        cols = st.columns([1.2, 1.0])
        with cols[0]:
            render_summary_table([
                ("Twin", twin_sel.replace("_", " ").title()),
                ("Twin hotspot", md.get("hotspot_name", "—")),
                ("Category", md.get("category", "—")),
                ("Streets", md.get("streets", "—")),
                ("Scenario note", md.get("scenario_note", latest.get("scenario_note", "—"))),
            ], "Twin identity")
            render_summary_table(twin_snapshot_fields(snap), "Current operational state")
        with cols[1]:
            twin_hotspot = md.get("hotspot_name") or focus_name
            render_hotspot_summary(twin_hotspot, hotspots_df, md.get("scenario_note") or latest.get("scenario_note"), title="Twin hotspot")

        wdf = df.tail(int(ss["live_window"]))
        if twin_sel == "intersection":
            st.plotly_chart(make_line(wdf, ["corridor_delay_s", "risk_score"], "Intersection-oriented trend", "Index / seconds"), use_container_width=True)
        elif twin_sel == "road_corridor":
            st.plotly_chart(make_line(wdf, ["network_speed_index", "corridor_reliability_index", "gateway_delay_index"], "Road corridor trend"), use_container_width=True)
        elif twin_sel == "bus_corridor":
            st.plotly_chart(make_line(wdf, ["bus_bunching_index", "bus_commercial_speed_kmh"], "Bus corridor trend", "Index / km/h"), use_container_width=True)
        elif twin_sel == "curb_zone":
            st.plotly_chart(make_line(wdf, ["curb_occupancy_rate", "illegal_curb_occupancy_rate", "delivery_queue"], "Curbside trend", "Rate / queue"), use_container_width=True)
        elif twin_sel == "risk_hotspot":
            st.plotly_chart(make_line(wdf, ["risk_score", "near_miss_index", "pedestrian_exposure", "bike_conflict_index"], "Risk hotspot trend"), use_container_width=True)

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
        bottom = st.columns([1.0, 1.2])
        with bottom[0]:
            render_hotspot_summary(focus_name, hotspots_df, latest.get("scenario_note"), title="Risk context hotspot")
        with bottom[1]:
            show_cols = [c for c in ["step_id", "active_event", "risk_score", "near_miss_index", "pedestrian_exposure", "bike_conflict_index", "decision_route"] if c in live_df.columns]
            st.dataframe(live_df[show_cols].tail(12), use_container_width=True)

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
        render_hotspot_summary(row.get("primary_hotspot_name"), hotspots_df, row.get("scenario_note"), title="Audit hotspot")
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
