
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from mobility_runtime import MobilityRuntime

st.set_page_config(page_title="Barcelona Mobility Control Room v5", layout="wide")

st.markdown(
    """
    <style>
    .block-container {max-width: 1660px; padding-top: 1rem; padding-bottom: 1.2rem;}
    .hero {padding: 1rem 1.2rem; border: 1px solid rgba(255,255,255,0.08); border-radius: 18px;
           background: linear-gradient(135deg, rgba(18,28,45,0.96), rgba(8,13,24,0.96)); margin-bottom: 1rem;}
    .hero-title {font-size: 2rem; font-weight: 700; color: #F4F7FB; margin-bottom: 0.2rem;}
    .hero-subtitle {font-size: 1rem; color: #C7D0DD;}
    .metric-card {padding: 0.75rem 0.95rem; border-radius: 16px; background: rgba(255,255,255,0.03);
                  border: 1px solid rgba(255,255,255,0.06);}
    .section-card {padding: 0.85rem 1rem; border-radius: 16px; background: rgba(255,255,255,0.03);
                   border: 1px solid rgba(255,255,255,0.06);}
    .small-note {font-size: 0.92rem; color: #B7C3D6;}
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
    ss.setdefault("live_window", 36)
    ss.setdefault("live_interval_s", 1.0)
    ss.setdefault("map_layers", list(LAYER_COLORS.keys()))
    ss.setdefault("focus_hotspot_mode", "Auto (scenario hotspot)")
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


def layer_group(category: str) -> str:
    cat = str(category).lower()
    if "aeroport" in cat or "gateway" in cat:
        return "Airport / gateway"
    if "port" in cat or "logístic" in cat or "logistic" in cat or "mercanc" in cat or "curb" in cat:
        return "Logistics / curb / port"
    if "intermodal" in cat or "bus" in cat or "metro" in cat or "tranv" in cat:
        return "Intermodal / public transport"
    return "Urban core / tourism"


def load_hotspots() -> pd.DataFrame:
    try:
        df = pd.read_csv(DATA_PATH)
    except Exception:
        return pd.DataFrame(columns=["name", "lat", "lon", "category", "streets", "why", "layer_group"])
    df["layer_group"] = df["category"].apply(layer_group)
    return df


def selected_hotspot_name(latest: Dict[str, Any]) -> str | None:
    mode = st.session_state.get("focus_hotspot_mode", "Auto (scenario hotspot)")
    if mode == "Auto (scenario hotspot)":
        return latest.get("primary_hotspot_name") if latest else None
    return mode


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
    layers = [pdk.Layer("ScatterplotLayer", data=base, get_position='[lon, lat]', get_fill_color="color", get_radius="radius", pickable=True, auto_highlight=True)]
    if not current.empty:
        layers.append(pdk.Layer("ScatterplotLayer", data=current, get_position='[lon, lat]', get_fill_color="color", get_radius="radius", pickable=True, auto_highlight=True))
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
        st.info("The basemap could not be rendered in this environment. Showing hotspot coordinates instead.")
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


def metric_label(key: str) -> str:
    labels = {
        "network_speed_index": "Network speed index",
        "corridor_reliability_index": "Corridor reliability",
        "corridor_delay_s": "Corridor delay [s]",
        "bus_bunching_index": "Bus bunching",
        "bus_commercial_speed_kmh": "Bus commercial speed [km/h]",
        "curb_occupancy_rate": "Curb occupancy",
        "illegal_curb_occupancy_rate": "Illegal curb occupancy",
        "delivery_queue": "Delivery queue",
        "risk_score": "Risk score",
        "near_miss_index": "Near-miss index",
        "pedestrian_exposure": "Pedestrian exposure",
        "gateway_delay_index": "Gateway delay",
        "step_operational_score": "Operational score",
    }
    return labels.get(key, key)


def project_what_if(latest: Dict[str, Any], focused_name: str | None, controls: Dict[str, Any]) -> Dict[str, Any]:
    if not latest:
        return {}
    proj = dict(latest)
    shock = controls.get("shock", "None")
    bus_priority = int(controls.get("bus_priority", 0))
    enforcement = int(controls.get("enforcement", 0))
    ped_protection = bool(controls.get("ped_protection", False))
    diversion = bool(controls.get("diversion", False))

    nsi = float(proj.get("network_speed_index", 0.0))
    cri = float(proj.get("corridor_reliability_index", 0.0))
    cds = float(proj.get("corridor_delay_s", 0.0))
    bbi = float(proj.get("bus_bunching_index", 0.0))
    bcs = float(proj.get("bus_commercial_speed_kmh", 0.0))
    cor = float(proj.get("curb_occupancy_rate", 0.0))
    icor = float(proj.get("illegal_curb_occupancy_rate", 0.0))
    dq = float(proj.get("delivery_queue", 0.0))
    rs = float(proj.get("risk_score", 0.0))
    nm = float(proj.get("near_miss_index", 0.0))
    pe = float(proj.get("pedestrian_exposure", 0.0))
    bc = float(proj.get("bike_conflict_index", 0.0))
    gd = float(proj.get("gateway_delay_index", 0.0))

    if shock == "Rain event":
        nsi -= 0.08; cri -= 0.06; cds += 8; bbi += 0.03; rs += 0.08; nm += 0.05; bc += 0.04
    elif shock == "Incident on corridor":
        nsi -= 0.15; cri -= 0.14; cds += 18; bbi += 0.06; rs += 0.10; gd += 0.07
    elif shock == "Delivery wave":
        cor += 0.10; icor += 0.08; dq += 4; rs += 0.03
    elif shock == "Gateway surge":
        gd += 0.16; nsi -= 0.06; cri -= 0.05; cds += 7
    elif shock == "Event release":
        nsi -= 0.10; cri -= 0.08; cds += 10; bbi += 0.05; gd += 0.08; pe += 0.07
    elif shock == "School peak":
        rs += 0.10; nm += 0.06; pe += 0.10; bc += 0.03

    if bus_priority > 0:
        nsi += 0.02 * bus_priority; cri += 0.03 * bus_priority; cds -= 2.5 * bus_priority
        bbi -= 0.05 * bus_priority; bcs += 0.8 * bus_priority
    if enforcement > 0:
        cor -= 0.02 * enforcement; icor -= 0.08 * enforcement; dq -= 1.2 * enforcement; rs -= 0.01 * enforcement
    if ped_protection:
        rs -= 0.07; nm -= 0.05; pe -= 0.04; nsi -= 0.02; cds += 2.5
    if diversion:
        nsi += 0.05; cri += 0.04; cds -= 4.0; gd -= 0.03; cor += 0.02

    proj["network_speed_index"] = float(max(0.0, min(1.3, nsi)))
    proj["corridor_reliability_index"] = float(max(0.0, min(1.3, cri)))
    proj["corridor_delay_s"] = float(max(0.0, cds))
    proj["bus_bunching_index"] = float(max(0.0, min(1.0, bbi)))
    proj["bus_commercial_speed_kmh"] = float(max(5.0, min(30.0, bcs)))
    proj["curb_occupancy_rate"] = float(max(0.0, min(1.0, cor)))
    proj["illegal_curb_occupancy_rate"] = float(max(0.0, min(1.0, icor)))
    proj["delivery_queue"] = float(max(0.0, dq))
    proj["risk_score"] = float(max(0.0, min(1.0, rs)))
    proj["near_miss_index"] = float(max(0.0, min(1.0, nm)))
    proj["pedestrian_exposure"] = float(max(0.0, min(1.0, pe)))
    proj["bike_conflict_index"] = float(max(0.0, min(1.0, bc)))
    proj["gateway_delay_index"] = float(max(0.0, min(1.0, gd)))

    step_score = (
        0.30 * proj["network_speed_index"]
        + 0.20 * proj["corridor_reliability_index"]
        + 0.15 * (1.0 - proj["bus_bunching_index"])
        + 0.15 * (1.0 - (0.55 * proj["curb_occupancy_rate"] + 0.45 * proj["illegal_curb_occupancy_rate"]))
        + 0.20 * (1.0 - proj["risk_score"])
    )
    proj["step_operational_score"] = float(step_score)
    proj["primary_hotspot_name"] = focused_name or proj.get("primary_hotspot_name")

    route = "CLASSICAL"
    reason = "Classical intervention package remains sufficient for this hotspot."
    subproblem = "local_control_problem"
    complexity = 4.8
    if shock in {"Delivery wave", "Gateway surge", "Event release"} or (bus_priority >= 2 and enforcement >= 1) or (diversion and shock == "Incident on corridor"):
        route = "QUANTUM"
        reason = "Hybrid route suggested because the hotspot combines several discrete interventions with competing objectives."
        subproblem = "multimodal_redispatch_problem"
        complexity = 6.0
    if shock in {"School peak", "Rain event"} and ped_protection:
        route = "CLASSICAL"
        reason = "Classical route preferred because the package is safety-critical and latency sensitive."
        subproblem = "safety_protection_problem"
        complexity = 5.2

    proj["what_if_route"] = route
    proj["what_if_reason"] = reason
    proj["what_if_subproblem"] = subproblem
    proj["what_if_complexity"] = complexity
    proj["what_if_shock"] = shock
    return proj


def metric_delta_rows(before: Dict[str, Any], after: Dict[str, Any], keys: list[str]) -> pd.DataFrame:
    rows = []
    for k in keys:
        b = before.get(k)
        a = after.get(k)
        if b is None or a is None:
            continue
        rows.append({
            "Metric": metric_label(k),
            "Baseline": round(float(b), 4),
            "Projected": round(float(a), 4),
            "Delta": round(float(a) - float(b), 4),
        })
    return pd.DataFrame(rows)


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
    ss["live_interval_s"] = st.slider("Live refresh interval (s)", 0.5, 2.0, float(ss["live_interval_s"]), step=0.1)

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
    st.caption("Stable live mode: only the top Live Monitor auto-refreshes. The rest of the app stays static to minimize flicker.")

st.markdown(
    """
    <div class="hero">
      <div class="hero-title">Barcelona Mobility Control Room</div>
      <div class="hero-subtitle">Version 5 — stable real-time architecture. A dedicated Live Monitor auto-refreshes while detailed views stay static to minimize flicker.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

run_every = f"{ss['live_interval_s']}s" if ss.get("running", False) else None

@st.fragment(run_every=run_every)
def live_monitor_fragment():
    if st.session_state.get("running", False):
        st.session_state["rt"].step()

    df = get_df()
    latest = latest_record(df)
    focus_name = selected_hotspot_name(latest)

    st.markdown("## Live Monitor")
    if df.empty:
        st.info("No simulation data yet. Press Step or Start.")
        return

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

    st.caption("This is the only auto-refreshing surface. Streamlit fragments rerun independently of the full app, which keeps the rest of the interface stable and reduces flicker. However, elements inside the fragment are still redrawn on each fragment rerun, so keeping this live area lightweight is important. See Streamlit fragments docs. citeturn0search0turn0search2")

    live_df = df.tail(int(st.session_state.get("live_window", 36))).copy()
    c1, c2 = st.columns(2)
    with c1:
        st.line_chart(live_df.set_index("step_id")[[c for c in ["network_speed_index", "corridor_reliability_index", "step_operational_score"] if c in live_df.columns]], use_container_width=True)
    with c2:
        st.line_chart(live_df.set_index("step_id")[[c for c in ["bus_bunching_index", "risk_score", "gateway_delay_index"] if c in live_df.columns]], use_container_width=True)
    c3, c4 = st.columns(2)
    with c3:
        st.line_chart(live_df.set_index("step_id")[[c for c in ["curb_occupancy_rate", "illegal_curb_occupancy_rate", "delivery_queue"] if c in live_df.columns]], use_container_width=True)
    with c4:
        st.line_chart(live_df.set_index("step_id")[[c for c in ["near_miss_index", "pedestrian_exposure", "bike_conflict_index"] if c in live_df.columns]], use_container_width=True)

    detail_left, detail_right = st.columns([1.5, 1.0])
    with detail_left:
        render_hotspot_summary(focus_name, hotspots_df, latest.get("scenario_note"), title="Focused hotspot")
    with detail_right:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Current live decision")
        st.write(f"**Route:** {ROUTE_LABELS.get(str(latest.get('decision_route', '')), '—')}")
        st.write(f"**Reason:** {latest.get('route_reason', '—')}")
        st.write(f"**Active event:** {latest.get('active_event', 'none') or 'none'}")
        st.write(f"**Primary hotspot:** {latest.get('primary_hotspot_name', '—')}")
        st.markdown("</div>", unsafe_allow_html=True)

live_monitor_fragment()

df = get_df()
latest = latest_record(df)
focus_name = selected_hotspot_name(latest)

tab_overview, tab_map, tab_twins, tab_risk, tab_sim, tab_audit = st.tabs([
    "Overview snapshot",
    "Map & Layers",
    "Mobility Twins",
    "Risk & Prevention",
    "What-if & Simulation",
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
            st.markdown("### Snapshot decision")
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
            render_summary_table([(k, v) for k, v in twin_snapshot_fields(snap)], "Current operational state")
        with cols[1]:
            twin_hotspot = md.get("hotspot_name") or focus_name
            render_hotspot_summary(twin_hotspot, hotspots_df, md.get("scenario_note") or latest.get("scenario_note"), title="Twin hotspot")

with tab_risk:
    if df.empty:
        st.info("No simulation data yet.")
    else:
        live_df = df.tail(int(ss["live_window"])).copy()
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(make_line(live_df, ["risk_score", "near_miss_index"], "Risk evolution"), use_container_width=True)
        with c2:
            st.plotly_chart(make_line(live_df, ["pedestrian_exposure", "bike_conflict_index"], "Exposure and conflict"), use_container_width=True)
        render_hotspot_summary(focus_name, hotspots_df, latest.get("scenario_note"), title="Risk hotspot")


with tab_sim:
    st.markdown("## What-if & Simulation")
    if df.empty:
        st.info("Run at least one step before launching a contextual what-if analysis.")
    else:
        left, right = st.columns([1.0, 1.2])
        with left:
            render_hotspot_summary(focus_name, hotspots_df, latest.get("scenario_note"), title="Simulation focus")
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown("### Goal")
            st.write("Build a quick before / after estimate for the selected hotspot without changing the running simulation.")
            st.markdown("</div>", unsafe_allow_html=True)

            with st.form("what_if_form"):
                shock = st.selectbox(
                    "Stress or context change",
                    ["None", "Rain event", "Incident on corridor", "Delivery wave", "Gateway surge", "Event release", "School peak"],
                    index=0,
                )
                bus_priority = st.slider("Increase bus priority", 0, 2, 1)
                enforcement = st.slider("Increase curbside enforcement", 0, 2, 0)
                ped_protection = st.checkbox("Activate pedestrian protection", value=False)
                diversion = st.checkbox("Activate diversion / re-routing", value=False)
                simulate = st.form_submit_button("Run what-if on focused hotspot", use_container_width=True)

        if "what_if_controls" not in ss:
            ss["what_if_controls"] = {
                "shock": "None",
                "bus_priority": 1,
                "enforcement": 0,
                "ped_protection": False,
                "diversion": False,
            }
        if simulate:
            ss["what_if_controls"] = {
                "shock": shock,
                "bus_priority": bus_priority,
                "enforcement": enforcement,
                "ped_protection": ped_protection,
                "diversion": diversion,
            }

        projected = project_what_if(latest, focus_name, ss["what_if_controls"])
        with right:
            delta_df = metric_delta_rows(
                latest,
                projected,
                [
                    "network_speed_index", "corridor_reliability_index", "corridor_delay_s",
                    "bus_bunching_index", "bus_commercial_speed_kmh",
                    "curb_occupancy_rate", "illegal_curb_occupancy_rate", "delivery_queue",
                    "risk_score", "near_miss_index", "pedestrian_exposure",
                    "gateway_delay_index", "step_operational_score",
                ],
            )
            top = st.columns(3)
            with top[0]:
                kpi_block("Projected route", ROUTE_LABELS.get(projected.get("what_if_route", "CLASSICAL"), "Classical"))
            with top[1]:
                delta_score = projected.get("step_operational_score", 0.0) - latest.get("step_operational_score", 0.0)
                kpi_block("Δ operational score", f"{delta_score:+.3f}")
            with top[2]:
                kpi_block("Subproblem", projected.get("what_if_subproblem", "—"))

            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown("### What-if interpretation")
            st.write(projected.get("what_if_reason", "No explanation available."))
            st.write(f"**Shock:** {projected.get('what_if_shock', 'None')}")
            st.write(f"**Focused hotspot:** {projected.get('primary_hotspot_name', focus_name or '—')}")
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("### Before / after")
            st.dataframe(delta_df, use_container_width=True, hide_index=True, height=420)

            compare_df = pd.DataFrame({
                "State": ["Baseline", "Projected"],
                "Operational score": [latest.get("step_operational_score", 0.0), projected.get("step_operational_score", 0.0)],
                "Risk": [latest.get("risk_score", 0.0), projected.get("risk_score", 0.0)],
                "Network speed": [latest.get("network_speed_index", 0.0), projected.get("network_speed_index", 0.0)],
            })
            fig = go.Figure()
            for metric in ["Operational score", "Risk", "Network speed"]:
                fig.add_trace(go.Bar(x=compare_df["State"], y=compare_df[metric], name=metric))
            fig.update_layout(template="plotly_dark", title="Scenario comparison", height=320, margin=dict(l=20, r=20, t=50, b=20), barmode="group")
            st.plotly_chart(fig, use_container_width=True)

with tab_audit:
    if df.empty:
        st.info("No records yet.")
    else:
        cols_to_show = [
            "step_id", "ts", "mode", "scenario", "active_event", "primary_hotspot_name",
            "decision_route", "exec_ms", "decision_confidence", "step_operational_score", "fallback_triggered"
        ]
        cols_to_show = [c for c in cols_to_show if c in df.columns]
        st.dataframe(df[cols_to_show].tail(60), use_container_width=True, height=320)
        idx = st.number_input("Record index (0-based)", min_value=0, max_value=max(0, len(df)-1), value=max(0, len(df)-1), step=1)
        row = df.iloc[int(idx)]
        c1, c2 = st.columns(2)
        with c1:
            render_summary_table([
                ("Step", int(row["step_id"])),
                ("Mode", MODE_LABELS.get(str(row["mode"]), str(row["mode"]))),
                ("Scenario", SCENARIO_LABELS.get(str(row["scenario"]), str(row["scenario"]))),
                ("Active event", row.get("active_event", "none") or "none"),
                ("Primary hotspot", row.get("primary_hotspot_name", "—")),
                ("Route", ROUTE_LABELS.get(str(row["decision_route"]), str(row["decision_route"]))),
                ("Reason", row.get("route_reason", "—")),
            ], "Decision summary")
        with c2:
            render_summary_table([
                ("Network speed", float(row.get("network_speed_index", 0.0))),
                ("Corridor reliability", float(row.get("corridor_reliability_index", 0.0))),
                ("Bus bunching", float(row.get("bus_bunching_index", 0.0))),
                ("Curb occupancy", float(row.get("curb_occupancy_rate", 0.0))),
                ("Risk", float(row.get("risk_score", 0.0))),
                ("Gateway delay", float(row.get("gateway_delay_index", 0.0))),
            ], "Urban state snapshot")
        render_hotspot_summary(row.get("primary_hotspot_name"), hotspots_df, row.get("scenario_note"), title="Audit hotspot")
        with st.expander("Technical detail"):
            st.markdown("### Dispatch")
            st.json(safe_json_loads(row.get("dispatch_json")))
            st.markdown("### Objective breakdown")
            st.json(safe_json_loads(row.get("objective_breakdown_json")))
            st.markdown("### Quantum Request Envelope")
            st.json(safe_json_loads(row.get("qre_json")) or {"info": "No QRE generated on this step."})
            st.markdown("### Quantum Result")
            st.json(safe_json_loads(row.get("result_json")) or {"info": "No quantum result on this step."})
