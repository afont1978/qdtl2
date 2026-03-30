from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ValidationResult:
    valid: bool
    validation_status: str
    notes: str
    dispatch: Dict[str, Any]


class Validator:
    """
    Basic urban validator: clamps unsafe or contradictory actions.
    """

    def validate(self, state: Dict[str, Any], dispatch: Dict[str, Any]) -> ValidationResult:
        dispatch = dict(dispatch)

        dispatch["bus_priority_level"] = int(max(0, min(dispatch.get("bus_priority_level", 1), 3)))
        dispatch["signal_plan_id"] = int(max(0, min(dispatch.get("signal_plan_id", 1), 3)))
        dispatch["curb_slot_policy"] = int(max(0, min(dispatch.get("curb_slot_policy", 1), 2)))
        dispatch["enforcement_level"] = int(max(0, min(dispatch.get("enforcement_level", 1), 2)))
        dispatch["ped_protection_mode"] = int(max(0, min(dispatch.get("ped_protection_mode", 0), 1)))
        dispatch["speed_mitigation_mode"] = int(max(0, min(dispatch.get("speed_mitigation_mode", 0), 1)))

        if state.get("mode") == "safety":
            dispatch["ped_protection_mode"] = max(1, dispatch.get("ped_protection_mode", 0))
            dispatch["speed_mitigation_mode"] = max(1, dispatch.get("speed_mitigation_mode", 0))

        return ValidationResult(
            valid=True,
            validation_status="approved",
            notes="Dispatch validated against basic urban control constraints.",
            dispatch=dispatch,
        )
