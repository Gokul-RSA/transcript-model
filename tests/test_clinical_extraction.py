import unittest
from app.services.clinical.models import ClinicalExtractionResult
from app.services.clinical.normalizer import ClinicalNormalizer
from app.services.clinical.extractor import ClinicalEntityExtractor
from app.services.clinical.pipeline import ClinicalProcessingPipeline

class TestClinicalExtraction(unittest.TestCase):
    def setUp(self):
        self.normalizer = ClinicalNormalizer()
        self.extractor = ClinicalEntityExtractor()
        self.pipeline = ClinicalProcessingPipeline()

    def test_symptom_with_severity(self):
        # 1. "I have severe headache" -> Expected: symptom=headache, severity=severe
        text = "I have severe headache"
        res = self.extractor.extract(text)
        self.assertEqual(len(res["symptoms"]), 1)
        self.assertEqual(res["symptoms"][0].name, "headache")
        self.assertEqual(res["symptoms"][0].severity, "severe")
        self.assertTrue(res["symptoms"][0].present)
        self.assertIsNone(res["symptoms"][0].duration)

    def test_symptom_with_duration(self):
        # 2. "I have fever for two days" -> Expected: symptom=fever, duration=two days
        text = "I have fever for two days"
        res = self.extractor.extract(text)
        self.assertEqual(len(res["symptoms"]), 1)
        self.assertEqual(res["symptoms"][0].name, "fever")
        self.assertEqual(res["symptoms"][0].duration, "two days")  # leading 'for' is stripped
        self.assertTrue(res["symptoms"][0].present)
        self.assertIsNone(res["symptoms"][0].severity)

    def test_medication_mention(self):
        # 3. "I took paracetamol" -> Expected: medication=paracetamol
        text = "I took paracetamol"
        res = self.extractor.extract(text)
        self.assertEqual(len(res["medications"]), 1)
        self.assertEqual(res["medications"][0].name, "paracetamol")
        self.assertTrue(res["medications"][0].present)

    def test_diagnosis_mention(self):
        # 4. "I have hypertension" -> Expected: diagnosis=hypertension
        text = "I have hypertension"
        res = self.extractor.extract(text)
        self.assertEqual(len(res["diagnoses"]), 1)
        self.assertEqual(res["diagnoses"][0].name, "hypertension")
        self.assertTrue(res["diagnoses"][0].present)

    def test_procedure_mention(self):
        # 5. "Doctor ordered an MRI" -> Expected: procedure=MRI
        text = "Doctor ordered an MRI"
        res = self.extractor.extract(text)
        self.assertEqual(len(res["procedures"]), 1)
        self.assertEqual(res["procedures"][0].name, "MRI")
        self.assertTrue(res["procedures"][0].present)

    def test_multiple_entities_in_one_sentence(self):
        # 6. Multiple entities in one sentence.
        text = "The patient with diabetes has a mild cough and was prescribed ibuprofen."
        res = self.extractor.extract(text)
        
        self.assertEqual(len(res["diagnoses"]), 1)
        self.assertEqual(res["diagnoses"][0].name, "diabetes")
        
        self.assertEqual(len(res["symptoms"]), 1)
        self.assertEqual(res["symptoms"][0].name, "cough")
        self.assertEqual(res["symptoms"][0].severity, "mild")
        
        self.assertEqual(len(res["medications"]), 1)
        self.assertEqual(res["medications"][0].name, "ibuprofen")

    def test_case_insensitive_matching(self):
        # 7. Case-insensitive matching.
        text = "I had a MILD FEVER and took PARACETAMOL for it."
        res = self.extractor.extract(text)
        
        self.assertEqual(len(res["symptoms"]), 1)
        self.assertEqual(res["symptoms"][0].name, "fever")
        self.assertEqual(res["symptoms"][0].severity, "mild")
        
        self.assertEqual(len(res["medications"]), 1)
        self.assertEqual(res["medications"][0].name, "paracetamol")

    def test_normalization_before_extraction(self):
        # 8. Normalization before extraction.
        text = "I have a head ache due to high blood pressure"
        
        # Verify direct normalization
        normalized = self.normalizer.normalize(text)
        self.assertEqual(normalized, "I have a headache due to hypertension")
        
        # Verify complete pipeline
        data = {
            "session_id": "session-xyz",
            "speaker_id": "patient",
            "transcript": text,
            "timestamp": 123.45
        }
        res = self.pipeline.process(data)
        
        self.assertIsInstance(res, ClinicalExtractionResult)
        self.assertEqual(res.session_id, "session-xyz")
        self.assertEqual(res.speaker_id, "patient")
        self.assertEqual(res.timestamp, 123.45)
        
        self.assertEqual(len(res.symptoms), 1)
        self.assertEqual(res.symptoms[0].name, "headache")
        self.assertTrue(res.symptoms[0].present)
        
        self.assertEqual(len(res.diagnoses), 1)
        self.assertEqual(res.diagnoses[0].name, "hypertension")
        self.assertTrue(res.diagnoses[0].present)

    def test_empty_input(self):
        # 9. Empty input.
        res_empty = self.extractor.extract("")
        self.assertEqual(len(res_empty["symptoms"]), 0)
        self.assertEqual(len(res_empty["medications"]), 0)
        self.assertEqual(len(res_empty["diagnoses"]), 0)
        self.assertEqual(len(res_empty["procedures"]), 0)

        res_none = self.extractor.extract(None)
        self.assertEqual(len(res_none["symptoms"]), 0)

    def test_no_entities_present(self):
        # 10. No entities present.
        text = "Hello doctor, how are you today? Yes, I am doing fine."
        res = self.extractor.extract(text)
        self.assertEqual(len(res["symptoms"]), 0)
        self.assertEqual(len(res["medications"]), 0)
        self.assertEqual(len(res["diagnoses"]), 0)
        self.assertEqual(len(res["procedures"]), 0)

    def test_negation_detection(self):
        # UPGRADE: Verify pre- and post-negation patterns across entities
        negated_cases = [
            ("I do not have a fever", "symptoms", "fever"),
            ("No cough present today", "symptoms", "cough"),
            ("Chest pain has been ruled out", "symptoms", "chest pain"),
            ("The patient denies nausea", "symptoms", "nausea"),
            ("We did not prescribe paracetamol", "medications", "paracetamol"),
            ("An MRI was ruled out", "procedures", "MRI")
        ]
        
        for text, category, name in negated_cases:
            with self.subTest(text=text):
                res = self.extractor.extract(text)
                self.assertEqual(len(res[category]), 1)
                self.assertEqual(res[category][0].name, name)
                self.assertFalse(res[category][0].present, f"Expected {name} to be negated in: '{text}'")

        # Verify multiple negated entities in one sentence
        multi_negated = "No diabetes or infection was diagnosed"
        res_multi = self.extractor.extract(multi_negated)
        self.assertEqual(len(res_multi["diagnoses"]), 2)
        for diag in res_multi["diagnoses"]:
            self.assertIn(diag.name, ["diabetes", "infection"])
            self.assertFalse(diag.present)

        # Verify negation boundaries do not leak across clauses
        clause_text = "No fever, but the patient has a cough."
        res_clause = self.extractor.extract(clause_text)
        
        self.assertEqual(len(res_clause["symptoms"]), 2)
        # Fever should be negated
        fever_ent = next(s for s in res_clause["symptoms"] if s.name == "fever")
        self.assertFalse(fever_ent.present)
        # Cough should be present (negation blocked by clause boundary "but")
        cough_ent = next(s for s in res_clause["symptoms"] if s.name == "cough")
        self.assertTrue(cough_ent.present)

    def test_clause_based_proximity_association(self):
        # UPGRADE: Verify that severity and duration are correctly bounded to their clause symptoms
        text = "The patient reports a severe cough and a mild headache."
        res = self.extractor.extract(text)
        
        self.assertEqual(len(res["symptoms"]), 2)
        cough_ent = next(s for s in res["symptoms"] if s.name == "cough")
        self.assertEqual(cough_ent.severity, "severe")
        
        headache_ent = next(s for s in res["symptoms"] if s.name == "headache")
        self.assertEqual(headache_ent.severity, "mild")

    def test_rich_synonyms_normalization(self):
        # UPGRADE: Verify that pounding head, light-headed, throwing up, and difficulty breathing map correctly
        synonym_cases = [
            ("My head has been pounding since yesterday", "headache", "yesterday"),
            ("I feel light-headed today", "dizziness", "today"),
            ("He was throwing up this morning", "nausea", None),
            ("Patient reports difficulty breathing for two days", "shortness of breath", "two days")
        ]
        
        for text, canonical_symptom, expected_duration in synonym_cases:
            with self.subTest(text=text):
                normalized = self.normalizer.normalize(text)
                res = self.extractor.extract(normalized)
                self.assertEqual(len(res["symptoms"]), 1)
                self.assertEqual(res["symptoms"][0].name, canonical_symptom)
                if expected_duration:
                    self.assertEqual(res["symptoms"][0].duration, expected_duration)

    def test_speaker_aware_filtering(self):
        # UPGRADE: Verify that clinician questions are ignored, while clinician observations are preserved
        
        # Scenario A: Clinician asks a question -> Ignored entirely
        doctor_question = {
            "session_id": "session-1",
            "speaker_id": "doctor",
            "transcript": "Do you have any chest pain?",
            "timestamp": 10.0
        }
        res_doc_q = self.pipeline.process(doctor_question)
        self.assertEqual(res_doc_q.speaker_id, "doctor")
        self.assertEqual(len(res_doc_q.symptoms), 0)  # Correctly ignored doctor question!

        # Scenario B: Clinician makes an observation/diagnosis -> Preserved
        doctor_statement = {
            "session_id": "session-1",
            "speaker_id": "doctor",
            "transcript": "Based on the report, you have hypertension.",
            "timestamp": 11.0
        }
        res_doc_s = self.pipeline.process(doctor_statement)
        self.assertEqual(res_doc_s.speaker_id, "doctor")
        self.assertEqual(len(res_doc_s.diagnoses), 1)
        self.assertEqual(res_doc_s.diagnoses[0].name, "hypertension")
        self.assertTrue(res_doc_s.diagnoses[0].present)

        # Scenario C: Patient reports symptom -> Preserved
        patient_data = {
            "session_id": "session-1",
            "speaker_id": "patient",
            "transcript": "No chest pain, but I have a mild cough.",
            "timestamp": 12.0
        }
        res_pat = self.pipeline.process(patient_data)
        self.assertEqual(res_pat.speaker_id, "patient")
        self.assertEqual(len(res_pat.symptoms), 2)
        
        chest_pain_pat = next(s for s in res_pat.symptoms if s.name == "chest pain")
        self.assertFalse(chest_pain_pat.present)  # Patient negated it
        
        cough_pat = next(s for s in res_pat.symptoms if s.name == "cough")
        self.assertTrue(cough_pat.present)
        self.assertEqual(cough_pat.severity, "mild")

    def test_advanced_negation_edge_cases(self):
        # UPGRADE: Verify long-range negation and double negation cancellation
        # A: Long-range negation ("absolutely does not currently have")
        text_long = "The patient absolutely does not currently have fever."
        res_long = self.extractor.extract(text_long)
        self.assertEqual(len(res_long["symptoms"]), 1)
        self.assertEqual(res_long["symptoms"][0].name, "fever")
        self.assertFalse(res_long["symptoms"][0].present)  # Successfully caught by full-prefix scan

        # B: Double negation ("was not ruled out" -> present = True)
        text_double = "Fever was not ruled out today."
        res_double = self.extractor.extract(text_double)
        self.assertEqual(len(res_double["symptoms"]), 1)
        self.assertEqual(res_double["symptoms"][0].name, "fever")
        self.assertTrue(res_double["symptoms"][0].present)  # Double negation canceled negation!

    def test_rich_duration_detection(self):
        # UPGRADE: Verify advanced generic duration patterns
        durations_cases = [
            ("I have had a cough for years", "years"),
            ("Fever has been present for about a month", "about a month"),
            ("Headache active since Monday", "Monday"),
            ("Shortness of breath for several weeks", "several weeks"),
            ("Chest pain active for 3-4 days", "3-4 days")
        ]
        for text, expected_duration in durations_cases:
            with self.subTest(text=text):
                res = self.extractor.extract(text)
                self.assertEqual(len(res["symptoms"]), 1)
                self.assertEqual(res["symptoms"][0].duration, expected_duration)

    def test_expanded_severities(self):
        # UPGRADE: Verify new severities (excruciating, slight, minimal, very severe)
        severity_cases = [
            ("I have excruciating headache", "excruciating"),
            ("Slight dizziness reported", "slight"),
            ("Minimal cough present", "minimal"),
            ("Very severe chest pain", "very severe")
        ]
        for text, expected_severity in severity_cases:
            with self.subTest(text=text):
                res = self.extractor.extract(text)
                self.assertEqual(len(res["symptoms"]), 1)
                self.assertEqual(res["symptoms"][0].severity, expected_severity)

    def test_entity_deduplication_and_consolidation(self):
        # UPGRADE: Verify that multiple mentions of the same entity in an utterance are consolidated
        text = "I have a cough. The cough has been very severe for two weeks."
        res = self.extractor.extract(text)
        
        # Should merge into a single cough entity with combined severity, duration, and positive present status
        self.assertEqual(len(res["symptoms"]), 1)
        self.assertEqual(res["symptoms"][0].name, "cough")
        self.assertEqual(res["symptoms"][0].severity, "very severe")
        self.assertEqual(res["symptoms"][0].duration, "two weeks")
        self.assertTrue(res["symptoms"][0].present)

    def test_risk_factor_extraction(self):
        # ARCHITECTURE BOX 4: Risk Factor Extractor
        text = "The patient has a history of smoking, but has stopped drinking alcohol."
        res = self.extractor.extract(text)
        
        self.assertEqual(len(res["risk_factors"]), 2)
        
        smoking = next(r for r in res["risk_factors"] if r.name == "smoking")
        self.assertTrue(smoking.present)
        
        alcohol = next(r for r in res["risk_factors"] if r.name == "alcohol")
        self.assertFalse(alcohol.present)  # "stopped drinking" is negated

    def test_family_history_extraction(self):
        # ARCHITECTURE BOX 4: Family History Extractor
        text = "Father has diabetes and there is no family history of cancer."
        res = self.extractor.extract(text)
        
        self.assertEqual(len(res["family_histories"]), 2)
        
        diabetes_history = next(f for f in res["family_histories"] if f.condition == "diabetes")
        self.assertEqual(diabetes_history.relationship, "father")
        self.assertTrue(diabetes_history.present)
        
        cancer_history = next(f for f in res["family_histories"] if f.condition == "cancer")
        self.assertEqual(cancer_history.relationship, "family")
        self.assertFalse(cancer_history.present)  # "no family history" is negated

    def test_user_reported_bugs(self):
        # Bug #2, #3, #4: Clinician questions should not generate findings
        # Do you have a fever? (speaker_id="doctor") -> Should be ignored/empty
        res1 = self.pipeline.process({
            "session_id": "test-session",
            "speaker_id": "doctor",
            "transcript": "Do you have a fever?",
            "timestamp": 0.0
        })
        self.assertEqual(len(res1.symptoms), 0)
        self.assertEqual(res1.speaker_id, "doctor")

        # Any nausea or vomiting? (speaker_id="doctor") -> Should be ignored/empty
        res2 = self.pipeline.process({
            "session_id": "test-session",
            "speaker_id": "doctor",
            "transcript": "Any nausea or vomiting?",
            "timestamp": 0.0
        })
        self.assertEqual(len(res2.symptoms), 0)
        self.assertEqual(res2.speaker_id, "doctor")

        # Do you have high blood pressure? (speaker_id="doctor") -> Should be ignored/empty
        res3 = self.pipeline.process({
            "session_id": "test-session",
            "speaker_id": "doctor",
            "transcript": "Do you have high blood pressure?",
            "timestamp": 0.0
        })
        self.assertEqual(len(res3.diagnoses), 0)
        self.assertEqual(res3.speaker_id, "doctor")

        # Bug #5: Vomiting negation missed
        # "Yes, I feel nauseous, but I haven't vomited." (speaker_id="patient")
        # should extract: nausea (present=True), vomiting (present=False)
        res4 = self.pipeline.process({
            "session_id": "test-session",
            "speaker_id": "patient",
            "transcript": "Yes, I feel nauseous, but I haven't vomited.",
            "timestamp": 0.0
        })
        self.assertEqual(len(res4.symptoms), 2)
        nausea = next(s for s in res4.symptoms if s.name == "nausea")
        self.assertTrue(nausea.present)
        
        vomiting = next(s for s in res4.symptoms if s.name == "vomiting")
        self.assertFalse(vomiting.present)

    def test_user_reported_next_scenarios(self):
        # 1. More negation variants
        text_neg1 = "I have no fever."
        res_neg1 = self.extractor.extract(text_neg1)
        self.assertEqual(len(res_neg1["symptoms"]), 1)
        self.assertEqual(res_neg1["symptoms"][0].name, "fever")
        self.assertFalse(res_neg1["symptoms"][0].present)

        text_neg2 = "Never had chest pain."
        res_neg2 = self.extractor.extract(text_neg2)
        self.assertEqual(len(res_neg2["symptoms"]), 1)
        self.assertEqual(res_neg2["symptoms"][0].name, "chest pain")
        self.assertFalse(res_neg2["symptoms"][0].present)

        text_neg3 = "I deny shortness of breath."
        res_neg3 = self.extractor.extract(text_neg3)
        self.assertEqual(len(res_neg3["symptoms"]), 1)
        self.assertEqual(res_neg3["symptoms"][0].name, "shortness of breath")
        self.assertFalse(res_neg3["symptoms"][0].present)

        text_neg4 = "No nausea or vomiting."
        normalized = self.normalizer.normalize(text_neg4)
        res_neg4 = self.extractor.extract(normalized)
        self.assertEqual(len(res_neg4["symptoms"]), 2)
        nausea = next(s for s in res_neg4["symptoms"] if s.name == "nausea")
        self.assertFalse(nausea.present)
        vomiting = next(s for s in res_neg4["symptoms"] if s.name == "vomiting")
        self.assertFalse(vomiting.present)

        # 2. Multiple symptoms in one sentence
        text_multi = "I have headache, fever, and dizziness."
        normalized_multi = self.normalizer.normalize(text_multi)
        res_multi = self.extractor.extract(normalized_multi)
        self.assertEqual(len(res_multi["symptoms"]), 3)
        self.assertTrue(all(s.present for s in res_multi["symptoms"]))

        # 3. Mixed positive/negative sentence
        text_mixed = "I have headache but no fever."
        res_mixed = self.extractor.extract(text_mixed)
        self.assertEqual(len(res_mixed["symptoms"]), 2)
        headache = next(s for s in res_mixed["symptoms"] if s.name == "headache")
        self.assertTrue(headache.present)
        fever = next(s for s in res_mixed["symptoms"] if s.name == "fever")
        self.assertFalse(fever.present)

        # 4. Duration attachment with plurals
        text_duration = "I've had headaches for three weeks and fever since yesterday."
        normalized_dur = self.normalizer.normalize(text_duration)
        res_duration = self.extractor.extract(normalized_dur)
        self.assertEqual(len(res_duration["symptoms"]), 2)
        
        headache_ent = next(s for s in res_duration["symptoms"] if s.name == "headache")
        self.assertEqual(headache_ent.duration, "three weeks")
        self.assertTrue(headache_ent.present)
        
        fever_ent = next(s for s in res_duration["symptoms"] if s.name == "fever")
        self.assertEqual(fever_ent.duration, "yesterday")
        self.assertTrue(fever_ent.present)

        # 5. Medication negation
        text_med = "I am not taking paracetamol anymore."
        res_med = self.extractor.extract(text_med)
        self.assertEqual(len(res_med["medications"]), 1)
        self.assertEqual(res_med["medications"][0].name, "paracetamol")
        self.assertFalse(res_med["medications"][0].present)
