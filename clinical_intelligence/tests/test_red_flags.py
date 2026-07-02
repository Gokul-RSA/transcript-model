"""
Tests for the RedFlagDetector — all 7 life-threatening conditions.
"""

import unittest
from pathlib import Path

from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer
from clinical_intelligence.rule_engine.loader import RuleLoader
from clinical_intelligence.rule_engine.red_flags import RedFlagDetector

RULES_DIR = Path(__file__).parent.parent / "rules"


def _load_red_flags():
    loader = RuleLoader(rules_dir=RULES_DIR)
    return loader.get().red_flags


class TestRedFlagDetector(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.detector = RedFlagDetector(_load_red_flags())

    def _detect(self, symptoms, vitals=None, history=None, rf_ids=None, age=None):
        tracer = ExplainabilityTracer()
        tracer.start()
        return self.detector.detect(
            present_symptoms=set(symptoms),
            negated_symptoms=set(),
            vital_signs_raw=vitals or {},
            medical_history=history or [],
            risk_factor_ids=rf_ids or [],
            age=age,
            tracer=tracer,
        )

    # ── ACS ───────────────────────────────────────────────────────────────

    def test_acs_fires_on_chest_pain_high_bp_age(self):
        """ACS red flag fires when chest pain + elevated BP + age ≥ 40."""
        alerts = self._detect(
            symptoms=["chest pain"],
            vitals={"bp": "158/94"},
            history=["hypertension"],
            rf_ids=["hypertension"],
            age=52,
        )
        flag_ids = [a.flag_id for a in alerts]
        self.assertTrue(
            any("acs" in fid for fid in flag_ids),
            f"ACS red flag not fired. Fired: {flag_ids}",
        )

    def test_acs_not_fires_without_any_trigger(self):
        """ACS red flag should not fire for unrelated symptoms."""
        alerts = self._detect(symptoms=["nausea", "headache"])
        flag_ids = [a.flag_id for a in alerts]
        self.assertFalse(any("acs" in fid or "stemi" in fid for fid in flag_ids))

    # ── Stroke ────────────────────────────────────────────────────────────

    def test_stroke_fires_on_facial_droop_speech(self):
        """Stroke red flag fires on facial droop + speech difficulty."""
        alerts = self._detect(
            symptoms=["sudden facial droop", "speech difficulty"],
            vitals={"bp": "168/100"},
            age=55,
        )
        flag_ids = [a.flag_id for a in alerts]
        self.assertTrue(
            any("stroke" in fid for fid in flag_ids),
            f"Stroke red flag not fired. Fired: {flag_ids}",
        )

    # ── Sepsis ────────────────────────────────────────────────────────────

    def test_sepsis_fires_on_fever_high_pulse_low_bp(self):
        """Sepsis fires on fever + tachycardia + hypotension."""
        alerts = self._detect(
            symptoms=["fever", "chills"],
            vitals={"bp": "86/54", "pulse": "102", "temperature": "38.8"},
            rf_ids=["diabetes"],
            age=70,
        )
        flag_ids = [a.flag_id for a in alerts]
        self.assertTrue(
            any("sepsis" in fid for fid in flag_ids),
            f"Sepsis red flag not fired. Fired: {flag_ids}",
        )

    # ── Hypertensive Crisis ───────────────────────────────────────────────

    def test_hypertensive_crisis_fires_on_bp_gt_180(self):
        """Hypertensive crisis fires on BP > 180 + severe headache."""
        alerts = self._detect(
            symptoms=["severe headache", "vision changes"],
            vitals={"bp": "192/122"},
            history=["hypertension"],
        )
        flag_ids = [a.flag_id for a in alerts]
        self.assertTrue(
            any("hypertensive" in fid for fid in flag_ids),
            f"Hypertensive crisis not fired. Fired: {flag_ids}",
        )

    # ── Anaphylaxis ───────────────────────────────────────────────────────

    def test_anaphylaxis_fires_on_urticaria_low_bp(self):
        """Anaphylaxis fires on urticaria + hypotension."""
        alerts = self._detect(
            symptoms=["urticaria", "throat swelling"],
            vitals={"bp": "82/50", "pulse": "115"},
            rf_ids=["known_allergy"],
        )
        flag_ids = [a.flag_id for a in alerts]
        self.assertTrue(
            any("anaphylaxis" in fid for fid in flag_ids),
            f"Anaphylaxis not fired. Fired: {flag_ids}",
        )

    # ── Respiratory Failure ───────────────────────────────────────────────

    def test_respiratory_failure_fires_on_low_spo2(self):
        """Respiratory failure fires on SpO2 < 90%."""
        alerts = self._detect(
            symptoms=["shortness of breath"],
            vitals={"spo2": "88", "pulse": "125"},
            history=["copd"],
            rf_ids=["copd"],
        )
        flag_ids = [a.flag_id for a in alerts]
        self.assertTrue(
            any("respiratory" in fid for fid in flag_ids),
            f"Respiratory failure not fired. Fired: {flag_ids}",
        )

    # ── Severity ordering ─────────────────────────────────────────────────

    def test_alerts_sorted_critical_first(self):
        """CRITICAL alerts must appear before HIGH and MODERATE."""
        alerts = self._detect(
            symptoms=["chest pain", "fever"],
            vitals={"bp": "185/115", "temperature": "38.9", "pulse": "105"},
            history=["hypertension"],
            rf_ids=["hypertension"],
            age=55,
        )
        if len(alerts) > 1:
            for i in range(len(alerts) - 1):
                sev_a = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2}.get(alerts[i].severity, 99)
                sev_b = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2}.get(alerts[i + 1].severity, 99)
                self.assertLessEqual(sev_a, sev_b)

    def test_red_flag_has_recommended_action(self):
        """Every fired red flag must include a non-empty recommended_action."""
        alerts = self._detect(
            symptoms=["chest pain"],
            vitals={"bp": "155/95"},
            rf_ids=["hypertension"],
            age=50,
        )
        for alert in alerts:
            self.assertTrue(len(alert.recommended_action) > 0)


if __name__ == "__main__":
    unittest.main()
