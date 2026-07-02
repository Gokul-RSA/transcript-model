"""
Full integration tests for the ClinicalReasoningEngine.

Tests run the complete engine end-to-end using the sample clinical state
fixture (an ACS presentation) and verify all output sections.
"""

import json
import unittest
from pathlib import Path

from clinical_intelligence.rule_engine.engine import ClinicalReasoningEngine
from clinical_intelligence.rule_engine.loader import RuleLoader
from clinical_intelligence.rule_engine.models import ClinicalReasoningResult

RULES_DIR = Path(__file__).parent.parent / "rules"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_clinical_state.json"


def _load_fixture() -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


class TestEngineFullPass(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        loader = RuleLoader(rules_dir=RULES_DIR)
        cls.engine = ClinicalReasoningEngine(loader=loader)
        cls.state = _load_fixture()
        cls.result: ClinicalReasoningResult = cls.engine.reason(cls.state)

    # ── Result structure ─────────────────────────────────────────────────

    def test_result_is_clinical_reasoning_result(self):
        self.assertIsInstance(self.result, ClinicalReasoningResult)

    def test_session_id_preserved(self):
        self.assertEqual(self.result.session_id, "test-session-acs-001")

    def test_engine_version_set(self):
        self.assertEqual(self.result.engine_version, "1.0.0")

    def test_rule_set_version_populated(self):
        self.assertGreater(self.result.rule_set_version.get("diseases", 0), 0)

    # ── Candidate Diagnoses ───────────────────────────────────────────────

    def test_has_candidate_diagnoses(self):
        self.assertGreater(len(self.result.candidate_diagnoses), 0)

    def test_acs_in_top_3_candidates(self):
        """ACS should be a top-3 candidate for this presentation."""
        top_ids = [c.disease_id for c in self.result.candidate_diagnoses[:3]]
        self.assertIn("acs", top_ids, f"ACS not in top 3. Top: {top_ids}")

    def test_confidence_sorted_desc(self):
        scores = [c.confidence for c in self.result.candidate_diagnoses]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_all_confidences_in_0_1(self):
        for c in self.result.candidate_diagnoses:
            self.assertGreaterEqual(c.confidence, 0.0)
            self.assertLessEqual(c.confidence, 1.0)

    def test_candidate_has_supporting_symptoms(self):
        for c in self.result.candidate_diagnoses[:3]:
            self.assertGreater(len(c.supporting_symptoms), 0, f"{c.name} has no supporting symptoms")

    def test_candidate_has_reasoning_trace(self):
        for c in self.result.candidate_diagnoses[:3]:
            self.assertGreater(len(c.reasoning_trace), 0, f"{c.name} has no reasoning trace")

    def test_rank_starts_at_1(self):
        if self.result.candidate_diagnoses:
            self.assertEqual(self.result.candidate_diagnoses[0].rank, 1)

    # ── Red Flags ─────────────────────────────────────────────────────────

    def test_has_red_flags(self):
        """ACS presentation with elevated BP + risk factors should trigger red flags."""
        self.assertGreater(len(self.result.red_flags), 0)

    def test_red_flags_have_recommended_action(self):
        for rf in self.result.red_flags:
            self.assertTrue(len(rf.recommended_action) > 10)

    def test_red_flags_have_severity(self):
        valid_severities = {"CRITICAL", "HIGH", "MODERATE"}
        for rf in self.result.red_flags:
            self.assertIn(rf.severity, valid_severities)

    # ── Risk Factors ──────────────────────────────────────────────────────

    def test_hypertension_risk_factor_identified(self):
        rf_ids = [r.factor_id for r in self.result.risk_factors]
        self.assertIn("hypertension", rf_ids)

    def test_diabetes_risk_factor_identified(self):
        rf_ids = [r.factor_id for r in self.result.risk_factors]
        self.assertIn("diabetes", rf_ids)

    # ── Investigations ────────────────────────────────────────────────────

    def test_has_investigations(self):
        self.assertGreater(len(self.result.recommended_investigations), 0)

    def test_ecg_recommended_for_acs(self):
        inv_ids = [i.investigation_id for i in self.result.recommended_investigations]
        self.assertIn("ecg_12lead", inv_ids)

    def test_troponin_recommended_for_acs(self):
        inv_ids = [i.investigation_id for i in self.result.recommended_investigations]
        self.assertIn("troponin", inv_ids)

    def test_investigations_sorted_by_priority(self):
        priority_rank = {"URGENT": 0, "HIGH": 1, "ROUTINE": 2}
        priorities = [priority_rank[i.priority] for i in self.result.recommended_investigations]
        self.assertEqual(priorities, sorted(priorities))

    # ── Contraindications ─────────────────────────────────────────────────

    def test_penicillin_allergy_flagged(self):
        """Patient has penicillin allergy — should be detected."""
        ci_ids = [c.contraindication_id for c in self.result.contraindications]
        self.assertIn("ci_penicillin_allergy", ci_ids)

    # ── Drug Interactions ─────────────────────────────────────────────────

    def test_warfarin_aspirin_interaction_detected(self):
        """Patient takes warfarin + aspirin — MAJOR interaction expected."""
        ix_ids = [i.interaction_id for i in self.result.drug_interactions]
        self.assertIn("di_warfarin_aspirin", ix_ids)

    def test_drug_interactions_have_mechanism(self):
        for ix in self.result.drug_interactions:
            self.assertTrue(len(ix.mechanism) > 0)

    # ── Missing Information ───────────────────────────────────────────────

    def test_has_missing_info_items(self):
        self.assertGreater(len(self.result.missing_information), 0)

    def test_missing_info_has_questions(self):
        for mi in self.result.missing_information:
            self.assertTrue(len(mi.question) > 0)

    def test_missing_info_priority_in_range(self):
        for mi in self.result.missing_information:
            self.assertIn(mi.priority, [1, 2, 3, 4, 5])

    # ── Clinical Alerts ───────────────────────────────────────────────────

    def test_has_clinical_alerts(self):
        self.assertGreater(len(self.result.clinical_alerts), 0)

    def test_clinical_alerts_have_title(self):
        for alert in self.result.clinical_alerts:
            self.assertTrue(len(alert.title) > 0)

    # ── Explainability ────────────────────────────────────────────────────

    def test_explainability_has_steps(self):
        self.assertGreater(len(self.result.explainability.reasoning_steps), 0)

    def test_explainability_rules_evaluated_nonzero(self):
        self.assertGreater(self.result.explainability.rules_evaluated, 0)

    def test_explainability_duration_nonzero(self):
        self.assertGreater(self.result.explainability.reasoning_duration_ms, 0.0)

    def test_explainability_loaded_files(self):
        self.assertGreater(len(self.result.explainability.rule_files_loaded), 0)

    # ── Serialisation ─────────────────────────────────────────────────────

    def test_result_serialises_to_json(self):
        """Result must be fully serialisable to JSON without errors."""
        json_str = self.result.model_dump_json()
        self.assertIsInstance(json_str, str)
        parsed = json.loads(json_str)
        self.assertIn("candidate_diagnoses", parsed)
        self.assertIn("red_flags", parsed)
        self.assertIn("explainability", parsed)


class TestEngineEdgeCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        loader = RuleLoader(rules_dir=RULES_DIR)
        cls.engine = ClinicalReasoningEngine(loader=loader)

    def test_empty_state_does_not_crash(self):
        """Engine must not crash with a minimal/empty state dict."""
        result = self.engine.reason({"session_id": "empty-session"})
        self.assertIsInstance(result, ClinicalReasoningResult)
        self.assertEqual(result.session_id, "empty-session")
        self.assertEqual(len(result.candidate_diagnoses), 0)

    def test_dict_input_accepted(self):
        """Engine must accept plain dict as well as Pydantic model."""
        state = {
            "session_id": "dict-input-test",
            "symptoms": [
                {"name": "chest pain", "status": "Active", "confidence": "High", "present": "True"}
            ],
            "medical_history": [],
            "current_medications": [],
            "allergies": [],
            "vital_signs": {},
            "patient_info": {"age": 50, "gender": "Male"},
        }
        result = self.engine.reason(state)
        self.assertIsInstance(result, ClinicalReasoningResult)
        self.assertGreater(len(result.candidate_diagnoses), 0)

    def test_invalid_input_raises(self):
        """Passing an unsupported type should raise InvalidClinicalStateError."""
        from clinical_intelligence.rule_engine.exceptions import InvalidClinicalStateError
        with self.assertRaises(InvalidClinicalStateError):
            self.engine.reason(12345)

    def test_unknown_symptoms_do_not_crash(self):
        """Completely unknown symptom names must be handled gracefully."""
        state = {
            "session_id": "unknown-sym",
            "symptoms": [
                {"name": "zzz_unknown_xyz_abc", "status": "Active", "confidence": "High", "present": "True"}
            ],
        }
        result = self.engine.reason(state)
        self.assertIsInstance(result, ClinicalReasoningResult)


if __name__ == "__main__":
    unittest.main()
