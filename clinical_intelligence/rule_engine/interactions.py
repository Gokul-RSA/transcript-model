"""
Drug Interaction Detector.

Checks drug_interactions.yaml pairwise against:
  - current patient medications × current patient medications
  - current patient medications × recommended investigation/treatment drugs
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set, Tuple

from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer
from clinical_intelligence.rule_engine.models import ClinicalAlert, DrugInteraction

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"MAJOR": 0, "MODERATE": 1, "MINOR": 2}


class DrugInteractionDetector:
    """
    Detects clinically significant drug–drug interactions using
    drug_interactions.yaml.
    """

    def __init__(self, interaction_rules: List[Dict[str, Any]]) -> None:
        self._rules = interaction_rules

    def detect(
        self,
        *,
        current_medications: List[str],
        additional_drugs: List[str] | None = None,
        tracer: ExplainabilityTracer,
    ) -> List[DrugInteraction]:
        """
        Detect pairwise drug interactions.

        Parameters
        ----------
        current_medications:
            Medications the patient is currently taking.
        additional_drugs:
            Additional drugs being considered (e.g. from recommended treatments).
        tracer:
            Explainability tracer.
        """
        all_drugs_lower = [d.lower() for d in current_medications]
        if additional_drugs:
            all_drugs_lower.extend(d.lower() for d in additional_drugs)

        found: List[DrugInteraction] = []
        seen_pairs: Set[Tuple[str, str]] = set()

        for rule in self._rules:
            int_id: str = rule.get("id", "unknown")
            drug_a_name: str = rule.get("drug_a", "")
            drug_a_terms: List[str] = [t.lower() for t in rule.get("drug_a_terms", [])]
            drug_b_name: str = rule.get("drug_b", "")
            drug_b_terms: List[str] = [t.lower() for t in rule.get("drug_b_terms", [])]
            severity: str = rule.get("severity", "MODERATE")
            mechanism: str = rule.get("mechanism", "").strip()
            clinical_effect: str = rule.get("clinical_effect", "").strip()
            recommendation: str = rule.get("recommendation", "").strip()

            tracer.increment_evaluated()

            # Check if drug_a and drug_b are both present in the patient's drug list
            drug_a_present = any(term in drug for drug in all_drugs_lower for term in drug_a_terms)
            drug_b_present = any(term in drug for drug in all_drugs_lower for term in drug_b_terms)

            if not (drug_a_present and drug_b_present):
                continue

            # Deduplicate by sorted pair
            pair = tuple(sorted([int_id]))
            if int_id in {p[0] for p in seen_pairs}:
                continue
            seen_pairs.add((int_id, int_id))

            found.append(
                DrugInteraction(
                    interaction_id=int_id,
                    drug_a=drug_a_name,
                    drug_b=drug_b_name,
                    severity=severity,  # type: ignore[arg-type]
                    mechanism=mechanism,
                    clinical_effect=clinical_effect,
                    recommendation=recommendation,
                )
            )
            tracer.increment_matched()
            tracer.add_step(
                component="DrugInteractionDetector",
                description=f"Interaction detected: {drug_a_name} ↔ {drug_b_name} [{severity}]",
                input_facts=[
                    f"drug_a: {drug_a_name}",
                    f"drug_b: {drug_b_name}",
                ],
                output=f"DrugInteraction(id={int_id}, severity={severity})",
            )

        # Sort: MAJOR first
        found.sort(key=lambda d: _SEVERITY_RANK.get(d.severity, 99))
        return found

    def to_clinical_alerts(
        self, interactions: List[DrugInteraction]
    ) -> List[ClinicalAlert]:
        """Convert DrugInteraction list to ClinicalAlert list."""
        alerts: List[ClinicalAlert] = []
        sev_map = {"MAJOR": "CRITICAL", "MODERATE": "HIGH", "MINOR": "MODERATE"}
        for ix in interactions:
            alerts.append(
                ClinicalAlert(
                    alert_id=f"alert_{ix.interaction_id}",
                    alert_type="interaction",
                    severity=sev_map.get(ix.severity, "MODERATE"),  # type: ignore[arg-type]
                    title=f"Drug Interaction: {ix.drug_a} ↔ {ix.drug_b}",
                    message=ix.clinical_effect,
                    supporting_evidence=[f"Mechanism: {ix.mechanism}"],
                    recommended_action=ix.recommendation,
                )
            )
        return alerts
