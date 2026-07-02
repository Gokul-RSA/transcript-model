"""
Tests for the SymptomMatcher — weighted, alias-normalised, negation-aware.
"""

import unittest
from pathlib import Path
from typing import List, Dict, Any

from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer
from clinical_intelligence.rule_engine.loader import RuleLoader
from clinical_intelligence.rule_engine.matcher import SymptomMatcher


RULES_DIR = Path(__file__).parent.parent / "rules"


def _load_rules() -> tuple:
    loader = RuleLoader(rules_dir=RULES_DIR)
    rules = loader.get()
    return rules.diseases, rules.symptoms


class TestSymptomMatcher(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.diseases, cls.symptoms = _load_rules()
        cls.matcher = SymptomMatcher(cls.diseases, cls.symptoms)

    def _run(self, present: List[Dict], negated: List[str]):
        tracer = ExplainabilityTracer()
        tracer.start()
        return self.matcher.match(
            present_symptoms=present,
            negated_symptoms=negated,
            tracer=tracer,
        )

    def _top_disease(self, results) -> str:
        return results[0].disease_id if results else ""

    def test_acs_cardinal_match(self):
        """Classic ACS presentation should rank ACS at top."""
        present = [
            {"name": "chest pain", "status": "Active", "confidence": "High"},
            {"name": "sweating", "status": "Active", "confidence": "High"},
            {"name": "shortness of breath", "status": "Active", "confidence": "High"},
        ]
        results = self._run(present, [])
        top_ids = [r.disease_id for r in results[:5]]
        self.assertIn("acs", top_ids)

    def test_alias_normalisation_breathlessness(self):
        """'breathlessness' should be treated as 'shortness of breath'."""
        present = [
            {"name": "breathlessness", "status": "Active", "confidence": "High"},
            {"name": "chest pain", "status": "Active", "confidence": "High"},
        ]
        results = self._run(present, [])
        acs = next((r for r in results if r.disease_id == "acs"), None)
        self.assertIsNotNone(acs)
        self.assertGreater(acs.raw_score, 0)

    def test_negation_applies_penalty(self):
        """Negating a cardinal symptom should add penalty."""
        present = [
            {"name": "chest pain", "status": "Active", "confidence": "High"},
        ]
        results_no_neg = self._run(present, [])
        results_with_neg = self._run(present, ["sweating"])

        acs_no_neg = next((r for r in results_no_neg if r.disease_id == "acs"), None)
        acs_with_neg = next((r for r in results_with_neg if r.disease_id == "acs"), None)
        # With negation, effective score should be same or lower
        score_no_neg = (acs_no_neg.raw_score - acs_no_neg.negation_penalty) if acs_no_neg else 0
        score_with_neg = (acs_with_neg.raw_score - acs_with_neg.negation_penalty) if acs_with_neg else 0
        self.assertGreaterEqual(score_no_neg, score_with_neg)

    def test_migraine_alias_match(self):
        """'throbbing headache' should match migraine's cardinal symptoms."""
        present = [
            {"name": "throbbing headache", "status": "Active", "confidence": "High"},
            {"name": "sensitivity to light", "status": "Active", "confidence": "High"},
            {"name": "nausea", "status": "Active", "confidence": "High"},
        ]
        results = self._run(present, [])
        top_ids = [r.disease_id for r in results[:5]]
        self.assertIn("migraine", top_ids)

    def test_empty_symptoms_all_zero(self):
        """With no symptoms, all raw scores should be zero."""
        results = self._run([], [])
        for r in results:
            self.assertEqual(r.raw_score, 0.0)

    def test_uti_dysuria_match(self):
        """Classic UTI symptoms should identify UTI as a top candidate."""
        present = [
            {"name": "dysuria", "status": "Active", "confidence": "High"},
            {"name": "frequency of urination", "status": "Active", "confidence": "High"},
            {"name": "burning on urination", "status": "Active", "confidence": "High"},
        ]
        results = self._run(present, [])
        top_ids = [r.disease_id for r in results[:5]]
        self.assertIn("uti", top_ids)

    def test_matched_cardinal_list_populated(self):
        """matched_cardinal should list the matched symptom names."""
        present = [
            {"name": "chest pain", "status": "Active", "confidence": "High"},
            {"name": "radiating arm pain", "status": "Active", "confidence": "High"},
        ]
        results = self._run(present, [])
        acs = next(r for r in results if r.disease_id == "acs")
        self.assertIn("chest pain", acs.matched_cardinal)

    def test_missing_cardinal_listed(self):
        """missing_cardinal should list cardinal symptoms not present."""
        present = [
            {"name": "sweating", "status": "Active", "confidence": "High"},
        ]
        results = self._run(present, [])
        acs = next(r for r in results if r.disease_id == "acs")
        self.assertIn("chest pain", acs.missing_cardinal)

    def test_max_possible_score_nonzero(self):
        """max_possible_score should always be > 0 for any disease with symptoms."""
        results = self._run([], [])
        for r in results:
            self.assertGreater(r.max_possible_score, 0.0)

    def test_confidence_string_to_float(self):
        """Confidence strings should map correctly to float multipliers."""
        from clinical_intelligence.rule_engine.matcher import SymptomMatcher as SM
        self.assertEqual(SM._conf_str_to_float("High"), 1.0)
        self.assertEqual(SM._conf_str_to_float("Medium"), 0.75)
        self.assertEqual(SM._conf_str_to_float("Low"), 0.5)
        self.assertEqual(SM._conf_str_to_float(0.8), 0.8)


if __name__ == "__main__":
    unittest.main()
