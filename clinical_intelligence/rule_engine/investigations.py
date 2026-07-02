"""
Investigation Recommender.

Recommends investigations based on candidate diagnoses and active red flags.
Deduplicates across diseases, escalates priority when red flags are present.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer
from clinical_intelligence.rule_engine.models import (
    CandidateDiagnosis,
    InvestigationRecommendation,
    RedFlagAlert,
)

logger = logging.getLogger(__name__)

_PRIORITY_RANK = {"URGENT": 0, "HIGH": 1, "ROUTINE": 2}


class InvestigationRecommender:
    """
    Maps candidate diagnoses to recommended investigations via investigations.yaml.
    """

    def __init__(self, investigation_rules: List[Dict[str, Any]]) -> None:
        # Build lookup: disease_id → [investigation_entry]
        self._rules = investigation_rules
        self._disease_map: Dict[str, List[Dict[str, Any]]] = {}
        self._id_map: Dict[str, Dict[str, Any]] = {}

        for inv in investigation_rules:
            inv_id = inv.get("id", "")
            self._id_map[inv_id] = inv
            for disease_id in inv.get("for_diseases", []):
                self._disease_map.setdefault(disease_id, []).append(inv)

    def recommend(
        self,
        *,
        candidates: List[CandidateDiagnosis],
        red_flags: List[RedFlagAlert],
        confidence_threshold: float = 0.30,
        tracer: ExplainabilityTracer,
    ) -> List[InvestigationRecommendation]:
        """
        Produce a deduplicated, priority-ordered investigation list.

        Parameters
        ----------
        candidates:
            Scored diagnoses from DiseaseScorer (all confidence ≥ threshold).
        red_flags:
            Fired red flags (used to escalate investigation priority).
        confidence_threshold:
            Minimum diagnosis confidence to trigger investigations.
        tracer:
            Explainability tracer.
        """
        # Collect active red-flag trigger IDs
        active_red_flag_ids: Set[str] = {rf.flag_id for rf in red_flags}

        # Map: investigation_id → best priority seen and for_conditions list
        recommended: Dict[str, Dict[str, Any]] = {}

        for candidate in candidates:
            if candidate.confidence < confidence_threshold:
                continue

            investigations_for_disease = self._disease_map.get(candidate.disease_id, [])
            for inv in investigations_for_disease:
                inv_id: str = inv.get("id", "")
                inv_name: str = inv.get("name", inv_id)
                base_priority: str = inv.get("priority", "ROUTINE")
                triggers: List[str] = inv.get("triggers", [])
                rationale: str = inv.get("rationale", "").strip()

                # Escalate to URGENT if a matching red flag is active
                escalated = any(t in active_red_flag_ids for t in triggers)
                final_priority = "URGENT" if escalated else base_priority

                if inv_id in recommended:
                    existing = recommended[inv_id]
                    # Keep highest priority
                    if _PRIORITY_RANK[final_priority] < _PRIORITY_RANK[existing["priority"]]:
                        existing["priority"] = final_priority
                        existing["escalated_by_red_flag"] = escalated
                    existing["for_conditions"].append(candidate.name)
                else:
                    recommended[inv_id] = {
                        "id": inv_id,
                        "name": inv_name,
                        "priority": final_priority,
                        "reason": rationale,
                        "for_conditions": [candidate.name],
                        "escalated_by_red_flag": escalated,
                    }

                tracer.increment_evaluated()
                tracer.increment_matched()

        # Sort: URGENT → HIGH → ROUTINE, then alphabetically
        result: List[InvestigationRecommendation] = []
        for inv_id, data in recommended.items():
            result.append(
                InvestigationRecommendation(
                    investigation_id=inv_id,
                    name=data["name"],
                    priority=data["priority"],  # type: ignore[arg-type]
                    reason=data["reason"],
                    for_conditions=list(dict.fromkeys(data["for_conditions"])),
                    escalated_by_red_flag=data["escalated_by_red_flag"],
                )
            )
            tracer.add_step(
                component="InvestigationRecommender",
                description=f"Recommending '{data['name']}' ({data['priority']})",
                input_facts=[f"for: {', '.join(data['for_conditions'][:3])}"],
                output=f"priority={data['priority']}, escalated={data['escalated_by_red_flag']}",
            )

        result.sort(
            key=lambda i: (
                _PRIORITY_RANK.get(i.priority, 99),
                i.name,
            )
        )
        return result
