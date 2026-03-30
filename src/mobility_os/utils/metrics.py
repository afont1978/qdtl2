from __future__ import annotations

from typing import Any

import pandas as pd


def compute_route_mix(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or 'decision_route' not in df.columns:
        return pd.DataFrame(columns=['route', 'count'])
    vc = df['decision_route'].value_counts().reset_index()
    vc.columns = ['route', 'count']
    return vc


def compute_alert_burden(df: pd.DataFrame) -> float:
    if df.empty or 'risk_score' not in df.columns:
        return 0.0
    latest = df.tail(12)
    return float(latest['risk_score'].mean())


def compute_city_operational_score(df: pd.DataFrame) -> float:
    if df.empty or 'step_operational_score' not in df.columns:
        return 0.0
    return float(df['step_operational_score'].tail(12).mean())


def format_pct(x: Any) -> str:
    try:
        return f"{float(x) * 100:.1f}%"
    except Exception:
        return '—'


def format_num(x: Any, suffix: str = '') -> str:
    try:
        return f"{float(x):.2f}{suffix}"
    except Exception:
        return '—'
