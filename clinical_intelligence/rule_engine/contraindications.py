"""
Contraindication Checker.

Checks contraindications.yaml rules against the patient's allergies,
medical history, and current medications.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer
from clinical_intelligence.rule_engine.models import (
    ClinicalAlert,
    Contraindication,
    InvestigationRecommendation,
)

logger = logging.getLogger(__name__)


class ContraindicationChecker:
    """
    Detects contraindications by matching trigger_terms against patient data.
    """

    def __init__(self, contraindication_rules: List[Dict[str, Any]]) -> None:
        self._rules = contraindication_rules

    def check(
        self,
        *,
        allergies: List[str],
        medical_history: List[str],
        current_medications: List[str],
        recommended_investigations: List[InvestigationRecommendation],
        tracer: ExplainabilityTracer,
    ) -> List[Contraindication]:
        """
        Evaluate contraindication rules and return any that are triggered.

        The checker considers:
        - Patient allergies vs. allergy-based rules
        - Medical history vs. history-based rules
        - Current medications vs. medication-based rules
        """
        # Build searchable text blobs
        allergy_text = " | ".join(allergies).lower()
        history_text = " | ".join(medical_history).lower()
        meds_text = " | ".join(current_medications).lower()

        # Also build investigation names text (to detect CI for recommended items)
        inv_names_text = " | ".join(
            i.name.lower() for i in recommended_investigations
        )

        source_map = {
            "allergy": allergy_text,
            "history": history_text,
            "medication": meds_text,
            "comorbidity": history_text,  # comorbidity checks use history
        }

        found: List[Contraindication] = []
        seen_ids: set = set()

        for rule in self._rules:
            ci_id: str = rule.get("id", "unknown")
            drug_or_proc: str = rule.get("drug_or_procedure", "")
            trigger_type: str = rule.get("trigger_type", "allergy")
            trigger_terms: List[str] = [t.lower() for t in rule.get("trigger_terms", [])]
            severity: str = rule.get("severity", "RELATIVE")
            reason: str = rule.get("reason", "").strip()
            recommendation: str = rule.get("recommendation", "").strip()

            tracer.increment_evaluated()

            text_to_search = source_map.get(trigger_type, "")

            matched_trigger: str = ""
            for term in trigger_terms:
                if term in text_to_search:
                    matched_trigger = term
                    break

            if not matched_trigger:
                continue

            # Deduplicate (same CI can fire from multiple trigger terms)
            if ci_id in seen_ids:
                continue
            seen_ids.add(ci_id)

            found.append(
                Contraindication(
                    contraindication_id=ci_id,
                    drug_or_procedure=drug_or_proc,
                    reason=reason,
                    trigger=matched_trigger,
                    severity=severity,  # type: ignore[arg-type]
                    recommendation=recommendation,
                )
            )
            tracer.increment_matched()
            tracer.add_step(
                component="ContraindicationChecker",
                description=f"Contraindication detected: {drug_or_proc}",
                input_facts=[
                    f"trigger_type: {trigger_type}",
                    f"trigger_term: {matched_trigger}",
                    f"severity: {severity}",
                ],
                output=f"Contraindication(id={ci_id}, severity={severity})",
            )

        # Sort: ABSOLUTE first
        found.sort(key=lambda c: (0 if c.severity == "ABSOLUTE" else 1))
        return found

    def to_clinical_alerts(
        self, contraindications: List[Contraindication]
    ) -> List[ClinicalAlert]:
        """Convert Contraindication list to ClinicalAlert list."""
        alerts: List[ClinicalAlert] = []
        for ci in contraindications:
            sev_map = {"ABSOLUTE": "CRITICAL", "RELATIVE": "HIGH"}
            alerts.append(
                ClinicalAlert(
                    alert_id=f"alert_{ci.contraindication_id}",
                    alert_type="contraindication",
                    severity=sev_map.get(ci.severity, "MODERATE"),  # type: ignore[arg-type]
                    title=f"Contraindication: {ci.drug_or_procedure}",
                    message=ci.reason,
                    supporting_evidence=[f"Trigger: {ci.trigger}"],
                    recommended_action=ci.recommendation,
                )
            )
        return alerts
