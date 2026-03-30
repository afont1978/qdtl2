from __future__ import annotations

from typing import Any, Dict, List

from .problem_decomposer import Subproblem
from .situation_interpreter import SituationSummary


class PriorityArbiter:
    """
    Chooses effective objective weights and priority order depending on the
    current mode and situation.
    """

    BASE_WEIGHTS = {
        "traffic": {
            "delay": 1.0,
            "transit": 0.9,
            "risk": 1.0,
            "logistics": 0.7,
            "gateway": 0.7,
        },
        "safety": {
            "delay": 0.5,
            "transit": 0.7,
            "risk": 1.4,
            "logistics": 0.5,
            "gateway": 0.5,
        },
        "logistics": {
            "delay": 0.7,
            "transit": 0.7,
            "risk": 1.0,
            "logistics": 1.3,
            "gateway": 0.6,
        },
        "gateway": {
            "delay": 0.8,
            "transit": 0.8,
            "risk": 1.0,
            "logistics": 0.8,
            "gateway": 1.3,
        },
        "event": {
            "delay": 0.9,
            "transit": 1.0,
            "risk": 1.1,
            "logistics": 0.8,
            "gateway": 1.0,
        },
    }

    def arbitrate(
        self,
        state: Dict[str, Any],
        situation: SituationSummary,
        subproblems: List[Subproblem],
    ) -> Dict[str, Any]:
        mode = state.get("mode", "traffic")
        weights = dict(self.BASE_WEIGHTS.get(mode, self.BASE_WEIGHTS["traffic"]))

        if situation.dominant_objective == "protect_vulnerable_users":
            weights["risk"] *= 1.25
            weights["delay"] *= 0.7
        elif situation.dominant_objective == "restore_curbside_and_delivery_flow":
            weights["logistics"] *= 1.2
        elif situation.dominant_objective == "contain_access_delay_and_rebalance_arrivals":
            weights["gateway"] *= 1.2
            weights["transit"] *= 1.1

        dominant_subproblem = subproblems[0].subproblem_type if subproblems else "local_tactical_adjustment"

        priority_order = [
            dominant_subproblem,
            *[sp.subproblem_type for sp in subproblems[1:]],
        ]

        return {
            "objective_weights": weights,
            "dominant_subproblem": dominant_subproblem,
            "priority_order": priority_order,
        }
