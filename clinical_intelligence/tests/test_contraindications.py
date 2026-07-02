"""
Tests for ContraindicationChecker and DrugInteractionDetector.
"""

import unittest
from pathlib import Path

from clinical_intelligence.rule_engine.contraindications import ContraindicationChecker
from clinical_intelligence.rule_engine.explainability import ExplainabilityTracer
from clinical_intelligence.rule_engine.interactions import DrugInteractionDetector
from clinical_intelligence.rule_engine.loader import RuleLoader

RULES_DIR = Path(__file__).parent.parent / "rules"


def _load_rules():
    loader = RuleLoader(rules_dir=RULES_DIR)
    return loader.get()


class TestContraindicationChecker(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rules = _load_rules()
        cls.checker = ContraindicationChecker(rules.contraindications)

    def _check(self, allergies=None, history=None, medications=None):
        tracer = ExplainabilityTracer()
        tracer.start()
        return self.checker.check(
            allergies=allergies or [],
            medical_history=history or [],
            current_medications=medications or [],
            recommended_investigations=[],
            tracer=tracer,
        )

    def test_penicillin_allergy_detected(self):
        """Penicillin allergy should flag the penicillin contraindication."""
        results = self._check(allergies=["Penicillin"])
        ids = [c.contraindication_id for c in results]
        self.assertIn("ci_penicillin_allergy", ids)

    def test_nsaid_contraindicated_in_peptic_ulcer(self):
        """NSAIDs should be contraindicated in peptic ulcer history."""
        results = self._check(history=["peptic ulcer disease"])
        ids = [c.contraindication_id for c in results]
        self.assertIn("ci_nsaid_peptic_ulcer", ids)

    def test_beta_blocker_contraindicated_in_asthma(self):
        """Beta-blockers should be contraindicated in asthma."""
        results = self._check(history=["asthma"])
        ids = [c.contraindication_id for c in results]
        self.assertIn("ci_beta_blocker_asthma", ids)

    def test_no_contraindications_clean_patient(self):
        """A clean patient with no relevant history should have no CIs."""
        results = self._check(
            allergies=[],
            history=["tension headache"],
            medications=["Paracetamol"],
        )
        # Should not contain penicillin or peptic ulcer CI
        ids = [c.contraindication_id for c in results]
        self.assertNotIn("ci_penicillin_allergy", ids)
        self.assertNotIn("ci_nsaid_peptic_ulcer", ids)

    def test_absolute_contraindications_first(self):
        """ABSOLUTE contraindications should appear before RELATIVE ones."""
        results = self._check(
            allergies=["Penicillin"],
            history=["peptic ulcer", "asthma"],
        )
        if len(results) > 1:
            abs_seen = False
            for ci in results:
                if ci.severity == "RELATIVE" and abs_seen:
                    break
                if ci.severity == "ABSOLUTE":
                    abs_seen = True
            # If any ABSOLUTE exists it should come first
            severities = [c.severity for c in results]
            if "ABSOLUTE" in severities and "RELATIVE" in severities:
                self.assertLess(
                    severities.index("ABSOLUTE"), severities.index("RELATIVE")
                )

    def test_ace_inhibitor_angioedema_history(self):
        """ACE inhibitor should be flagged when angioedema history present."""
        results = self._check(history=["angioedema", "previous ace inhibitor angioedema"])
        ids = [c.contraindication_id for c in results]
        self.assertIn("ci_ace_inhibitor_angioedema", ids)


class TestDrugInteractionDetector(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rules = _load_rules()
        cls.detector = DrugInteractionDetector(rules.drug_interactions)

    def _detect(self, meds, additional=None):
        tracer = ExplainabilityTracer()
        tracer.start()
        return self.detector.detect(
            current_medications=meds,
            additional_drugs=additional,
            tracer=tracer,
        )

    def test_warfarin_aspirin_major_interaction(self):
        """Warfarin + Aspirin should produce a MAJOR interaction."""
        results = self._detect(["Warfarin 3mg OD", "Aspirin 75mg OD"])
        ids = [i.interaction_id for i in results]
        self.assertIn("di_warfarin_aspirin", ids)
        major_ix = next(i for i in results if i.interaction_id == "di_warfarin_aspirin")
        self.assertEqual(major_ix.severity, "MAJOR")

    def test_ssri_tramadol_serotonin_syndrome(self):
        """SSRI + Tramadol should produce a MAJOR interaction."""
        results = self._detect(["Sertraline 50mg OD", "Tramadol 50mg TDS"])
        ids = [i.interaction_id for i in results]
        self.assertIn("di_ssri_tramadol", ids)

    def test_no_interactions_single_drug(self):
        """A single drug alone should produce no interactions."""
        results = self._detect(["Paracetamol 1g QDS"])
        self.assertEqual(len(results), 0)

    def test_major_interactions_sorted_first(self):
        """MAJOR interactions should appear before MODERATE and MINOR."""
        results = self._detect([
            "Warfarin 3mg OD",
            "Aspirin 75mg OD",
            "Sertraline 50mg OD",
            "Tramadol 50mg",
        ])
        severities = [i.severity for i in results]
        rank = {"MAJOR": 0, "MODERATE": 1, "MINOR": 2}
        for i in range(len(severities) - 1):
            self.assertLessEqual(rank.get(severities[i], 99), rank.get(severities[i + 1], 99))

    def test_interaction_has_mechanism(self):
        """Every detected interaction must have a non-empty mechanism."""
        results = self._detect(["Warfarin 3mg OD", "Aspirin 75mg OD"])
        for ix in results:
            self.assertTrue(len(ix.mechanism) > 0)

    def test_warfarin_nsaid_interaction(self):
        """Warfarin + Ibuprofen should produce interaction."""
        results = self._detect(["Warfarin", "Ibuprofen 400mg TDS"])
        ids = [i.interaction_id for i in results]
        self.assertIn("di_warfarin_nsaid", ids)

    def test_metronidazole_alcohol_interaction(self):
        """Metronidazole + alcohol should flag disulfiram-like interaction."""
        results = self._detect(["Metronidazole 400mg TDS"], additional=["alcohol"])
        ids = [i.interaction_id for i in results]
        self.assertIn("di_alcohol_metronidazole", ids)


if __name__ == "__main__":
    unittest.main()
