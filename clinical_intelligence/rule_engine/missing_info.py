"""
Missing Information Detector.

Analyses the current ClinicalState to identify important clinical details
that have not yet been collected and generates prioritised follow-up questions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer
from clinical_intelligence.rule_engine.models import CandidateDiagnosis, MissingInfoItem

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Master list of missing-info rules.
# Each entry defines a clinical field, detection logic, a follow-up question,
# priority (1=most urgent), and the disease IDs this is relevant for.
# ──────────────────────────────────────────────────────────────────────────

_MISSING_INFO_RULES: List[Dict[str, Any]] = [
    {
        "field": "pain_radiation",
        "question": "Does the pain radiate anywhere — to the arm, jaw, shoulder, or back?",
        "priority": 1,
        "relevant_disease_ids": ["acs", "unstable_angina", "pancreatitis", "cholecystitis"],
        "check_fn": "has_radiation",
    },
    {
        "field": "pain_character",
        "question": "How would you describe the character of the pain — sharp, dull, burning, pressure, or cramping?",
        "priority": 1,
        "relevant_disease_ids": ["acs", "gerd", "peptic_ulcer", "appendicitis", "cholecystitis", "pancreatitis"],
        "check_fn": "has_severity",
    },
    {
        "field": "ecg_findings",
        "question": "Has an ECG been performed? If so, what were the findings?",
        "priority": 1,
        "relevant_disease_ids": ["acs", "unstable_angina", "heart_failure", "pulmonary_embolism"],
        "check_fn": "has_ecg",
    },
    {
        "field": "troponin_result",
        "question": "What is the troponin level? Has serial troponin been checked at 0, 3, and 6 hours?",
        "priority": 1,
        "relevant_disease_ids": ["acs", "unstable_angina"],
        "check_fn": "has_troponin",
    },
    {
        "field": "fever_duration",
        "question": "How long has the fever been present and what is the highest temperature recorded?",
        "priority": 2,
        "relevant_disease_ids": ["sepsis", "pneumonia", "pyelonephritis", "meningitis", "appendicitis"],
        "check_fn": "has_fever_duration",
    },
    {
        "field": "smoking_history",
        "question": "Does the patient smoke or have a smoking history? If so, how many pack-years?",
        "priority": 2,
        "relevant_disease_ids": ["copd_exacerbation", "acs", "ischemic_stroke", "pulmonary_embolism"],
        "check_fn": "has_smoking_history",
    },
    {
        "field": "spo2",
        "question": "What is the oxygen saturation (SpO2) on air?",
        "priority": 1,
        "relevant_disease_ids": ["pulmonary_embolism", "pneumonia", "sepsis", "copd_exacerbation", "asthma_attack"],
        "check_fn": "has_spo2",
    },
    {
        "field": "blood_pressure",
        "question": "What is the current blood pressure?",
        "priority": 1,
        "relevant_disease_ids": ["acs", "ischemic_stroke", "hypertensive_crisis", "heart_failure", "sepsis"],
        "check_fn": "has_bp",
    },
    {
        "field": "pulse_rate",
        "question": "What is the heart rate / pulse rate?",
        "priority": 1,
        "relevant_disease_ids": ["sepsis", "anaphylaxis", "pulmonary_embolism", "acs"],
        "check_fn": "has_pulse",
    },
    {
        "field": "duration_of_symptoms",
        "question": "When did the symptoms start? How long have they been present?",
        "priority": 2,
        "relevant_disease_ids": ["acs", "ischemic_stroke", "appendicitis"],
        "check_fn": "has_duration",
    },
    {
        "field": "onset_character",
        "question": "Was the onset of symptoms sudden or gradual?",
        "priority": 2,
        "relevant_disease_ids": ["ischemic_stroke", "pulmonary_embolism", "acs", "anaphylaxis"],
        "check_fn": "has_onset",
    },
    {
        "field": "allergy_history",
        "question": "Does the patient have any known drug or food allergies?",
        "priority": 1,
        "relevant_disease_ids": ["anaphylaxis"],
        "check_fn": "has_allergy_info",
    },
    {
        "field": "fast_score",
        "question": "FAST assessment: Is there facial drooping, arm weakness, or speech difficulty?",
        "priority": 1,
        "relevant_disease_ids": ["ischemic_stroke"],
        "check_fn": "has_fast_symptoms",
    },
    {
        "field": "urinary_symptoms",
        "question": "Are there any urinary symptoms — burning, frequency, blood in urine, or flank pain?",
        "priority": 2,
        "relevant_disease_ids": ["uti", "pyelonephritis", "sepsis"],
        "check_fn": "has_urinary_symptoms",
    },
    {
        "field": "alcohol_nsaid_use",
        "question": "Does the patient drink alcohol regularly or take NSAIDs (ibuprofen, aspirin)?",
        "priority": 2,
        "relevant_disease_ids": ["peptic_ulcer", "gerd", "pancreatitis"],
        "check_fn": "has_alcohol_nsaid",
    },
    {
        "field": "leg_symptoms",
        "question": "Is there any calf pain, tenderness, swelling, or leg redness?",
        "priority": 1,
        "relevant_disease_ids": ["dvt", "pulmonary_embolism"],
        "check_fn": "has_leg_symptoms",
    },
    {
        "field": "immobilisation_history",
        "question": "Has there been any period of prolonged immobilisation, recent surgery, or long-distance travel?",
        "priority": 2,
        "relevant_disease_ids": ["dvt", "pulmonary_embolism"],
        "check_fn": "has_immobilisation",
    },
    {
        "field": "family_history",
        "question": "Is there any relevant family history — heart disease, diabetes, stroke, or cancer?",
        "priority": 3,
        "relevant_disease_ids": ["acs", "ischemic_stroke", "type2_diabetes", "migraine"],
        "check_fn": "has_family_history",
    },
    {
        "field": "medication_compliance",
        "question": "Is the patient taking their medications as prescribed? Any missed doses?",
        "priority": 2,
        "relevant_disease_ids": ["hypertensive_crisis", "type2_diabetes", "heart_failure"],
        "check_fn": "has_medication",
    },
    {
        "field": "headache_character",
        "question": "Is the headache throbbing or pressure-type? Is it one-sided or bilateral? Any visual symptoms (aura)?",
        "priority": 2,
        "relevant_disease_ids": ["migraine", "tension_headache", "meningitis"],
        "check_fn": "has_headache_detail",
    },
    {
        "field": "glucose_result",
        "question": "What is the blood glucose level? Has HbA1c been checked?",
        "priority": 2,
        "relevant_disease_ids": ["type2_diabetes", "sepsis"],
        "check_fn": "has_glucose",
    },
]


def _has_symptom_keyword(symptoms: List[Dict], *keywords: str) -> bool:
    """Check if any active symptom name contains one of the keywords."""
    names = {s.get("name", "").lower() for s in symptoms if s.get("status") == "Active"}
    return any(any(kw in name for name in names) for kw in keywords)


class MissingInfoDetector:
    """
    Identifies important missing clinical information based on the patient's
    current state and the candidate diagnoses being considered.
    """

    def detect(
        self,
        *,
        clinical_state_data: Dict[str, Any],
        candidates: List[CandidateDiagnosis],
        tracer: ExplainabilityTracer,
    ) -> List[MissingInfoItem]:
        """
        Return a priority-ordered list of missing clinical information items.

        Parameters
        ----------
        clinical_state_data:
            The model_dump() of the ClinicalState.
        candidates:
            Active candidate diagnoses (used to scope which questions are relevant).
        tracer:
            Explainability tracer.
        """
        candidate_ids = {c.disease_id for c in candidates}
        vital_signs = clinical_state_data.get("vital_signs", {}) or {}
        symptoms = clinical_state_data.get("symptoms", []) or []
        history = [h.lower() for h in (clinical_state_data.get("medical_history", []) or [])]
        medications = clinical_state_data.get("current_medications", []) or []
        allergies = clinical_state_data.get("allergies", []) or []
        family_history = clinical_state_data.get("family_history", []) or []
        duration = clinical_state_data.get("duration")

        missing: List[MissingInfoItem] = []

        for rule in _MISSING_INFO_RULES:
            # Only suggest if at least one relevant candidate is active
            relevant = rule.get("relevant_disease_ids", [])
            if not any(rid in candidate_ids for rid in relevant):
                continue

            check_fn_name = rule.get("check_fn", "")
            check_fn = getattr(self, f"_check_{check_fn_name}", None)
            if check_fn is None:
                continue

            tracer.increment_evaluated()

            already_present = check_fn(
                symptoms=symptoms,
                vital_signs=vital_signs,
                history=history,
                medications=medications,
                allergies=allergies,
                family_history=family_history,
                duration=duration,
            )

            if not already_present:
                relevant_conditions = [
                    c.name for c in candidates if c.disease_id in relevant
                ]
                missing.append(
                    MissingInfoItem(
                        field=rule["field"],
                        question=rule["question"],
                        priority=rule["priority"],
                        relevant_conditions=relevant_conditions,
                    )
                )
                tracer.increment_matched()
                tracer.add_step(
                    component="MissingInfoDetector",
                    description=f"Missing info: {rule['field']}",
                    input_facts=[f"relevant for: {', '.join(relevant_conditions[:3])}"],
                    output=f"follow-up question generated (priority={rule['priority']})",
                )

        # Sort by priority ascending (1 = most urgent)
        missing.sort(key=lambda m: (m.priority, m.field))
        return missing

    # ── Check functions ───────────────────────────────────────────────────

    def _check_has_radiation(self, *, symptoms, **_) -> bool:
        return _has_symptom_keyword(symptoms, "radiat", "arm", "jaw", "back", "shoulder")

    def _check_has_severity(self, *, symptoms, **_) -> bool:
        return any(s.get("severity") for s in symptoms)

    def _check_has_ecg(self, *, history, medications, **_) -> bool:
        return any("ecg" in h or "electrocardiogram" in h for h in history)

    def _check_has_troponin(self, *, history, **_) -> bool:
        return any("troponin" in h for h in history)

    def _check_has_fever_duration(self, *, symptoms, duration, **_) -> bool:
        has_fever = _has_symptom_keyword(symptoms, "fever", "temperature")
        return has_fever and duration is not None

    def _check_has_smoking_history(self, *, history, **_) -> bool:
        return any("smok" in h or "tobacco" in h or "cigarette" in h for h in history)

    def _check_has_spo2(self, *, vital_signs, **_) -> bool:
        return bool(vital_signs.get("spo2"))

    def _check_has_bp(self, *, vital_signs, **_) -> bool:
        return bool(vital_signs.get("bp"))

    def _check_has_pulse(self, *, vital_signs, **_) -> bool:
        return bool(vital_signs.get("pulse"))

    def _check_has_duration(self, *, duration, **_) -> bool:
        return duration is not None

    def _check_has_onset(self, *, symptoms, **_) -> bool:
        return _has_symptom_keyword(symptoms, "sudden", "gradual", "acute")

    def _check_has_allergy_info(self, *, allergies, **_) -> bool:
        return bool(allergies)

    def _check_has_fast_symptoms(self, *, symptoms, **_) -> bool:
        return _has_symptom_keyword(
            symptoms, "facial", "arm weak", "speech", "slurred"
        )

    def _check_has_urinary_symptoms(self, *, symptoms, **_) -> bool:
        return _has_symptom_keyword(
            symptoms, "dysuria", "burn", "frequen", "urin", "hematuria"
        )

    def _check_has_alcohol_nsaid(self, *, history, medications, **_) -> bool:
        combined = " ".join(history) + " ".join(m.lower() for m in medications)
        return any(kw in combined for kw in ["alcohol", "ibuprofen", "naproxen", "nsaid", "diclofenac"])

    def _check_has_leg_symptoms(self, *, symptoms, **_) -> bool:
        return _has_symptom_keyword(symptoms, "calf", "leg", "dvt", "clot")

    def _check_has_immobilisation(self, *, history, **_) -> bool:
        return any(kw in h for h in history for kw in ["bed rest", "immobil", "surgery", "flight", "travel"])

    def _check_has_family_history(self, *, family_history, **_) -> bool:
        return bool(family_history)

    def _check_has_medication(self, *, medications, **_) -> bool:
        return bool(medications)

    def _check_has_headache_detail(self, *, symptoms, **_) -> bool:
        for s in symptoms:
            if "headache" in s.get("name", "").lower() and s.get("severity"):
                return True
        return _has_symptom_keyword(symptoms, "aura", "pulsating", "unilateral", "bilateral")

    def _check_has_glucose(self, *, history, **_) -> bool:
        return any("glucose" in h or "hba1c" in h or "diabetes" in h for h in history)
