
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
    .block-container {max-width: 1680px; padding-top: 0.85rem; padding-bottom: 1.3rem;}
    .hero {padding: 1.05rem 1.2rem; border: 1px solid rgba(255,255,255,0.07); border-radius: 22px;
           background: radial-gradient(circle at top left, rgba(38,53,83,0.96), rgba(11,16,26,0.98) 60%);
           margin-bottom: 1rem; box-shadow: 0 12px 28px rgba(0,0,0,0.25);}
    .hero-title {font-size: 2rem; font-weight: 750; color: #F4F7FB; margin-bottom: 0.15rem; letter-spacing: 0.01em;}
    .hero-subtitle {font-size: 0.98rem; color: #C9D4E3; line-height: 1.4;}
    .metric-shell {padding: 0.8rem 0.95rem; border-radius: 18px; background: linear-gradient(180deg, rgba(255,255,255,0.038), rgba(255,255,255,0.02));
                   border: 1px solid rgba(255,255,255,0.07); min-height: 110px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);}
    .metric-shell::before {content: ''; display: block; height: 4px; border-radius: 8px; margin: -0.25rem -0.25rem 0.6rem -0.25rem;}
    .metric-shell.neutral::before {background: linear-gradient(90deg, #6baed6, #4e79a7);}
    .metric-shell.good::before {background: linear-gradient(90deg, #5ad66f, #2ca25f);}
    .metric-shell.warn::before {background: linear-gradient(90deg, #ffd166, #f39c12);}
    .metric-shell.alert::before {background: linear-gradient(90deg, #ff8a65, #e74c3c);}
    .metric-eyebrow {font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.08em; color: #95A7BF; margin-bottom: 0.45rem;}
    .metric-value {font-size: 1.6rem; font-weight: 730; color: #F7FAFF; line-height: 1.1;}
    .metric-delta {font-size: 0.85rem; color: #B8C6D8; margin-top: 0.4rem;}
    .section-card {padding: 0.85rem 1rem; border-radius: 18px; background: rgba(255,255,255,0.028);
                   border: 1px solid rgba(255,255,255,0.06); box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);}
    .section-title {font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.08em; color: #9FB0C6; margin-bottom: 0.55rem;}
    .small-note {font-size: 0.88rem; color: #AFC0D4;}
    .chip-row {display:flex; gap:0.45rem; flex-wrap:wrap; margin:0.2rem 0 0.75rem 0;}
    .chip {display:inline-flex; align-items:center; gap:0.35rem; padding:0.26rem 0.58rem; border-radius:999px; font-size:0.78rem; font-weight:600; border:1px solid rgba(255,255,255,0.07);}
    .chip.neutral {background:rgba(94,138,196,0.16); color:#dbe8ff;}
    .chip.good {background:rgba(76,175,80,0.16); color:#e6ffe8;}
    .chip.warn {background:rgba(255,193,7,0.16); color:#fff3cc;}
    .chip.alert {background:rgba(244,67,54,0.16); color:#ffdede;}
    .chip.dim {background:rgba(255,255,255,0.06); color:#d0dae6;}
    .subgrid-note {font-size: 0.84rem; color: #B7C3D6;}
    div[data-testid="stDataFrame"] div[role="table"] {border-radius: 14px; overflow: hidden;}
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
def resolve_hotspots_path() -> Path:
    candidates = [
        Path(__file__).with_name("barcelona_mobility_hotspots.csv"),
        Path(__file__).parent / "data" / "barcelona_mobility_hotspots.csv",
        Path.cwd() / "barcelona_mobility_hotspots.csv",
        Path.cwd() / "data" / "barcelona_mobility_hotspots.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


DATA_PATH = resolve_hotspots_path()


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


def chip(text: str, tone: str = "neutral") -> str:
    return f'<span class="chip {tone}">{text}</span>'


def kpi_block(label: str, value: str, delta: str = "", tone: str = "neutral") -> None:
    st.markdown(
        f"""
        <div class="metric-shell {tone}">
          <div class="metric-eyebrow">{label}</div>
          <div class="metric-value">{value}</div>
          <div class="metric-delta">{delta or '&nbsp;'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def tone_from_value(value: float, higher_is_better: bool = True) -> str:
    try:
        v = float(value)
    except Exception:
        return "neutral"
    if higher_is_better:
        if v >= 0.75:
            return "good"
        if v >= 0.5:
            return "neutral"
        if v >= 0.3:
            return "warn"
        return "alert"
    else:
        if v <= 0.25:
            return "good"
        if v <= 0.45:
            return "neutral"
        if v <= 0.65:
            return "warn"
        return "alert"


def route_tone(route: str) -> str:
    return {"CLASSICAL": "neutral", "QUANTUM": "warn", "FALLBACK_CLASSICAL": "alert"}.get(route, "neutral")


def render_chip_row(items: list[tuple[str, str]]) -> None:
    html = '<div class="chip-row">' + ''.join(chip(text, tone) for text, tone in items if text) + '</div>'
    st.markdown(html, unsafe_allow_html=True)


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


def make_group_bar(df: pd.DataFrame, x: str, y: str, color: str | None, title: str, height: int = 280) -> go.Figure:
    fig = px.bar(df, x=x, y=y, color=color, template="plotly_dark", title=title)
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=height, showlegend=bool(color))
    return fig


def make_delta_bar(delta_df: pd.DataFrame, top_n: int = 8) -> go.Figure:
    if delta_df.empty:
        return go.Figure()
    plot_df = delta_df.copy()
    plot_df["abs_delta"] = plot_df["Delta"].abs()
    plot_df = plot_df.sort_values("abs_delta", ascending=False).head(top_n)
    fig = px.bar(plot_df, x="Delta", y="Metric", orientation="h", template="plotly_dark", title="Metric deltas", color="Delta", color_continuous_scale="RdBu")
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=320, coloraxis_showscale=False)
    return fig


def make_route_mix_chart(df: pd.DataFrame) -> go.Figure:
    rc = route_counts(df)
    if rc.empty:
        return go.Figure()
    fig = px.pie(rc, names="route", values="count", hole=0.58, template="plotly_dark", title="Route mix", color="route", color_discrete_map=ROUTE_COLORS)
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=280, showlegend=True)
    return fig


def make_subsystem_score_chart(latest: Dict[str, Any]) -> go.Figure:
    if not latest:
        return go.Figure()
    curb_pressure = 0.55 * float(latest.get("curb_occupancy_rate", 0.0) or 0.0) + 0.45 * float(latest.get("illegal_curb_occupancy_rate", 0.0) or 0.0)
    data = pd.DataFrame({
        "Subsystem": ["Traffic", "Transit", "Risk", "Logistics", "Gateway"],
        "Score": [
            float(latest.get("network_speed_index", 0.0) or 0.0),
            max(0.0, 1.0 - float(latest.get("bus_bunching_index", 0.0) or 0.0)),
            max(0.0, 1.0 - float(latest.get("risk_score", 0.0) or 0.0)),
            max(0.0, 1.0 - curb_pressure),
            max(0.0, 1.0 - float(latest.get("gateway_delay_index", 0.0) or 0.0)),
        ],
    })
    fig = px.bar(data, x="Score", y="Subsystem", orientation="h", template="plotly_dark", title="Subsystem scoreboard", color="Subsystem", color_discrete_sequence=["#4E79A7", "#53C6D9", "#F06565", "#9C6ADE", "#F39C12"])
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=300, showlegend=False, xaxis_range=[0,1.05])
    return fig


def make_signal_phase_chart(signals_df: pd.DataFrame) -> go.Figure:
    if signals_df.empty:
        return go.Figure()
    counts = signals_df["phase"].value_counts().reindex(["Emerging","Active","Clearing"], fill_value=0).reset_index()
    counts.columns = ["Phase", "Count"]
    fig = px.bar(counts, x="Phase", y="Count", template="plotly_dark", title="Signal phases", color="Phase", color_discrete_map={"Emerging":"#ffd166","Active":"#ff6b6b","Clearing":"#95a5a6"})
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=260, showlegend=False)
    return fig


def make_window_df(df: pd.DataFrame, idx: int, radius: int = 8) -> pd.DataFrame:
    if df.empty:
        return df
    lo = max(0, idx - radius)
    hi = min(len(df), idx + radius + 1)
    return df.iloc[lo:hi].copy()


def make_scatter_compare(before: Dict[str, Any], after: Dict[str, Any], metrics: list[str], title: str = "Before vs projected") -> go.Figure:
    rows = []
    for m in metrics:
        if m in before and m in after:
            rows.append({"Metric": metric_label(m), "State": "Baseline", "Value": float(before[m])})
            rows.append({"Metric": metric_label(m), "State": "Projected", "Value": float(after[m])})
    plot_df = pd.DataFrame(rows)
    if plot_df.empty:
        return go.Figure()
    fig = px.bar(plot_df, x="Metric", y="Value", color="State", barmode="group", template="plotly_dark", title=title)
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=340)
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
    st.markdown(f"### {title}")
    render_chip_row([
        (str(details.get("layer_group", "—")), "neutral"),
        (str(details.get("category", "—")), "dim"),
        (f"{float(details.get('lat', 0.0)):.3f}, {float(details.get('lon', 0.0)):.3f}", "dim"),
    ])
    c1, c2 = st.columns([1.35, 0.85])
    with c1:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Location</div>', unsafe_allow_html=True)
        st.markdown(f"**{details['name']}**")
        st.caption(str(details.get("streets", "—")))
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Scenario anchor</div>', unsafe_allow_html=True)
        st.write(scenario_note or "—")
        st.markdown("</div>", unsafe_allow_html=True)
    with st.expander("Operational context", expanded=False):
        st.caption(str(details.get("why", "No additional note available.")))


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

    hotspot_lower = (focused_name or proj.get("primary_hotspot_name") or "").lower()
    asset_focus = "gateway" if any(k in hotspot_lower for k in ["aeropuerto", "port", "moll", "terminal", "plaça cerdà", "zona franca"]) else (
        "intermodal" if any(k in hotspot_lower for k in ["glòries", "espanya", "catalunya", "sants"]) else "urban_node"
    )

    rec_action = "Maintain current operational package"
    rec_priority = "Medium"
    rec_expected = "Stabilise the hotspot without major side effects."
    rec_owner = "Urban operations"

    if shock == "Incident on corridor":
        if diversion:
            rec_action = "Activate corridor diversion package and coordinated signal plan"
            rec_expected = "Reduce corridor delay and protect network reliability at the cost of slightly higher local curb pressure."
        else:
            rec_action = "Deploy incident response corridor plan with selective diversion"
            rec_expected = "Contain delay propagation and queue spillback around the hotspot."
        rec_priority = "High"
        rec_owner = "Traffic control"
    elif shock == "Rain event":
        if ped_protection:
            rec_action = "Enable pedestrian protection and temporary speed mitigation"
            rec_expected = "Lower risk and near-miss exposure, with a moderate penalty in corridor speed."
        else:
            rec_action = "Prepare wet-weather safety plan and monitor vulnerable-user exposure"
            rec_expected = "Prevent risk escalation while preserving base traffic coordination."
        rec_priority = "High"
        rec_owner = "Safety operations"
    elif shock == "School peak":
        rec_action = "Activate school-area protection package and crossing supervision logic"
        rec_expected = "Reduce pedestrian exposure and conflict around the hotspot during the peak window."
        rec_priority = "High"
        rec_owner = "Safety operations"
    elif shock == "Delivery wave":
        if enforcement > 0:
            rec_action = "Tighten curbside enforcement and reallocate DUM slots"
            rec_expected = "Reduce illegal curb use and delivery queue pressure in the selected hotspot."
        else:
            rec_action = "Reallocate delivery windows and prioritise legal curbside turnover"
            rec_expected = "Contain logistics saturation while limiting pedestrian conflict."
        rec_priority = "High"
        rec_owner = "Logistics / curbside"
    elif shock == "Gateway surge":
        rec_action = "Activate gateway staging and access metering package"
        rec_expected = "Reduce gateway delay and smooth arrivals/departures across the selected access node."
        rec_priority = "High"
        rec_owner = "Gateway operations"
    elif shock == "Event release":
        rec_action = "Launch event dispersal package with multimodal rebalancing"
        rec_expected = "Absorb the post-event surge with better corridor reliability and bus regularity."
        rec_priority = "High"
        rec_owner = "Event mobility"
    elif bus_priority >= 2:
        rec_action = "Increase bus priority and coordinated holding on the focused corridor"
        rec_expected = "Improve regularity and reduce bunching, with manageable side effects on general traffic."
        rec_priority = "Medium"
        rec_owner = "Transit operations"
    elif enforcement >= 1:
        rec_action = "Increase curbside enforcement around the hotspot"
        rec_expected = "Reduce illegal occupancy and improve logistics turnover."
        rec_priority = "Medium"
        rec_owner = "Logistics / curbside"
    elif ped_protection:
        rec_action = "Enable local pedestrian protection mode"
        rec_expected = "Lower exposure and near-miss indicators around the hotspot."
        rec_priority = "Medium"
        rec_owner = "Safety operations"
    elif diversion:
        rec_action = "Apply targeted re-routing for the focused hotspot"
        rec_expected = "Relieve corridor delay and improve reliability, with limited spillover elsewhere."
        rec_priority = "Medium"
        rec_owner = "Traffic control"

    if asset_focus == "gateway" and shock in {"Gateway surge", "Incident on corridor"}:
        rec_action += " with gateway-specific coordination"
    elif asset_focus == "intermodal" and bus_priority >= 1:
        rec_action += " and intermodal priority tuning"

    proj["what_if_route"] = route
    proj["what_if_reason"] = reason
    proj["what_if_subproblem"] = subproblem
    proj["what_if_complexity"] = complexity
    proj["what_if_shock"] = shock
    proj["recommended_action"] = rec_action
    proj["recommended_priority"] = rec_priority
    proj["recommended_expected_impact"] = rec_expected
    proj["recommended_owner"] = rec_owner
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


def recommend_action_from_record(row: Dict[str, Any]) -> Dict[str, str]:
    event = str(row.get("active_event") or "none")
    hotspot_name = str(row.get("primary_hotspot_name") or "")
    route = str(row.get("decision_route") or "CLASSICAL")
    risk = float(row.get("risk_score", 0.0) or 0.0)
    bunching = float(row.get("bus_bunching_index", 0.0) or 0.0)
    curb_occ = float(row.get("curb_occupancy_rate", 0.0) or 0.0)
    illegal_curb = float(row.get("illegal_curb_occupancy_rate", 0.0) or 0.0)
    gateway_delay = float(row.get("gateway_delay_index", 0.0) or 0.0)
    network_speed = float(row.get("network_speed_index", 0.0) or 0.0)

    hotspot_lower = hotspot_name.lower()
    asset_focus = "gateway" if any(k in hotspot_lower for k in ["aeropuerto", "port", "moll", "terminal", "plaça cerdà", "zona franca"]) else (
        "intermodal" if any(k in hotspot_lower for k in ["glòries", "espanya", "catalunya", "sants"]) else "urban_node"
    )

    action = "Maintain current operational package"
    priority = "Medium"
    owner = "Urban operations"
    expected = "Preserve the current balance between flow, safety and curbside performance."
    subproblem = "local_control_problem"

    if event == "incident":
        action = "Deploy incident response package with diversion and coordinated corridor timing"
        priority = "High"
        owner = "Traffic control"
        expected = "Contain queue spillback and protect corridor reliability around the hotspot."
        subproblem = "incident_response_portfolio_problem"
    elif event == "school_peak" or risk >= 0.62:
        action = "Enable pedestrian protection and local speed mitigation around the hotspot"
        priority = "High"
        owner = "Safety operations"
        expected = "Reduce vulnerable-user exposure and near-miss probability with a moderate traffic penalty."
        subproblem = "safety_protection_problem"
    elif event == "delivery_wave" or illegal_curb >= 0.22 or curb_occ >= 0.72:
        action = "Tighten curbside enforcement and reallocate legal DUM slots"
        priority = "High"
        owner = "Logistics / curbside"
        expected = "Lower illegal curb use, improve turnover and reduce pedestrian conflict."
        subproblem = "curb_allocation_problem"
    elif event == "gateway_surge" or gateway_delay >= 0.55:
        action = "Activate access metering and staging package for the gateway"
        priority = "High"
        owner = "Gateway operations"
        expected = "Reduce access delay and smooth arrivals/departures at the selected gateway."
        subproblem = "gateway_resource_problem"
    elif event == "event_release":
        action = "Launch event dispersal package with multimodal priority tuning"
        priority = "High"
        owner = "Event mobility"
        expected = "Absorb the post-event surge with better bus regularity and corridor performance."
        subproblem = "event_release_rebalancing_problem"
    elif event == "bus_bunching" or bunching >= 0.32:
        action = "Increase bus priority and coordinated holding on the focused corridor"
        priority = "Medium"
        owner = "Transit operations"
        expected = "Reduce bunching and improve commercial speed with limited side effects on general traffic."
        subproblem = "bus_priority_problem"
    elif network_speed <= 0.58:
        action = "Activate coordinated corridor timing and selective diversion"
        priority = "Medium"
        owner = "Traffic control"
        expected = "Improve network speed and travel-time reliability in the focused area."
        subproblem = "signal_coordination_problem"

    if asset_focus == "gateway" and "gateway" not in owner.lower():
        action += " with gateway-specific coordination"
    elif asset_focus == "intermodal" and owner in {"Traffic control", "Transit operations", "Urban operations"}:
        action += " and intermodal priority tuning"

    if route == "QUANTUM":
        route_note = "Hybrid route suggests this package is worth solving as a discrete multiobjective intervention."
    elif route == "FALLBACK_CLASSICAL":
        route_note = "The system would prefer a classical deployment because the hybrid attempt was not admissible."
    else:
        route_note = "The system considers this package manageable with deterministic coordination."

    return {
        "action": action,
        "priority": priority,
        "owner": owner,
        "expected": expected,
        "subproblem": subproblem,
        "route_note": route_note,
    }



def _signal_value_from_metrics(layer: str, metrics: Dict[str, float]) -> tuple[float, str, str, str]:
    if layer == "Intermodal / public transport":
        relevant_value = max(metrics["bus_bunching_index"], 1.0 - min(metrics["corridor_reliability_index"], 1.0))
        return (
            relevant_value,
            "Transit and corridor stress",
            "BUS",
            f"Bus bunching {metrics['bus_bunching_index']:.2f}; corridor reliability {metrics['corridor_reliability_index']:.2f}.",
        )
    if layer == "Logistics / curb / port":
        relevant_value = max(
            0.55 * metrics["curb_occupancy_rate"] + 0.45 * metrics["illegal_curb_occupancy_rate"],
            min(metrics["delivery_queue"] / 15.0, 1.0),
            metrics["gateway_delay_index"] * 0.9,
        )
        return (
            relevant_value,
            "Logistics and curbside pressure",
            "LOG",
            f"Curb occupancy {metrics['curb_occupancy_rate']:.2f}; illegal use {metrics['illegal_curb_occupancy_rate']:.2f}; queue {metrics['delivery_queue']:.1f}.",
        )
    if layer == "Airport / gateway":
        relevant_value = max(metrics["gateway_delay_index"], 0.7 * (1.0 - min(metrics["network_speed_index"], 1.0)))
        return (
            relevant_value,
            "Gateway access pressure",
            "GTW",
            f"Gateway delay {metrics['gateway_delay_index']:.2f}; network speed {metrics['network_speed_index']:.2f}.",
        )
    relevant_value = max(metrics["risk_score"], metrics["near_miss_index"], 0.9 * metrics["pedestrian_exposure"])
    return (
        relevant_value,
        "Urban safety and pedestrian pressure",
        "RSK",
        f"Risk {metrics['risk_score']:.2f}; near-miss {metrics['near_miss_index']:.2f}; pedestrian exposure {metrics['pedestrian_exposure']:.2f}.",
    )


def build_hotspot_signals(hotspots_df: pd.DataFrame, history_df: pd.DataFrame, latest: Dict[str, Any], focused_name: str | None) -> pd.DataFrame:
    """
    Build a dynamic signal layer where alerts appear, intensify, clear and disappear
    as the scenario evolves. The map only shows hotspots that are operationally
    relevant right now (or are clearing after having been relevant very recently).
    """
    if hotspots_df.empty:
        return pd.DataFrame()

    records = []
    primary = (latest or {}).get("primary_hotspot_name")
    active_event = (latest or {}).get("active_event") or "none"
    scenario = (latest or {}).get("scenario") or "unknown"

    latest_metrics = {
        "network_speed_index": float((latest or {}).get("network_speed_index", 0.0) or 0.0),
        "corridor_reliability_index": float((latest or {}).get("corridor_reliability_index", 0.0) or 0.0),
        "bus_bunching_index": float((latest or {}).get("bus_bunching_index", 0.0) or 0.0),
        "bus_commercial_speed_kmh": float((latest or {}).get("bus_commercial_speed_kmh", 0.0) or 0.0),
        "curb_occupancy_rate": float((latest or {}).get("curb_occupancy_rate", 0.0) or 0.0),
        "illegal_curb_occupancy_rate": float((latest or {}).get("illegal_curb_occupancy_rate", 0.0) or 0.0),
        "delivery_queue": float((latest or {}).get("delivery_queue", 0.0) or 0.0),
        "risk_score": float((latest or {}).get("risk_score", 0.0) or 0.0),
        "near_miss_index": float((latest or {}).get("near_miss_index", 0.0) or 0.0),
        "pedestrian_exposure": float((latest or {}).get("pedestrian_exposure", 0.0) or 0.0),
        "gateway_delay_index": float((latest or {}).get("gateway_delay_index", 0.0) or 0.0),
    }

    previous_metrics = latest_metrics.copy()
    if history_df is not None and not history_df.empty:
        hist = history_df.tail(8).copy()
        if len(hist) >= 2:
            prev = hist.iloc[:-1].tail(4)
            if not prev.empty:
                for k in previous_metrics.keys():
                    if k in prev.columns:
                        previous_metrics[k] = float(prev[k].mean())

    def classify(level: float) -> str:
        if level >= 0.78:
            return "Critical"
        if level >= 0.58:
            return "Alert"
        if level >= 0.38:
            return "Watch"
        return "Normal"

    def color(level_name: str, phase: str) -> list[int]:
        base = {
            "Normal": [70, 160, 80, 170],
            "Watch": [245, 190, 50, 190],
            "Alert": [245, 120, 35, 210],
            "Critical": [215, 50, 50, 230],
        }[level_name]
        if phase == "Emerging":
            return [min(255, base[0] + 12), min(255, base[1] + 12), min(255, base[2] + 12), 235]
        if phase == "Clearing":
            return [base[0], base[1], base[2], 120]
        return base

    def event_relevance(layer: str, event: str) -> bool:
        mapping = {
            "Intermodal / public transport": {"bus_bunching", "demand_spike", "event_release", "incident"},
            "Logistics / curb / port": {"delivery_wave", "illegal_curb_occupation", "gateway_surge", "incident"},
            "Airport / gateway": {"gateway_surge", "incident", "event_release"},
            "Urban core / tourism": {"school_peak", "rain_event", "incident", "event_release"},
        }
        return event in mapping.get(layer, set())

    for _, row in hotspots_df.iterrows():
        name = row["name"]
        layer = row.get("layer_group", "Urban core / tourism")
        category = str(row.get("category", ""))
        is_primary = name == primary
        is_focused = name == focused_name

        emphasis = 1.0 + (0.22 if is_primary else 0.0) + (0.12 if is_focused else 0.0)
        cur_value, signal_type, short_label, cur_message = _signal_value_from_metrics(layer, latest_metrics)
        prev_value, _, _, _ = _signal_value_from_metrics(layer, previous_metrics)

        if active_event in {"incident", "event_release", "gateway_surge", "delivery_wave", "school_peak", "rain_event", "bus_bunching"}:
            cur_value += 0.08 if is_primary or is_focused else 0.03
            prev_value += 0.03 if event_relevance(layer, active_event) else 0.0

        severity = max(0.0, min(1.0, cur_value * emphasis))
        prev_severity = max(0.0, min(1.0, prev_value * emphasis))
        level = classify(severity)
        relevant_event = event_relevance(layer, active_event)

        if severity >= 0.38 and prev_severity < 0.38:
            phase = "Emerging"
        elif severity >= 0.38:
            phase = "Active"
        elif prev_severity >= 0.38 and severity >= 0.18:
            phase = "Clearing"
        elif relevant_event and severity >= 0.24:
            phase = "Emerging"
        else:
            phase = "Hidden"

        visible = (
            is_primary
            or is_focused
            or phase in {"Emerging", "Active", "Clearing"}
            or (relevant_event and severity >= 0.24)
        )

        if not visible:
            continue

        if phase == "Clearing":
            message = f"Signal is easing. {cur_message}"
        elif phase == "Emerging":
            message = f"Signal is building. {cur_message}"
        else:
            message = cur_message

        records.append({
            "name": name,
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "category": category,
            "streets": row.get("streets", ""),
            "layer_group": layer,
            "is_primary": is_primary,
            "is_focused": is_focused,
            "signal_type": signal_type,
            "short_label": short_label,
            "severity": severity,
            "previous_severity": prev_severity,
            "delta_severity": severity - prev_severity,
            "alert_level": level,
            "phase": phase,
            "color": color(level, phase),
            "radius": 150 + 240 * severity + (80 if is_primary else 0) + (45 if is_focused else 0),
            "active_event": active_event,
            "message": message,
            "scenario": scenario,
            "visible": visible,
        })

    out = pd.DataFrame(records)
    if out.empty:
        return out
    # show strongest first and limit labels later in render
    return out.sort_values(["severity", "is_primary", "is_focused"], ascending=[False, False, False]).reset_index(drop=True)

def make_alert_level_chart(signals_df: pd.DataFrame) -> go.Figure:
    if signals_df.empty:
        return go.Figure()
    counts = signals_df["alert_level"].value_counts().reindex(["Critical", "Alert", "Watch", "Normal"], fill_value=0).reset_index()
    counts.columns = ["Alert level", "Count"]
    fig = px.bar(
        counts,
        x="Alert level",
        y="Count",
        color="Alert level",
        template="plotly_dark",
        title="Alert level distribution",
        color_discrete_map={
            "Critical": "#d73232",
            "Alert": "#f57824",
            "Watch": "#f5be32",
            "Normal": "#46a050",
        },
    )
    fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), height=280, showlegend=False)
    return fig


def render_signals_map(signals_df: pd.DataFrame, height: int = 720) -> None:
    if signals_df.empty:
        st.info("No dynamic hotspot signals available.")
        return

    center_lat = float(signals_df["lat"].mean())
    center_lon = float(signals_df["lon"].mean())
    focused = signals_df[signals_df["is_focused"] | signals_df["is_primary"]]
    if not focused.empty:
        center_lat = float(focused.iloc[0]["lat"])
        center_lon = float(focused.iloc[0]["lon"])

    work = signals_df.copy()
    phase_code = {"Emerging": "E", "Active": "A", "Clearing": "C"}
    work["phase_code"] = work["phase"].map(phase_code).fillna("-")
    work["label_text"] = work["short_label"] + " · " + work["phase_code"]

    top_labels = work.sort_values(["severity", "is_primary", "is_focused"], ascending=[False, False, False]).head(8).copy()

    emerging = work[work["phase"] == "Emerging"].copy()
    active = work[work["phase"] == "Active"].copy()
    clearing = work[work["phase"] == "Clearing"].copy()

    # phase-specific radii and colors to create visual iconography by state
    if not emerging.empty:
        emerging["outer_radius"] = emerging["radius"] * 1.9
        emerging["inner_radius"] = emerging["radius"] * 0.82
        emerging["outer_color"] = [[255, 255, 255, 40] for _ in range(len(emerging))]
        emerging["outline_color"] = [[255, 255, 255, 120] for _ in range(len(emerging))]
    if not active.empty:
        active["inner_radius"] = active["radius"] * 0.95
        active["ring_radius"] = active["radius"] * 1.18
        active["ring_color"] = [[255, 255, 255, 150] for _ in range(len(active))]
    if not clearing.empty:
        clearing["inner_radius"] = clearing["radius"] * 0.72
        clearing["ring_radius"] = clearing["radius"] * 0.98
        clearing["ring_color"] = [[180, 190, 205, 110] for _ in range(len(clearing))]
        clearing["text_color"] = [[210, 215, 225, 160] for _ in range(len(clearing))]
    else:
        clearing["text_color"] = []

    layers = []

    if not emerging.empty:
        layers += [
            pdk.Layer(
                "ScatterplotLayer",
                data=emerging,
                get_position='[lon, lat]',
                get_fill_color="outer_color",
                get_radius="outer_radius",
                pickable=False,
                stroked=False,
                opacity=0.35,
            ),
            pdk.Layer(
                "ScatterplotLayer",
                data=emerging,
                get_position='[lon, lat]',
                get_fill_color="color",
                get_radius="inner_radius",
                pickable=True,
                auto_highlight=True,
                stroked=True,
                get_line_color="outline_color",
                line_width_min_pixels=2,
            ),
        ]

    if not active.empty:
        layers += [
            pdk.Layer(
                "ScatterplotLayer",
                data=active,
                get_position='[lon, lat]',
                get_fill_color="ring_color",
                get_radius="ring_radius",
                pickable=False,
                stroked=False,
                opacity=0.55,
            ),
            pdk.Layer(
                "ScatterplotLayer",
                data=active,
                get_position='[lon, lat]',
                get_fill_color="color",
                get_radius="inner_radius",
                pickable=True,
                auto_highlight=True,
                stroked=True,
                get_line_color=[255,255,255,185],
                line_width_min_pixels=2,
            ),
        ]

    if not clearing.empty:
        layers += [
            pdk.Layer(
                "ScatterplotLayer",
                data=clearing,
                get_position='[lon, lat]',
                get_fill_color="ring_color",
                get_radius="ring_radius",
                pickable=False,
                stroked=False,
                opacity=0.45,
            ),
            pdk.Layer(
                "ScatterplotLayer",
                data=clearing,
                get_position='[lon, lat]',
                get_fill_color="color",
                get_radius="inner_radius",
                pickable=True,
                auto_highlight=True,
                stroked=True,
                get_line_color=[210,215,225,110],
                line_width_min_pixels=1,
            ),
        ]

    layers.append(
        pdk.Layer(
            "TextLayer",
            data=top_labels,
            get_position='[lon, lat]',
            get_text="label_text",
            get_color=[245,245,245,220],
            get_size=15,
            get_alignment_baseline="bottom",
            get_pixel_offset=[0, -14],
        )
    )

    deck = pdk.Deck(
        map_provider="carto",
        map_style="dark",
        initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=11.9, pitch=0),
        layers=layers,
        tooltip={
            "html": "<b>{name}</b><br/><b>{alert_level}</b> · {phase} · {signal_type}<br/>{message}<br/><b>Event:</b> {active_event}<br/><b>Layer:</b> {layer_group}<br/>{streets}",
        },
    )
    try:
        st.pydeck_chart(deck, use_container_width=True, height=height)
    except Exception:
        fallback = work.copy()
        fallback["Map marker state"] = fallback["phase"]
        st.dataframe(
            fallback[["name", "alert_level", "Map marker state", "signal_type", "active_event", "layer_group", "streets", "lat", "lon"]],
            use_container_width=True,
            hide_index=True,
            height=min(520, 42 + 34 * len(fallback)),
        )



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

st.markdown(
    """
    <div class="hero">
      <div class="hero-title">Barcelona Mobility Control Room</div>
      <div class="hero-subtitle">Operational dashboard for synthetic Barcelona mobility: traffic, transit, risk, logistics, gateways, alerts and contextual what-if.</div>
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
        kpi_block("Mode", MODE_LABELS.get(str(latest.get("mode", "")), str(latest.get("mode", "—"))), tone="neutral")
    with row1[1]:
        kpi_block("Network speed", f"{latest.get('network_speed_index', 0.0):.2f}", tone=tone_from_value(float(latest.get('network_speed_index',0.0) or 0.0), True))
    with row1[2]:
        kpi_block("Corridor reliability", f"{latest.get('corridor_reliability_index', 0.0):.2f}", tone=tone_from_value(float(latest.get('corridor_reliability_index',0.0) or 0.0), True))
    with row1[3]:
        kpi_block("Bus bunching", f"{latest.get('bus_bunching_index', 0.0):.2f}", tone=tone_from_value(float(latest.get('bus_bunching_index',0.0) or 0.0), False))
    with row1[4]:
        kpi_block("Risk", f"{latest.get('risk_score', 0.0):.2f}", tone=tone_from_value(float(latest.get('risk_score',0.0) or 0.0), False))
    with row1[5]:
        kpi_block("Gateway delay", f"{latest.get('gateway_delay_index', 0.0):.2f}", tone=tone_from_value(float(latest.get('gateway_delay_index',0.0) or 0.0), False))

    row2 = st.columns(5)
    with row2[0]:
        kpi_block("Decision route", ROUTE_LABELS.get(str(latest.get("decision_route", "")), "—"), tone=route_tone(str(latest.get("decision_route", ""))))
    with row2[1]:
        kpi_block("Confidence", f"{float(latest.get('decision_confidence', 0.0))*100:.1f}%", tone=tone_from_value(float(latest.get('decision_confidence',0.0) or 0.0), True))
    with row2[2]:
        kpi_block("Latency", f"{int(latest.get('exec_ms', 0))} ms", tone=tone_from_value(min(float(latest.get('exec_ms',0) or 0)/1200.0,1.0), False))
    with row2[3]:
        q_share = (df["decision_route"] == "QUANTUM").mean() * 100.0 if "decision_route" in df.columns else 0.0
        kpi_block("Quantum share", f"{q_share:.1f}%", tone="warn" if q_share > 20 else "neutral")
    with row2[4]:
        fb_rate = df["fallback_triggered"].mean() * 100.0 if "fallback_triggered" in df.columns else 0.0
        kpi_block("Fallback rate", f"{fb_rate:.1f}%", tone=tone_from_value(min(fb_rate/100.0,1.0), False))

    live_df = df.tail(int(st.session_state.get("live_window", 36))).copy()
    render_chip_row([
        (f"Hotspot · {latest.get('primary_hotspot_name', '—')}", "neutral"),
        (f"Event · {latest.get('active_event', 'none') or 'none'}", "alert" if (latest.get('active_event') not in [None, 'none']) else "dim"),
        (f"Action · {latest.get('recommended_action', 'n/a')}", "warn"),
    ])
    c1, c2 = st.columns([1.25, 1.0])
    with c1:
        st.line_chart(live_df.set_index("step_id")[[c for c in ["network_speed_index", "corridor_reliability_index", "step_operational_score"] if c in live_df.columns]], use_container_width=True)
    with c2:
        st.plotly_chart(make_subsystem_score_chart(latest), use_container_width=True, key="plotly_1199")
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
        st.markdown('<div class="section-title">Current live decision</div>', unsafe_allow_html=True)
        render_chip_row([
            (ROUTE_LABELS.get(str(latest.get('decision_route', '')), '—'), route_tone(str(latest.get('decision_route', '')))),
            (f"Priority · {latest.get('action_priority', '—')}", "warn"),
            (f"Owner · {latest.get('responsible_layer', '—')}", "dim"),
        ])
        st.write(latest.get('recommended_action', '—'))
        st.caption(latest.get('expected_impact', latest.get('route_reason', '—')))
        st.markdown("</div>", unsafe_allow_html=True)

live_monitor_fragment()

df = get_df()
latest = latest_record(df)
focus_name = selected_hotspot_name(latest)

tab_overview, tab_map, tab_signals, tab_twins, tab_risk, tab_sim, tab_audit = st.tabs([
    "Overview",
    "Map & Layers",
    "Signals & Alerts Map",
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
        left, right = st.columns([1.7, 1.0])
        with left:
            render_city_map(hotspots_df, latest, height=560, focused_name=focus_name)
        with right:
            top_right = st.columns(2)
            with top_right[0]:
                kpi_block("Route", ROUTE_LABELS.get(str(latest.get("decision_route", "")), "—"), tone=route_tone(str(latest.get("decision_route", ""))))
            with top_right[1]:
                kpi_block("Event", str(latest.get("active_event", "none") or "none"), tone="alert" if (latest.get("active_event") not in [None, "none"]) else "dim")
            render_hotspot_summary(focus_name, hotspots_df, latest.get("scenario_note"), title="Focused hotspot")
            if not df.empty:
                st.plotly_chart(make_route_mix_chart(df.tail(max(int(ss["live_window"]), 12))), use_container_width=True, key="plotly_1253")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.plotly_chart(make_line(live_df, ["network_speed_index", "corridor_reliability_index"], "Network dynamics"), use_container_width=True, key="plotly_1256")
        with c2:
            st.plotly_chart(make_line(live_df, ["bus_bunching_index", "bus_commercial_speed_kmh"], "Transit dynamics"), use_container_width=True, key="plotly_1258")
        with c3:
            st.plotly_chart(make_line(live_df, ["risk_score", "gateway_delay_index", "curb_occupancy_rate"], "Pressure dynamics"), use_container_width=True, key="plotly_1260")

with tab_map:
    st.markdown("## Map & layers")
    if df.empty:
        st.info("No simulation data yet.")
    else:
        top = st.columns([1.7, 1.0])
        with top[0]:
            render_city_map(hotspots_df, latest, height=700, focused_name=focus_name)
        with top[1]:
            render_hotspot_summary(focus_name, hotspots_df, latest.get("scenario_note"), title="Selected hotspot")
            if not hotspots_df.empty:
                layer_counts = hotspots_df[hotspots_df["layer_group"].isin(ss.get("map_layers", []))]["layer_group"].value_counts().reset_index()
                layer_counts.columns = ["Layer", "Count"]
                st.plotly_chart(make_group_bar(layer_counts, "Layer", "Count", None, "Layer catalogue", height=240), use_container_width=True, key="plotly_1275")
                st.plotly_chart(make_subsystem_score_chart(latest), use_container_width=True, key="plotly_1276")
        catalogue = hotspots_df[["name", "layer_group", "category", "streets", "lat", "lon"]].copy() if not hotspots_df.empty else hotspots_df
        st.dataframe(catalogue, use_container_width=True, height=300)


with tab_signals:
    st.markdown("## Signals & Alerts Map")
    if df.empty:
        st.info("No simulation data yet.")
    else:
        signals_df = build_hotspot_signals(hotspots_df, df, latest, focus_name)
        if signals_df.empty:
            st.info("No signal layer available.")
        else:
            left, right = st.columns([1.8, 1.0])
            with left:
                render_signals_map(signals_df, height=760)
            with right:
                top_alerts = signals_df.sort_values(["severity", "name"], ascending=[False, True]).head(6).copy()
                top_alerts["severity"] = top_alerts["severity"].round(3)
                render_summary_table([
                    ("Scenario", SCENARIO_LABELS.get(str(latest.get("scenario", "")), str(latest.get("scenario", "—")))),
                    ("Active event", latest.get("active_event", "none") or "none"),
                    ("Focused hotspot", focus_name or "—"),
                    ("Primary route", ROUTE_LABELS.get(str(latest.get("decision_route", "")), "—")),
                ], "Operational context")
                st.plotly_chart(make_alert_level_chart(signals_df), use_container_width=True, key="plotly_1302")
                st.dataframe(
                    top_alerts[["name", "alert_level", "phase", "signal_type", "active_event", "severity"]],
                    use_container_width=True,
                    hide_index=True,
                    height=260,
                )

            info_cols = st.columns(3)
            with info_cols[0]:
                st.plotly_chart(make_line(df.tail(int(ss["live_window"])), ["risk_score", "near_miss_index"], "Risk signal trend"), use_container_width=True, key="plotly_1312")
            with info_cols[1]:
                st.plotly_chart(make_line(df.tail(int(ss["live_window"])), ["bus_bunching_index", "corridor_reliability_index"], "Transit signal trend"), use_container_width=True, key="plotly_1314")
            with info_cols[2]:
                st.plotly_chart(make_line(df.tail(int(ss["live_window"])), ["curb_occupancy_rate", "illegal_curb_occupancy_rate", "gateway_delay_index"], "Curb / gateway trend"), use_container_width=True, key="plotly_1316")

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
        live_df = df.tail(int(ss["live_window"])).copy()

        metric_map = {
            "intersection": [["corridor_delay_s", "risk_score"], ["near_miss_index", "pedestrian_exposure"]],
            "road_corridor": [["network_speed_index", "corridor_reliability_index"], ["corridor_delay_s", "gateway_delay_index"]],
            "bus_corridor": [["bus_bunching_index", "bus_commercial_speed_kmh"], ["bus_priority_requests", "corridor_reliability_index"]],
            "curb_zone": [["curb_occupancy_rate", "illegal_curb_occupancy_rate"], ["delivery_queue", "risk_score"]],
            "risk_hotspot": [["risk_score", "near_miss_index"], ["pedestrian_exposure", "bike_conflict_index"]],
        }

        grid = st.columns([1.45, 1.45, 1.0])
        with grid[0]:
            st.plotly_chart(make_line(live_df, metric_map[twin_sel][0], "Twin trend A"), use_container_width=True, key="plotly_1341")
        with grid[1]:
            st.plotly_chart(make_line(live_df, metric_map[twin_sel][1], "Twin trend B"), use_container_width=True, key="plotly_1343")
        with grid[2]:
            render_hotspot_summary(md.get("hotspot_name") or focus_name, hotspots_df, md.get("scenario_note") or latest.get("scenario_note"), title="Twin hotspot")
            render_chip_row([
                (f"Status · {snap.get('operational_status', '—')}", 'neutral'),
                (f"Pressure · {snap.get('pressure_level', '—')}", 'warn'),
                (f"Trend · {snap.get('trend_state', '—')}", 'dim'),
                (f"Action · {snap.get('action_active', '—')}", 'alert' if snap.get('action_active') not in [None,'none','None','—'] else 'dim'),
            ])
            twin_rows = [(k, v) for k, v in twin_snapshot_fields(snap)]
            render_summary_table(twin_rows[:8], "Key metrics")

        if twin_sel == "bus_corridor":
            st.plotly_chart(make_line(live_df, ["bus_bunching_index", "bus_commercial_speed_kmh", "bus_priority_requests"], "Bus corridor focus"), use_container_width=True, key="plotly_1356")
        elif twin_sel == "curb_zone":
            st.plotly_chart(make_line(live_df, ["curb_occupancy_rate", "illegal_curb_occupancy_rate", "delivery_queue"], "Curb zone focus"), use_container_width=True, key="plotly_1358")
        elif twin_sel == "risk_hotspot":
            st.plotly_chart(make_line(live_df, ["risk_score", "near_miss_index", "pedestrian_exposure", "bike_conflict_index"], "Risk hotspot focus"), use_container_width=True, key="plotly_1360")

with tab_risk:
    if df.empty:
        st.info("No simulation data yet.")
    else:
        live_df = df.tail(int(ss["live_window"])).copy()
        risk_row = st.columns(4)
        with risk_row[0]:
            kpi_block("Risk", f"{latest.get('risk_score', 0.0):.2f}", tone=tone_from_value(float(latest.get('risk_score',0.0) or 0.0), False))
        with risk_row[1]:
            kpi_block("Near-miss", f"{latest.get('near_miss_index', 0.0):.2f}", tone=tone_from_value(float(latest.get('near_miss_index',0.0) or 0.0), False))
        with risk_row[2]:
            kpi_block("Pedestrian exposure", f"{latest.get('pedestrian_exposure', 0.0):.2f}", tone=tone_from_value(float(latest.get('pedestrian_exposure',0.0) or 0.0), False))
        with risk_row[3]:
            kpi_block("Gateway pressure", f"{latest.get('gateway_delay_index', 0.0):.2f}", tone=tone_from_value(float(latest.get('gateway_delay_index',0.0) or 0.0), False))
        c1, c2, c3 = st.columns([1.0, 1.0, 1.0])
        with c1:
            st.plotly_chart(make_line(live_df, ["risk_score", "near_miss_index"], "Risk evolution"), use_container_width=True, key="plotly_1378")
        with c2:
            st.plotly_chart(make_line(live_df, ["pedestrian_exposure", "bike_conflict_index"], "Exposure and conflict"), use_container_width=True, key="plotly_1380")
        with c3:
            st.plotly_chart(make_line(live_df, ["corridor_delay_s", "bus_bunching_index", "gateway_delay_index"], "Risk context"), use_container_width=True, key="plotly_1382")
        render_chip_row([
            (f"Dominant risk · {latest.get('dominant_risk_type', '—')}", 'alert'),
            (f"Phase · {latest.get('risk_phase', '—')}", 'warn'),
            (f"Forecast · {latest.get('risk_forecast_trend', '—')}", 'neutral'),
        ])
        render_hotspot_summary(focus_name, hotspots_df, latest.get("scenario_note"), title="Risk hotspot")


with tab_sim:
    st.markdown("## What-if & Simulation")
    if df.empty:
        st.info("Run at least one step before launching a contextual what-if analysis.")
    else:
        left, right = st.columns([0.95, 1.25])
        with left:
            render_hotspot_summary(focus_name, hotspots_df, latest.get("scenario_note"), title="Simulation focus")
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
                kpi_block("Projected route", ROUTE_LABELS.get(projected.get("what_if_route", "CLASSICAL"), "Classical"), tone=route_tone(projected.get("what_if_route", "CLASSICAL")))
            with top[1]:
                delta_score = projected.get("step_operational_score", 0.0) - latest.get("step_operational_score", 0.0)
                kpi_block("Δ operational score", f"{delta_score:+.3f}")
            with top[2]:
                kpi_block("Subproblem", projected.get("what_if_subproblem", "—"))

            g1, g2 = st.columns(2)
            with g1:
                st.plotly_chart(make_scatter_compare(latest, projected, ["step_operational_score", "network_speed_index", "risk_score", "bus_bunching_index"], "Scenario comparison"), use_container_width=True, key="plotly_1452")
            with g2:
                st.plotly_chart(make_delta_bar(delta_df), use_container_width=True, key="plotly_1454")

            rec_cols = st.columns(2)
            with rec_cols[0]:
                render_summary_table([
                    ("Action", projected.get("recommended_action", "—")),
                    ("Priority", projected.get("recommended_priority", "—")),
                    ("Responsible layer", projected.get("recommended_owner", "—")),
                ], "Action package")
            with rec_cols[1]:
                render_summary_table([
                    ("Projected route", ROUTE_LABELS.get(projected.get("what_if_route", "CLASSICAL"), "Classical")),
                    ("Subproblem", projected.get("what_if_subproblem", "—")),
                    ("Expected impact", projected.get("recommended_expected_impact", "—")),
                ], "Operational expectation")

            st.dataframe(delta_df, use_container_width=True, hide_index=True, height=380)

with tab_audit:
    if df.empty:
        st.info("No records yet.")
    else:
        cols_to_show = [
            "step_id", "ts", "mode", "scenario", "active_event", "primary_hotspot_name",
            "decision_route", "exec_ms", "decision_confidence", "step_operational_score", "fallback_triggered"
        ]
        cols_to_show = [c for c in cols_to_show if c in df.columns]
        st.dataframe(df[cols_to_show].tail(60), use_container_width=True, height=260)
        idx = st.number_input("Record index (0-based)", min_value=0, max_value=max(0, len(df)-1), value=max(0, len(df)-1), step=1)
        row = df.iloc[int(idx)]
        window_df = make_window_df(df, int(idx), radius=8)

        top = st.columns(4)
        with top[0]:
            kpi_block("Route", ROUTE_LABELS.get(str(row.get("decision_route")), str(row.get("decision_route"))), tone=route_tone(str(row.get("decision_route"))))
        with top[1]:
            kpi_block("Latency", f"{int(row.get('exec_ms', 0))} ms", tone=tone_from_value(min(float(row.get('exec_ms',0) or 0)/1200.0,1.0), False))
        with top[2]:
            kpi_block("Confidence", f"{float(row.get('decision_confidence', 0.0))*100:.1f}%", tone=tone_from_value(float(row.get('decision_confidence',0.0) or 0.0), True))
        with top[3]:
            kpi_block("Score", f"{float(row.get('step_operational_score', 0.0)):.3f}", tone=tone_from_value(float(row.get('step_operational_score',0.0) or 0.0), True))

        render_chip_row([
            (f"Situation · {row.get('situation_type', '—')}", 'neutral'),
            (f"Subproblem · {row.get('subproblem_type', '—')}", 'warn'),
            (f"Action priority · {row.get('action_priority', '—')}", 'alert' if str(row.get('action_priority','')).lower()=='high' else 'warn'),
        ])

        g1, g2, g3 = st.columns(3)
        with g1:
            st.plotly_chart(make_line(window_df, ["network_speed_index", "corridor_reliability_index"], "Local urban performance"), use_container_width=True, key="plotly_1504")
        with g2:
            st.plotly_chart(make_line(window_df, ["risk_score", "near_miss_index", "pedestrian_exposure"], "Local risk window"), use_container_width=True, key="plotly_1506")
        with g3:
            st.plotly_chart(make_line(window_df, ["bus_bunching_index", "curb_occupancy_rate", "gateway_delay_index"], "Operational pressure window"), use_container_width=True, key="plotly_1508")

        details = st.columns([1.05, 1.05, 0.9])
        with details[0]:
            render_summary_table([
                ("Step", int(row["step_id"])),
                ("Mode", MODE_LABELS.get(str(row["mode"]), str(row["mode"]))),
                ("Scenario", SCENARIO_LABELS.get(str(row["scenario"]), str(row["scenario"]))),
                ("Event", row.get("active_event", "none") or "none"),
                ("Hotspot", row.get("primary_hotspot_name", "—")),
            ], "Record")
        with details[1]:
            render_summary_table([
                ("Network speed", float(row.get("network_speed_index", 0.0))),
                ("Bus bunching", float(row.get("bus_bunching_index", 0.0))),
                ("Curb occupancy", float(row.get("curb_occupancy_rate", 0.0))),
                ("Risk", float(row.get("risk_score", 0.0))),
                ("Gateway delay", float(row.get("gateway_delay_index", 0.0))),
            ], "State vector")
        with details[2]:
            recommendation = recommend_action_from_record(row.to_dict())
            render_summary_table([
                ("Action", recommendation["action"]),
                ("Priority", recommendation["priority"]),
                ("Owner", recommendation["owner"]),
                ("Subproblem", recommendation["subproblem"]),
            ], "Recommended action")

        render_hotspot_summary(row.get("primary_hotspot_name"), hotspots_df, row.get("scenario_note"), title="Audit hotspot")

        with st.expander("Technical detail"):
            tech_cols = st.columns(2)
            with tech_cols[0]:
                st.markdown("### Dispatch")
                st.json(safe_json_loads(row.get("dispatch_json")))
                st.markdown("### Objective breakdown")
                st.json(safe_json_loads(row.get("objective_breakdown_json")))
            with tech_cols[1]:
                st.markdown("### Quantum Request Envelope")
                st.json(safe_json_loads(row.get("qre_json")) or {"info": "No QRE generated on this step."})
                st.markdown("### Quantum Result")
                st.json(safe_json_loads(row.get("result_json")) or {"info": "No quantum result on this step."})
