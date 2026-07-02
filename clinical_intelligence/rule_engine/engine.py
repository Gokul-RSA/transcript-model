"""
Clinical Reasoning Engine — Orchestrator.

This is the sole public entry point of Module 1 (Rule-Based Clinical
Reasoning Engine). It coordinates all sub-components and returns a fully
explainable ClinicalReasoningResult.

Usage::

    from clinical_intelligence.rule_engine.engine import ClinicalReasoningEngine

    engine = ClinicalReasoningEngine()
    result = engine.reason(clinical_state)   # ClinicalState from Milestone 1
    print(result.model_dump_json(indent=2))
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from clinical_intelligence.rule_engine.contraindications import ContraindicationChecker
from clinical_intelligence.rule_engine.exceptions import InvalidClinicalStateError
from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer
from clinical_intelligence.rule_engine.interactions import DrugInteractionDetector
from clinical_intelligence.rule_engine.investigations import InvestigationRecommender
from clinical_intelligence.rule_engine.loader import RuleLoader, get_loader
from clinical_intelligence.rule_engine.matcher import SymptomMatcher
from clinical_intelligence.rule_engine.missing_info import MissingInfoDetector
from clinical_intelligence.rule_engine.models import (
    ClinicalAlert,
    ClinicalReasoningResult,
)
from clinical_intelligence.rule_engine.red_flags import RedFlagDetector
from clinical_intelligence.rule_engine.risk_evaluator import RiskFactorEvaluator
from clinical_intelligence.rule_engine.scorer import DiseaseScorer

logger = logging.getLogger(__name__)

# ── Alias normalisation helpers (shared with matcher) ────────────────────
from clinical_intelligence.rule_engine.matcher import _build_alias_map, _partial_match, _normalise


class ClinicalReasoningEngine:
    """
    Deterministic, LLM-free Clinical Reasoning Engine.

    Accepts a ClinicalState (or its dict representation) and returns a
    fully explainable ClinicalReasoningResult.

    All reasoning is driven by configurable YAML rules — no LLM is used.
    """

    ENGINE_VERSION = "1.0.0"

    def __init__(self, loader: Optional[RuleLoader] = None) -> None:
        self._loader = loader or get_loader()
        logger.info(
            "ClinicalReasoningEngine: Initialised. Rules loaded: %s",
            self._loader.get().version_summary(),
        )

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def reason(self, clinical_state: Any) -> ClinicalReasoningResult:
        """
        Perform a complete deterministic clinical reasoning pass.

        Parameters
        ----------
        clinical_state:
            Either a ClinicalState Pydantic model (from Milestone 1) or
            a plain dict with the same schema.

        Returns
        -------
        ClinicalReasoningResult
            Fully typed, fully explainable structured clinical intelligence.
        """
        # ── 0. Normalise input ──────────────────────────────────────────
        state_data = self._extract_state_data(clinical_state)
        session_id = state_data.get("session_id", "unknown")

        # ── 1. Hot-reload rules ─────────────────────────────────────────
        rules = self._loader.get()
        tracer = ExplainabilityTracer()
        tracer.start()

        logger.info(
            "ClinicalReasoningEngine: Starting reasoning pass for session=%s",
            session_id,
        )

        # ── 2. Extract relevant state fields ────────────────────────────
        present_symptoms = self._get_present_symptoms(state_data)
        negated_symptoms = self._get_negated_symptoms(state_data)
        all_symptom_names_present: Set[str] = set()

        vital_signs: Dict[str, Optional[str]] = state_data.get("vital_signs", {}) or {}
        age: Optional[int] = state_data.get("patient_info", {}).get("age") if state_data.get("patient_info") else None
        gender: Optional[str] = state_data.get("patient_info", {}).get("gender") if state_data.get("patient_info") else None
        medical_history: List[str] = state_data.get("medical_history", []) or []
        current_medications: List[str] = state_data.get("current_medications", []) or []
        allergies: List[str] = state_data.get("allergies", []) or []
        family_history = state_data.get("family_history", []) or []

        # Build alias map for red-flag canonical matching
        alias_map = _build_alias_map(rules.symptoms)
        canonical_present: Set[str] = set()
        canonical_negated: Set[str] = set()
        for sym in present_symptoms:
            raw = sym.get("name", "")
            canonical_present.add(
                _partial_match(raw, alias_map) or _normalise(raw, alias_map)
            )
        for neg_name in negated_symptoms:
            canonical_negated.add(
                _partial_match(neg_name, alias_map) or _normalise(neg_name, alias_map)
            )

        tracer.add_step(
            component="Engine",
            description="Clinical state parsed and normalised",
            input_facts=[
                f"session_id={session_id}",
                f"present_symptoms={len(present_symptoms)}",
                f"negated_symptoms={len(negated_symptoms)}",
                f"age={age}, gender={gender}",
                f"history_items={len(medical_history)}",
                f"medications={len(current_medications)}",
                f"allergies={len(allergies)}",
            ],
            output="State normalised successfully",
        )

        # ── 3. Risk Factor Evaluation ────────────────────────────────────
        rf_evaluator = RiskFactorEvaluator(rules.risk_factors)
        identified_risk_factors, identified_rf_ids = rf_evaluator.evaluate(
            medical_history=medical_history,
            current_medications=current_medications,
            allergies=allergies,
            family_history=family_history,
            tracer=tracer,
        )

        # ── 4. Symptom Matching ──────────────────────────────────────────
        matcher = SymptomMatcher(rules.diseases, rules.symptoms)
        match_results = matcher.match(
            present_symptoms=present_symptoms,
            negated_symptoms=negated_symptoms,
            tracer=tracer,
        )

        # ── 5. Disease Confidence Scoring ────────────────────────────────
        scorer = DiseaseScorer()
        candidate_diagnoses = scorer.score(
            match_results=match_results,
            vital_signs=vital_signs,
            age=age,
            gender=gender,
            identified_risk_factor_ids=identified_rf_ids,
            tracer=tracer,
        )

        # ── 6. Red Flag Detection ────────────────────────────────────────
        red_flag_detector = RedFlagDetector(rules.red_flags)
        red_flags = red_flag_detector.detect(
            present_symptoms=canonical_present,
            negated_symptoms=canonical_negated,
            vital_signs_raw=vital_signs,
            medical_history=medical_history,
            risk_factor_ids=identified_rf_ids,
            age=age,
            tracer=tracer,
        )

        # ── 7. Investigation Recommendations ─────────────────────────────
        investigator = InvestigationRecommender(rules.investigations)
        recommended_investigations = investigator.recommend(
            candidates=candidate_diagnoses,
            red_flags=red_flags,
            tracer=tracer,
        )

        # ── 8. Contraindication Checking ─────────────────────────────────
        ci_checker = ContraindicationChecker(rules.contraindications)
        contraindications = ci_checker.check(
            allergies=allergies,
            medical_history=medical_history,
            current_medications=current_medications,
            recommended_investigations=recommended_investigations,
            tracer=tracer,
        )

        # ── 9. Drug Interaction Detection ────────────────────────────────
        di_detector = DrugInteractionDetector(rules.drug_interactions)
        drug_interactions = di_detector.detect(
            current_medications=current_medications,
            tracer=tracer,
        )

        # ── 10. Missing Information Detection ────────────────────────────
        missing_detector = MissingInfoDetector()
        missing_information = missing_detector.detect(
            clinical_state_data=state_data,
            candidates=candidate_diagnoses,
            tracer=tracer,
        )

        # ── 11. Aggregate Clinical Alerts ─────────────────────────────────
        clinical_alerts: List[ClinicalAlert] = []
        clinical_alerts.extend(red_flag_detector.to_clinical_alerts(red_flags))
        clinical_alerts.extend(ci_checker.to_clinical_alerts(contraindications))
        clinical_alerts.extend(di_detector.to_clinical_alerts(drug_interactions))
        # Risk-factor info alerts
        for rf in identified_risk_factors:
            clinical_alerts.append(
                ClinicalAlert(
                    alert_id=f"alert_rf_{rf.factor_id}",
                    alert_type="risk_factor",
                    severity="INFO",
                    title=f"Risk Factor: {rf.name}",
                    message=f"Patient has {rf.name} — increases likelihood of associated conditions.",
                    supporting_evidence=[f"Found in: {rf.source}"],
                )
            )
        # Missing-info alerts
        for mi in missing_information[:5]:  # Top 5 only to avoid noise
            clinical_alerts.append(
                ClinicalAlert(
                    alert_id=f"alert_mi_{mi.field}",
                    alert_type="missing_info",
                    severity="LOW",
                    title=f"Missing Information: {mi.field.replace('_', ' ').title()}",
                    message=mi.question,
                    supporting_evidence=[f"Relevant for: {', '.join(mi.relevant_conditions[:2])}"],
                    recommended_action=mi.question,
                )
            )

        # ── 12. Build Explainability Metadata ────────────────────────────
        explainability_metadata = tracer.finish(
            loaded_files=self._loader.loaded_files(),
        )

        # ── 13. Assemble Final Result ─────────────────────────────────────
        result = ClinicalReasoningResult(
            session_id=session_id,
            candidate_diagnoses=candidate_diagnoses,
            red_flags=red_flags,
            risk_factors=identified_risk_factors,
            recommended_investigations=recommended_investigations,
            missing_information=missing_information,
            contraindications=contraindications,
            drug_interactions=drug_interactions,
            clinical_alerts=clinical_alerts,
            explainability=explainability_metadata,
            engine_version=self.ENGINE_VERSION,
            rule_set_version=rules.version_summary(),
        )

        logger.info(
            "ClinicalReasoningEngine: Reasoning complete. "
            "session=%s | candidates=%d | red_flags=%d | investigations=%d | "
            "contraindications=%d | interactions=%d | missing=%d | "
            "duration_ms=%.1f",
            session_id,
            len(candidate_diagnoses),
            len(red_flags),
            len(recommended_investigations),
            len(contraindications),
            len(drug_interactions),
            len(missing_information),
            explainability_metadata.reasoning_duration_ms,
        )

        return result

    # ──────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _extract_state_data(clinical_state: Any) -> Dict[str, Any]:
        """
        Accept either a Pydantic ClinicalState model or a plain dict.
        Raises InvalidClinicalStateError if neither.
        """
        if isinstance(clinical_state, dict):
            return clinical_state
        if hasattr(clinical_state, "model_dump"):
            return clinical_state.model_dump()
        if hasattr(clinical_state, "dict"):
            return clinical_state.dict()
        raise InvalidClinicalStateError(
            field="clinical_state",
            reason=f"Expected ClinicalState or dict, got {type(clinical_state).__name__}",
        )

    @staticmethod
    def _get_present_symptoms(state_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return symptoms with status == 'Active' (or present == 'True')."""
        symptoms = state_data.get("symptoms", []) or []
        return [
            s for s in symptoms
            if s.get("status") == "Active" or str(s.get("present", "True")).lower() == "true"
        ]

    @staticmethod
    def _get_negated_symptoms(state_data: Dict[str, Any]) -> List[str]:
        """Return symptom names with status Negated or Resolved."""
        symptoms = state_data.get("symptoms", []) or []
        return [
            s["name"]
            for s in symptoms
            if s.get("status") in ("Negated", "Resolved")
            or str(s.get("present", "True")).lower() == "false"
        ]
