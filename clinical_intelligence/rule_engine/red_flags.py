"""
Red Flag Detector.

Evaluates each entry in red_flags.yaml against the patient's clinical state
and returns a list of RedFlagAlert objects ordered by severity.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer
from clinical_intelligence.rule_engine.models import ClinicalAlert, RedFlagAlert
from clinical_intelligence.rule_engine.scorer import _evaluate_vital_condition, _parse_vitals

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2}


class RedFlagDetector:
    """
    Evaluates red_flags.yaml rules against a patient clinical state.

    A red flag fires when ALL required_symptoms are present AND at least
    one condition in any_of_symptoms, vital_sign_criteria, history_criteria,
    or risk_factor_criteria is satisfied.
    """

    def __init__(self, red_flag_rules: List[Dict[str, Any]]) -> None:
        self._rules = red_flag_rules

    def detect(
        self,
        *,
        present_symptoms: Set[str],
        negated_symptoms: Set[str],
        vital_signs_raw: Dict[str, Optional[str]],
        medical_history: List[str],
        risk_factor_ids: List[str],
        age: Optional[int],
        tracer: ExplainabilityTracer,
    ) -> List[RedFlagAlert]:
        """
        Evaluate all red flag rules and return fired alerts.

        Parameters
        ----------
        present_symptoms:
            Lower-cased, canonical symptom names that are Active.
        negated_symptoms:
            Lower-cased symptom names that are negated/resolved.
        vital_signs_raw:
            Raw vital-sign strings from ClinicalState.
        medical_history:
            Lower-cased history strings.
        risk_factor_ids:
            IDs of confirmed active risk factors.
        age:
            Patient age in years.
        tracer:
            Explainability tracer.
        """
        parsed_vitals = _parse_vitals(vital_signs_raw)
        alerts: List[RedFlagAlert] = []
        history_lower = {h.lower() for h in medical_history}

        for rule in self._rules:
            flag_id: str = rule.get("id", "unknown")
            condition: str = rule.get("condition", flag_id)
            severity: str = rule.get("severity", "HIGH")
            tracer.increment_evaluated()

            triggered_by: List[str] = []

            # ── 1. Required symptoms (ALL must be present) ──
            required: List[str] = [s.lower() for s in rule.get("required_symptoms", [])]
            if required:
                if not all(r in present_symptoms for r in required):
                    continue
                triggered_by.extend(required)

            # ── 2. any_of_symptoms (AT LEAST ONE required if list non-empty) ──
            any_of: List[str] = [s.lower() for s in rule.get("any_of_symptoms", [])]
            any_of_matched: List[str] = [s for s in any_of if s in present_symptoms]
            has_symptom_trigger = bool(any_of_matched)
            triggered_by.extend(any_of_matched)

            # ── 3. Vital sign criteria ──
            has_vital_trigger = False
            vital_evidence: List[str] = []
            for criterion in rule.get("vital_sign_criteria", []):
                cond = criterion.get("condition", "")
                threshold = float(criterion.get("threshold", 0))
                if _evaluate_vital_condition(cond, threshold, parsed_vitals):
                    has_vital_trigger = True
                    vital_evidence.append(f"{cond} (threshold: {threshold})")
            triggered_by.extend(vital_evidence)

            # ── 4. Age criteria ──
            has_age_trigger = False
            age_criteria = rule.get("age_criteria", {})
            if age_criteria and age is not None:
                min_age = age_criteria.get("min_age", 0)
                max_age = age_criteria.get("max_age", 200)
                if min_age <= age <= max_age:
                    has_age_trigger = True
                    triggered_by.append(f"age {age} (risk range ≥{min_age})")

            # ── 5. History criteria ──
            hist_terms: List[str] = [h.lower() for h in rule.get("history_criteria", [])]
            hist_matched = [h for h in hist_terms if any(h in hx for hx in history_lower)]
            triggered_by.extend(hist_matched)

            # ── 6. Risk factor criteria ──
            rf_terms: List[str] = rule.get("risk_factor_criteria", [])
            rf_matched = [r for r in rf_terms if r in risk_factor_ids]
            triggered_by.extend(rf_matched)

            # ── Decision: fire if any trigger present ──
            any_trigger = (
                has_symptom_trigger
                or has_vital_trigger
                or has_age_trigger
                or bool(hist_matched)
                or bool(rf_matched)
            )
            if not any_trigger:
                continue

            # Build supporting evidence
            supporting_evidence = list(dict.fromkeys(triggered_by))  # deduplicate, preserve order
            recommended_action: str = rule.get("recommended_action", "").strip()

            alert = RedFlagAlert(
                flag_id=flag_id,
                condition=condition,
                severity=severity,  # type: ignore[arg-type]
                supporting_evidence=supporting_evidence,
                recommended_action=recommended_action,
                triggered_by=list(triggered_by),
            )
            alerts.append(alert)
            tracer.increment_matched()

            tracer.add_step(
                component="RedFlagDetector",
                description=f"RED FLAG fired: {condition} [{severity}]",
                input_facts=supporting_evidence[:5],
                output=f"RedFlagAlert(condition={condition}, severity={severity})",
                confidence_delta=0.0,
            )

        # Sort by severity (CRITICAL first)
        alerts.sort(key=lambda a: _SEVERITY_ORDER.get(a.severity, 99))
        return alerts

    def to_clinical_alerts(self, red_flags: List[RedFlagAlert]) -> List[ClinicalAlert]:
        """Convert RedFlagAlert list to ClinicalAlert list for the aggregate alerts field."""
        from clinical_intelligence.rule_engine.models import ClinicalAlert
        result: List[ClinicalAlert] = []
        for rf in red_flags:
            result.append(
                ClinicalAlert(
                    alert_id=f"alert_{rf.flag_id}",
                    alert_type="red_flag",
                    severity=rf.severity,  # type: ignore[arg-type]
                    title=f"⚠️ RED FLAG: {rf.condition}",
                    message=rf.recommended_action,
                    supporting_evidence=rf.supporting_evidence,
                    recommended_action=rf.recommended_action,
                )
            )
        return result
