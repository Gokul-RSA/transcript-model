import unittest
from app.services.clinical.dictionary.loader import dictionary_manager
from app.services.clinical.extractors.negation import NegationDetector
from app.services.clinical.extractors.confidence import ConfidenceScorer
from app.services.clinical.extractors.section_detector import SectionDetector
from app.services.clinical.extractors.context import context_manager
from app.services.clinical.extractors.name_extractor import NameExtractor
from app.services.clinical.extractors.symptom_extractor import SymptomExtractor
from app.services.clinical.extractors.medication_extractor import MedicationExtractor
from app.services.clinical.extractors.diagnosis_extractor import DiagnosisExtractor
from app.services.clinical.extractors.history_extractor import HistoryExtractor
from app.services.clinical.extractors.investigation_extractor import InvestigationExtractor
from app.services.clinical.extractors.vitals_extractor import VitalsExtractor

class TestClinicalOptimization(unittest.TestCase):
    def setUp(self):
        self.negation_detector = NegationDetector()
        self.name_extractor = NameExtractor()
        self.symptom_extractor = SymptomExtractor()
        self.medication_extractor = MedicationExtractor()
        self.diagnosis_extractor = DiagnosisExtractor()
        self.history_extractor = HistoryExtractor()
        self.investigation_extractor = InvestigationExtractor()
        self.vitals_extractor = VitalsExtractor()
        self.section_detector = SectionDetector()
        
        # Clear context manager
        context_manager.clear_session("test-opt-session")
        self.section_detector.clear_session("test-opt-session")

    def tearDown(self):
        context_manager.clear_session("test-opt-session")
        self.section_detector.clear_session("test-opt-session")

    # ==========================================
    # 1. Dictionary Loader Tests (7 Tests)
    # ==========================================
    def test_dict_loader_symptoms(self):
        symptom_dict = dictionary_manager.get_symptoms()
        self.assertIn("headache", symptom_dict)
        self.assertIn("fever", symptom_dict)

    def test_dict_loader_diseases(self):
        diseases_dict = dictionary_manager.get_diseases()
        self.assertIn("diabetes", diseases_dict)
        self.assertIn("hypertension", diseases_dict)

    def test_dict_loader_drugs(self):
        drugs_dict = dictionary_manager.get_drugs()
        self.assertIn("paracetamol", drugs_dict)
        self.assertIn("ibuprofen", drugs_dict)

    def test_dict_loader_anatomy(self):
        anatomy_dict = dictionary_manager.get_anatomy()
        self.assertIn("head", anatomy_dict)
        self.assertIn("chest", anatomy_dict)

    def test_dict_loader_procedures(self):
        procedures_dict = dictionary_manager.get_procedures()
        self.assertIn("CBC", procedures_dict)
        self.assertIn("MRI", procedures_dict)

    def test_dict_loader_negations(self):
        negations_dict = dictionary_manager.get_negations()
        self.assertIn("pre_negation", negations_dict)
        self.assertIn("post_negation", negations_dict)

    def test_dict_loader_family(self):
        family_dict = dictionary_manager.get_family()
        self.assertIn("father", family_dict)
        self.assertIn("mother", family_dict)

    # ==========================================
    # 2. Section Detector Tests (9 Tests)
    # ==========================================
    def test_section_greeting(self):
        sec = self.section_detector.detect_section("test-opt-session", "Hello, welcome to the clinic", "doctor")
        self.assertEqual(sec, "Greeting")

    def test_section_chief_complaint(self):
        sec = self.section_detector.detect_section("test-opt-session", "What brings you in today?", "doctor")
        self.assertEqual(sec, "Chief Complaint")

    def test_section_hpi(self):
        sec = self.section_detector.detect_section("test-opt-session", "How long have you had this pain?", "doctor")
        self.assertEqual(sec, "History of Present Illness")

    def test_section_past_history(self):
        sec = self.section_detector.detect_section("test-opt-session", "Any past medical history?", "doctor")
        self.assertEqual(sec, "Past History")

    def test_section_medication_review(self):
        sec = self.section_detector.detect_section("test-opt-session", "Are you taking any medications regularly?", "doctor")
        self.assertEqual(sec, "Medication Review")

    def test_section_examination(self):
        sec = self.section_detector.detect_section("test-opt-session", "Let me check your blood pressure", "doctor")
        self.assertEqual(sec, "Examination")

    def test_section_assessment(self):
        sec = self.section_detector.detect_section("test-opt-session", "I suspect this is a case of migraine", "doctor")
        self.assertEqual(sec, "Assessment")

    def test_section_treatment(self):
        sec = self.section_detector.detect_section("test-opt-session", "I will prescribe ibuprofen", "doctor")
        self.assertEqual(sec, "Treatment")

    def test_section_followup(self):
        sec = self.section_detector.detect_section("test-opt-session", "Please come back in next week", "doctor")
        self.assertEqual(sec, "Follow-up")

    # ==========================================
    # 3. Negation Detector Tests (10 Tests)
    # ==========================================
    def test_negation_basic_no(self):
        self.assertTrue(self.negation_detector.is_negated("No fever today", "fever", 3, 8))

    def test_negation_denies(self):
        self.assertTrue(self.negation_detector.is_negated("The patient denies cough", "cough", 19, 24))

    def test_negation_resolved(self):
        self.assertTrue(self.negation_detector.is_negated("Headache is resolved", "Headache", 0, 8))

    def test_negation_gone(self):
        self.assertTrue(self.negation_detector.is_negated("My nausea is gone", "nausea", 3, 9))

    def test_negation_double_cancellation(self):
        self.assertFalse(self.negation_detector.is_negated("Fever is not ruled out", "Fever", 0, 5))

    def test_negation_contraction_expansion(self):
        cleaned = self.negation_detector.expand_contractions("I don't have chest pain")
        self.assertEqual(cleaned, "I do not have chest pain")

    def test_negation_contraction_negation(self):
        text = self.negation_detector.expand_contractions("I don't have fever")
        self.assertTrue(self.negation_detector.is_negated(text, "fever", 13, 18))

    def test_negation_never(self):
        self.assertTrue(self.negation_detector.is_negated("I have never had asthma", "asthma", 17, 23))

    def test_negation_ceased(self):
        self.assertTrue(self.negation_detector.is_negated("The patient has ceased smoking", "smoking", 23, 30))

    def test_negation_ruled_out_double(self):
        self.assertFalse(self.negation_detector.is_negated("Shortness of breath cannot be ruled out", "Shortness of breath", 0, 19))

    # ==========================================
    # 4. Confidence Scorer Tests (8 Tests)
    # ==========================================
    def test_conf_exact_match(self):
        score = ConfidenceScorer.calculate_confidence(True, False, False, False, False, False, False)
        self.assertAlmostEqual(score, 0.90)
        self.assertEqual(ConfidenceScorer.get_confidence_label(score), "High")

    def test_conf_synonym_match(self):
        score = ConfidenceScorer.calculate_confidence(False, True, False, False, False, False, False)
        self.assertAlmostEqual(score, 0.70)
        self.assertEqual(ConfidenceScorer.get_confidence_label(score), "Medium")

    def test_conf_same_speaker(self):
        score = ConfidenceScorer.calculate_confidence(True, False, True, False, False, False, False)
        self.assertAlmostEqual(score, 1.0)
        self.assertEqual(ConfidenceScorer.get_confidence_label(score), "High")

    def test_conf_cross_turn(self):
        score = ConfidenceScorer.calculate_confidence(True, False, False, True, False, False, False)
        self.assertAlmostEqual(score, 1.0) # 0.5 + 0.4 + 0.15 = 1.05 capped at 1.0
        self.assertEqual(ConfidenceScorer.get_confidence_label(score), "High")

    def test_conf_modifiers(self):
        score = ConfidenceScorer.calculate_confidence(False, True, False, False, True, True, False)
        self.assertAlmostEqual(score, 0.80) # 0.5 + 0.2 + 0.05 + 0.05
        self.assertEqual(ConfidenceScorer.get_confidence_label(score), "Medium")

    def test_conf_hedging_ambiguity(self):
        score = ConfidenceScorer.calculate_confidence(True, False, False, False, False, False, True)
        self.assertAlmostEqual(score, 0.70) # 0.5 + 0.4 - 0.2
        self.assertEqual(ConfidenceScorer.get_confidence_label(score), "Medium")

    def test_conf_all_negative(self):
        score = ConfidenceScorer.calculate_confidence(False, False, False, False, False, False, False)
        self.assertAlmostEqual(score, 0.50)
        self.assertEqual(ConfidenceScorer.get_confidence_label(score), "Low")

    def test_conf_low_threshold(self):
        score = ConfidenceScorer.calculate_confidence(False, False, False, False, False, False, True)
        self.assertAlmostEqual(score, 0.30) # 0.5 - 0.2
        self.assertEqual(ConfidenceScorer.get_confidence_label(score), "Low")

    # ==========================================
    # 5. Name Extractor Tests (8 Tests)
    # ==========================================
    def test_name_my_name_is(self):
        name = self.name_extractor.extract_name("Hello doctor, my name is John.", "patient")
        self.assertEqual(name, "John")

    def test_name_i_am(self):
        name = self.name_extractor.extract_name("I am Mr. Sarah Jenkins.", "patient")
        self.assertEqual(name, "Mr. Sarah")

    def test_name_call_me(self):
        name = self.name_extractor.extract_name("You can call me Johnson.", "patient")
        self.assertEqual(name, "Johnson")

    def test_name_greeting_address(self):
        name = self.name_extractor.extract_name("Hello Mr. Jones, how are you?", "doctor")
        self.assertEqual(name, "Mr. Jones")

    def test_name_doctor_ignore(self):
        name = self.name_extractor.extract_name("I am Dr. Robert Smith speaking.", "doctor")
        self.assertIsNone(name)

    def test_name_doctor_mixed(self):
        name = self.name_extractor.extract_name("I'm Dr. Robert. Good morning Mr. Jones.", "doctor")
        self.assertEqual(name, "Mr. Jones")

    def test_name_dr_title_patient(self):
        name = self.name_extractor.extract_name("My name is Dr. John.", "patient")
        self.assertEqual(name, "Dr. John")

    def test_name_honorifics(self):
        name = self.name_extractor.extract_name("Morning Mrs. Peterson.", "doctor")
        self.assertEqual(name, "Mrs. Peterson")

    # ==========================================
    # 6. Context Manager & Memory Tests (10 Tests)
    # ==========================================
    def test_context_add_and_retrieve_pronoun(self):
        context_manager.add_entity("test-opt-session", "symptom", "headache", "symptom_headache", 100.0, "Chief Complaint")
        entity = context_manager.resolve_pronoun("test-opt-session", "it", 101.0)
        self.assertIsNotNone(entity)
        self.assertEqual(entity["name"], "headache")

    def test_context_expiry_timeout(self):
        context_manager.add_entity("test-opt-session", "symptom", "headache", "symptom_headache", 100.0, "Chief Complaint")
        # Beyond 60 seconds timeout
        entity = context_manager.resolve_pronoun("test-opt-session", "it", 200.0)
        self.assertIsNone(entity)

    def test_context_expiry_turns(self):
        context_manager.add_entity("test-opt-session", "symptom", "headache", "symptom_headache", 100.0, "Chief Complaint")
        # 4 turns updates
        context_manager.update_turns("test-opt-session", "Chief Complaint")
        context_manager.update_turns("test-opt-session", "Chief Complaint")
        context_manager.update_turns("test-opt-session", "Chief Complaint")
        context_manager.update_turns("test-opt-session", "Chief Complaint")
        
        entity = context_manager.resolve_pronoun("test-opt-session", "it", 101.0)
        self.assertIsNone(entity)

    def test_context_expiry_section_change(self):
        context_manager.add_entity("test-opt-session", "symptom", "headache", "symptom_headache", 100.0, "Chief Complaint")
        # Update section to Treatment
        context_manager.update_turns("test-opt-session", "Treatment")
        entity = context_manager.resolve_pronoun("test-opt-session", "it", 101.0)
        self.assertIsNone(entity)

    def test_context_new_symptom_replaces_active(self):
        context_manager.add_entity("test-opt-session", "symptom", "headache", "symptom_headache", 100.0, "Chief Complaint")
        context_manager.add_entity("test-opt-session", "symptom", "fever", "symptom_fever", 102.0, "Chief Complaint")
        entity = context_manager.resolve_pronoun("test-opt-session", "it", 103.0)
        self.assertEqual(entity["name"], "fever")

    def test_context_modifier_target_single(self):
        context_manager.add_entity("test-opt-session", "symptom", "headache", "symptom_headache", 100.0, "Chief Complaint")
        target = context_manager.get_modifier_target("test-opt-session", "duration", 101.0)
        self.assertNotEqual(target, "Needs clarification")
        self.assertEqual(target["name"], "headache")

    def test_context_modifier_target_ambiguity(self):
        context_manager.add_entity("test-opt-session", "symptom", "headache", "symptom_headache", 100.0, "Chief Complaint")
        context_manager.add_entity("test-opt-session", "symptom", "fever", "symptom_fever", 101.0, "Chief Complaint")
        # Both active, should trigger ambiguity
        target = context_manager.get_modifier_target("test-opt-session", "duration", 102.0)
        self.assertEqual(target, "Needs clarification")

    def test_context_clear_session(self):
        context_manager.add_entity("test-opt-session", "symptom", "headache", "symptom_headache", 100.0, "Chief Complaint")
        context_manager.clear_session("test-opt-session")
        entity = context_manager.resolve_pronoun("test-opt-session", "it", 101.0)
        self.assertIsNone(entity)

    def test_context_pronoun_invalid(self):
        context_manager.add_entity("test-opt-session", "symptom", "headache", "symptom_headache", 100.0, "Chief Complaint")
        entity = context_manager.resolve_pronoun("test-opt-session", "what", 101.0)
        self.assertIsNone(entity)

    def test_context_modifier_empty(self):
        target = context_manager.get_modifier_target("test-opt-session", "duration", 100.0)
        self.assertIsNone(target)

    # ==========================================
    # 7. Extractors Modular Testing (9 Tests)
    # ==========================================
    def test_symptom_extractor_basic(self):
        res = self.symptom_extractor.extract_symptoms("I have severe cough", "patient")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].name, "cough")
        self.assertEqual(res[0].severity, "severe")

    def test_medication_extractor_full(self):
        res = self.medication_extractor.extract_medications("Take paracetamol 650 mg twice daily orally after meals for five days", "doctor")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].name, "paracetamol")
        self.assertEqual(res[0].dosage, "650 mg")
        self.assertEqual(res[0].frequency, "Twice daily")
        self.assertEqual(res[0].duration, "five days")
        self.assertEqual(res[0].route, "Orally")
        self.assertEqual(res[0].instructions, "After meals")
        self.assertFalse(res[0].prn)

    def test_medication_extractor_prn(self):
        res = self.medication_extractor.extract_medications("Take ibuprofen 400 mg as needed", "doctor")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].name, "ibuprofen")
        self.assertTrue(res[0].prn)

    def test_diagnosis_extractor_diabetes(self):
        res = self.diagnosis_extractor.extract_diagnoses("I have diabetes mellitus", "patient")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].name, "diabetes")

    def test_history_extractor_family(self):
        res = self.history_extractor.extract_history("Father had hypertension", "patient")
        self.assertEqual(len(res["family_histories"]), 1)
        self.assertEqual(res["family_histories"][0].relationship, "father")
        self.assertEqual(res["family_histories"][0].condition, "hypertension")

    def test_history_extractor_social(self):
        res = self.history_extractor.extract_history("The patient is a former smoker", "patient")
        smoking_rf = next(r for r in res["risk_factors"] if r.name == "smoking")
        self.assertFalse(smoking_rf.present) # quit/former smoking is negated

    def test_investigation_extractor_scans(self):
        res = self.investigation_extractor.extract_investigations("Let's order a complete blood count and MRI", "doctor")
        self.assertEqual(len(res), 2)
        self.assertIn("CBC", [p.name for p in res])
        self.assertIn("MRI", [p.name for p in res])

    def test_vitals_extractor_all(self):
        vitals = self.vitals_extractor.extract_vitals("Pulse was 72 bpm, BP is 120/80 and temperature is 98.6 F")
        self.assertEqual(vitals["pulse"], "72")
        self.assertEqual(vitals["bp"], "120/80")
        self.assertEqual(vitals["temperature"], "98.6")

    def test_vitals_extractor_none(self):
        vitals = self.vitals_extractor.extract_vitals("Just a normal conversation without numbers.")
        self.assertIsNone(vitals["bp"])
        self.assertIsNone(vitals["pulse"])

if __name__ == "__main__":
    unittest.main()
