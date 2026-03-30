from __future__ import annotations

from typing import Dict, Optional

import numpy as np


def forecast_risk_short(current: float, previous: Optional[float], phase: str) -> Dict[str, float | str]:
    prev = current if previous is None else previous
    delta = current - prev
    projected = float(np.clip(current + 0.65 * delta + (0.06 if phase == "emerging" else 0.03 if phase == "critical" else 0.0), 0.0, 1.0))
    escalation_probability = float(np.clip(0.35 + 1.2 * max(projected - current, 0.0) + (0.18 if phase in {"emerging", "active"} else 0.0), 0.0, 1.0))
    trend = "worsening" if projected > current + 0.03 else "improving" if projected < current - 0.03 else "stable"
    return {
        "risk_forecast_score": projected,
        "escalation_probability": escalation_probability,
        "risk_forecast_trend": trend,
    }
