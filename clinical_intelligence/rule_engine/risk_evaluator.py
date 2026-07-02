"""
Risk Factor Evaluator.

Scans the patient's clinical state (medical history, current medications,
allergies, social history) against the risk_factors.yaml rules to identify
active risk factors and their confidence modifier values.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer
from clinical_intelligence.rule_engine.models import IdentifiedRiskFactor

logger = logging.getLogger(__name__)


class RiskFactorEvaluator:
    """
    Identifies clinically active risk factors by matching detection_terms
    against designated ClinicalState fields.
    """

    def __init__(self, risk_factor_rules: List[Dict[str, Any]]) -> None:
        self._rules = risk_factor_rules

    def evaluate(
        self,
        *,
        medical_history: List[str],
        current_medications: List[str],
        allergies: List[str],
        family_history: Optional[List[Any]] = None,
        social_history: Optional[str] = None,
        vital_signs: Optional[Dict[str, Optional[str]]] = None,
        age: Optional[int] = None,
        gender: Optional[str] = None,
        tracer: ExplainabilityTracer,
    ) -> Tuple[List[IdentifiedRiskFactor], List[str]]:
        """
        Evaluate all risk factor rules against the patient state.

        Returns
        -------
        Tuple of:
            - List[IdentifiedRiskFactor]: full detail records
            - List[str]: just the IDs of present risk factors (for scorer input)
        """
        # Normalise all source text to lower-case
        history_text = " | ".join(medical_history).lower()
        meds_text = " | ".join(current_medications).lower()
        allergies_text = " | ".join(allergies).lower()
        fh_text = self._flatten_family_history(family_history or []).lower()
        social_text = (social_history or "").lower()

        source_lookup: Dict[str, str] = {
            "medical_history": history_text,
            "current_medications": meds_text,
            "allergies": allergies_text,
            "family_history": fh_text,
            "social_history": social_text,
        }

        identified: List[IdentifiedRiskFactor] = []
        identified_ids: List[str] = []

        for rule in self._rules:
            rf_id: str = rule.get("id", "unknown")
            rf_name: str = rule.get("name", rf_id)
            rf_category: str = rule.get("category", "other")
            rf_modifier: float = float(rule.get("confidence_modifier", 0.0))
            source_fields: List[str] = rule.get("source_fields", [])
            detection_terms: List[str] = [t.lower() for t in rule.get("detection_terms", [])]

            tracer.increment_evaluated()

            matched_source: Optional[str] = None

            for field_name in source_fields:
                text = source_lookup.get(field_name, "")
                for term in detection_terms:
                    if term in text:
                        matched_source = field_name
                        break
                if matched_source:
                    break

            if matched_source:
                identified.append(
                    IdentifiedRiskFactor(
                        factor_id=rf_id,
                        name=rf_name,
                        category=rf_category,
                        present=True,
                        source=matched_source,
                        confidence_modifier=rf_modifier,
                    )
                )
                identified_ids.append(rf_id)
                tracer.increment_matched()
                tracer.add_step(
                    component="RiskFactorEvaluator",
                    description=f"Risk factor '{rf_name}' identified",
                    input_facts=[f"matched in {matched_source}"],
                    output=f"risk_factor present: {rf_id} (modifier={rf_modifier})",
                    confidence_delta=rf_modifier,
                )

        return identified, identified_ids

    @staticmethod
    def _flatten_family_history(fh: List[Any]) -> str:
        """Convert family_history records (dicts or strings) to a flat text blob."""
        parts: List[str] = []
        for item in fh:
            if isinstance(item, dict):
                parts.append(item.get("condition", "") + " " + item.get("relationship", ""))
            elif isinstance(item, str):
                parts.append(item)
        return " | ".join(parts)
