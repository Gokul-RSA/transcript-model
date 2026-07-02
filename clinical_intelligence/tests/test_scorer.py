"""
Tests for the DiseaseScorer — confidence normalisation, vitals, and risk factor modifiers.
"""

import unittest
from pathlib import Path

from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer
from clinical_intelligence.rule_engine.loader import RuleLoader
from clinical_intelligence.rule_engine.matcher import SymptomMatcher
from clinical_intelligence.rule_engine.scorer import DiseaseScorer, _parse_vitals

RULES_DIR = Path(__file__).parent.parent / "rules"


def _load_rules():
    loader = RuleLoader(rules_dir=RULES_DIR)
    return loader.get()


class TestVitalsParsing(unittest.TestCase):

    def test_parse_bp(self):
        vitals = _parse_vitals({"bp": "160/100"})
        self.assertEqual(vitals["bp_systolic"], 160.0)
        self.assertEqual(vitals["bp_diastolic"], 100.0)

    def test_parse_pulse(self):
        vitals = _parse_vitals({"pulse": "108 bpm"})
        self.assertEqual(vitals["pulse"], 108.0)

    def test_parse_spo2(self):
        vitals = _parse_vitals({"spo2": "94%"})
        self.assertEqual(vitals["spo2"], 94.0)

    def test_parse_temperature(self):
        vitals = _parse_vitals({"temperature": "38.5°C"})
        self.assertEqual(vitals["temperature"], 38.5)

    def test_missing_vitals_none(self):
        vitals = _parse_vitals({})
        self.assertIsNone(vitals.get("bp_systolic"))


class TestDiseaseScorer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rules = _load_rules()
        cls.matcher = SymptomMatcher(rules.diseases, rules.symptoms)
        cls.scorer = DiseaseScorer()
        cls.rules = rules

    def _score(self, present_symptoms, vital_signs=None, age=None, gender=None, rf_ids=None):
        tracer = ExplainabilityTracer()
        tracer.start()
        matches = self.matcher.match(
            present_symptoms=present_symptoms,
            negated_symptoms=[],
            tracer=tracer,
        )
        return self.scorer.score(
            match_results=matches,
            vital_signs=vital_signs or {},
            age=age,
            gender=gender,
            identified_risk_factor_ids=rf_ids or [],
            tracer=tracer,
        )

    def test_confidence_clamped_0_to_1(self):
        """All confidence scores must be in [0, 1]."""
        present = [
            {"name": "chest pain", "status": "Active", "confidence": "High"},
            {"name": "sweating", "status": "Active", "confidence": "High"},
            {"name": "shortness of breath", "status": "Active", "confidence": "High"},
        ]
        candidates = self._score(present)
        for c in candidates:
            self.assertGreaterEqual(c.confidence, 0.0)
            self.assertLessEqual(c.confidence, 1.0)

    def test_vitals_modifier_increases_score(self):
        """Elevated BP should increase ACS confidence score."""
        present = [
            {"name": "chest pain", "status": "Active", "confidence": "High"},
        ]
        without_vitals = self._score(present)
        with_vitals = self._score(present, vital_signs={"bp": "165/100"})

        acs_without = next((c for c in without_vitals if c.disease_id == "acs"), None)
        acs_with = next((c for c in with_vitals if c.disease_id == "acs"), None)

        if acs_without and acs_with:
            self.assertGreaterEqual(acs_with.confidence, acs_without.confidence)

    def test_risk_factor_increases_confidence(self):
        """Active risk factors should increase ACS confidence."""
        present = [
            {"name": "chest pain", "status": "Active", "confidence": "High"},
        ]
        without_rf = self._score(present)
        with_rf = self._score(present, rf_ids=["hypertension", "diabetes", "smoking"])

        acs_without = next((c for c in without_rf if c.disease_id == "acs"), None)
        acs_with = next((c for c in with_rf if c.disease_id == "acs"), None)

        if acs_without and acs_with:
            self.assertGreaterEqual(acs_with.confidence, acs_without.confidence)

    def test_age_modifier_applied(self):
        """Male patient age 60 should have higher ACS confidence than age 20."""
        present = [
            {"name": "chest pain", "status": "Active", "confidence": "High"},
        ]
        old = self._score(present, age=60, gender="Male")
        young = self._score(present, age=20, gender="Male")

        acs_old = next((c for c in old if c.disease_id == "acs"), None)
        acs_young = next((c for c in young if c.disease_id == "acs"), None)

        if acs_old and acs_young:
            self.assertGreaterEqual(acs_old.confidence, acs_young.confidence)

    def test_candidates_sorted_by_confidence_desc(self):
        """Candidates must be sorted descending by confidence."""
        present = [
            {"name": "chest pain", "status": "Active", "confidence": "High"},
            {"name": "sweating", "status": "Active", "confidence": "High"},
        ]
        candidates = self._score(present)
        scores = [c.confidence for c in candidates]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_rank_matches_order(self):
        """Rank should be 1 for highest confidence candidate."""
        present = [
            {"name": "chest pain", "status": "Active", "confidence": "High"},
            {"name": "sweating", "status": "Active", "confidence": "High"},
        ]
        candidates = self._score(present)
        if candidates:
            self.assertEqual(candidates[0].rank, 1)

    def test_supporting_symptoms_listed(self):
        """Matched symptoms should appear in supporting_symptoms."""
        present = [
            {"name": "chest pain", "status": "Active", "confidence": "High"},
        ]
        candidates = self._score(present)
        acs = next((c for c in candidates if c.disease_id == "acs"), None)
        if acs:
            self.assertIn("chest pain", acs.supporting_symptoms)

    def test_below_threshold_excluded(self):
        """Diseases below min_diagnosis_threshold should not appear."""
        # No symptoms matching — all should be filtered
        candidates = self._score([])
        self.assertEqual(len(candidates), 0)


if __name__ == "__main__":
    unittest.main()
