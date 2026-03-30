from __future__ import annotations

from typing import Optional


def determine_risk_phase(current: float, previous: Optional[float], incident: bool = False) -> str:
    if incident and current >= 0.70:
        return "critical"
    if previous is None:
        if current >= 0.55:
            return "active"
        if current >= 0.30:
            return "emerging"
        return "latent"
    delta = current - previous
    if current >= 0.80:
        return "critical"
    if current >= 0.55:
        return "active" if delta >= -0.03 else "stabilizing"
    if current >= 0.30:
        return "emerging" if delta >= 0.0 else "stabilizing"
    if previous >= 0.30 and current < 0.30:
        return "cleared"
    return "latent"
