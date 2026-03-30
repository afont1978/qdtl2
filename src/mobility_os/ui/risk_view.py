"""Risk & Prevention helpers for Sprint 4."""

from __future__ import annotations

from typing import Any, Dict, List


def build_risk_summary_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"metric": "Risk burden", "value": state.get("risk_burden", 0.0)},
        {"metric": "Dominant risk", "value": state.get("dominant_risk_type", "")},
        {"metric": "Risk phase", "value": state.get("risk_phase", "latent")},
        {"metric": "Forecast score", "value": state.get("risk_forecast_score", 0.0)},
        {"metric": "Escalation probability", "value": state.get("escalation_probability", 0.0)},
        {"metric": "Preventive action", "value": state.get("preventive_action_recommended", "")},
    ]
