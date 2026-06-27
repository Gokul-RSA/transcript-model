import unittest
from app.services.providers.models import TranscriptEvent
from app.services.clinical import clinical_state_engine

class TestClinicalStateEngine(unittest.TestCase):
    def setUp(self):
        # Clear state
        clinical_state_engine.clear_state("test-session-123")

    def tearDown(self):
        clinical_state_engine.clear_state("test-session-123")

    def test_incremental_state_building(self):
        session_id = "test-session-123"

        # Turn 1: Patient introduces age and gender
        event1 = TranscriptEvent(
            session_id=session_id,
            sequence_number=1,
            role="patient",
            speaker_id="patient",
            transcript="Hello doctor, I'm a 39 yo male.",
            is_final=True,
            is_partial=False,
            event_id="e1",
            timestamp=100.0,
            start_time=0.0,
            end_time=2.0
        )
        state = clinical_state_engine.update_state_from_event(event1)
        self.assertEqual(state.patient_info.age, 39)
        self.assertEqual(state.patient_info.gender, "Male")

        # Turn 2: Patient reports headache
        event2 = TranscriptEvent(
            session_id=session_id,
            sequence_number=2,
            role="patient",
            speaker_id="patient",
            transcript="I came in for a headache.",
            is_final=True,
            is_partial=False,
            event_id="e2",
            timestamp=102.0,
            start_time=2.0,
            end_time=5.0
        )
        state = clinical_state_engine.update_state_from_event(event2)
        self.assertEqual(state.chief_complaint, ["headache"])
        self.assertEqual(len(state.symptoms), 1)
        self.assertEqual(state.symptoms[0]["name"], "headache")

        # Turn 3: Patient specifies duration of headache
        event3 = TranscriptEvent(
            session_id=session_id,
            sequence_number=3,
            role="patient",
            speaker_id="patient",
            transcript="I've had it for about two weeks.",
            is_final=True,
            is_partial=False,
            event_id="e3",
            timestamp=104.0,
            start_time=5.0,
            end_time=8.0
        )
        state = clinical_state_engine.update_state_from_event(event3)
        self.assertEqual(state.duration, "two weeks")
        self.assertEqual(state.symptoms[0]["duration"], "two weeks")

        # Turn 4: Doctor asks a question (should be ignored by extractor)
        event4 = TranscriptEvent(
            session_id=session_id,
            sequence_number=4,
            role="doctor",
            speaker_id="doctor",
            transcript="Do you have a fever?",
            is_final=True,
            is_partial=False,
            event_id="e4",
            timestamp=106.0,
            start_time=8.0,
            end_time=10.0
        )
        state = clinical_state_engine.update_state_from_event(event4)
        self.assertNotIn("fever", [s["name"] for s in state.symptoms])

        # Turn 5: Patient denies fever
        event5 = TranscriptEvent(
            session_id=session_id,
            sequence_number=5,
            role="patient",
            speaker_id="patient",
            transcript="No, I don't have a fever.",
            is_final=True,
            is_partial=False,
            event_id="e5",
            timestamp=108.0,
            start_time=10.0,
            end_time=12.0
        )
        state = clinical_state_engine.update_state_from_event(event5)
        # Fever is added but with status="Negated" and present="False"
        fever_sym = next((s for s in state.symptoms if s["name"] == "fever"), None)
        self.assertIsNotNone(fever_sym)
        self.assertEqual(fever_sym["status"], "Negated")
        self.assertEqual(fever_sym["present"], "False")

        # Turn 6: Patient reports history of high blood pressure and amlodipine
        event6 = TranscriptEvent(
            session_id=session_id,
            sequence_number=6,
            role="patient",
            speaker_id="patient",
            transcript="I was diagnosed with high blood pressure three years ago, and I take amlodipine daily.",
            is_final=True,
            is_partial=False,
            event_id="e6",
            timestamp=110.0,
            start_time=12.0,
            end_time=16.0
        )
        state = clinical_state_engine.update_state_from_event(event6)
        self.assertIn("Hypertension", state.medical_history)
        self.assertIn("Amlodipine", state.current_medications)

        # Turn 7: Doctor prescribes medication and advice
        event7 = TranscriptEvent(
            session_id=session_id,
            sequence_number=7,
            role="doctor",
            speaker_id="doctor",
            transcript="You should take paracetamol 650 mg twice daily. Also stay well hydrated.",
            is_final=True,
            is_partial=False,
            event_id="e7",
            timestamp=112.0,
            start_time=16.0,
            end_time=20.0
        )
        state = clinical_state_engine.update_state_from_event(event7)
        self.assertEqual(len(state.treatment_plan.medicines), 1)
        self.assertEqual(state.treatment_plan.medicines[0]["name"], "Paracetamol")
        self.assertEqual(state.treatment_plan.medicines[0]["dosage"], "650 mg")
        self.assertEqual(state.treatment_plan.medicines[0]["frequency"], "Twice daily")
        self.assertIn("Stay well hydrated", state.treatment_plan.advice)

        # Turn 8: Doctor suggests investigations and follow-up
        event8 = TranscriptEvent(
            session_id=session_id,
            sequence_number=8,
            role="doctor",
            speaker_id="doctor",
            transcript="I will order some blood tests. We will review them at your follow-up appointment next week.",
            is_final=True,
            is_partial=False,
            event_id="e8",
            timestamp=114.0,
            start_time=20.0,
            end_time=24.0
        )
        state = clinical_state_engine.update_state_from_event(event8)
        self.assertIn("Blood test", state.treatment_plan.investigations)
        self.assertEqual(len(state.follow_up), 1)
        self.assertIn("We will review them at your follow-up appointment next week.", state.follow_up[0])

    def test_contradiction_resolution_and_state_evolution(self):
        session_id = "test-session-123"

        # 1. Assert fever is active
        e1 = TranscriptEvent(
            session_id=session_id, sequence_number=1, role="patient", speaker_id="patient",
            transcript="I have a fever.", is_final=True, is_partial=False, event_id="ev1", timestamp=100.0
        )
        state = clinical_state_engine.update_state_from_event(e1)
        fever_sym = next((s for s in state.symptoms if s["name"] == "fever"), None)
        self.assertEqual(fever_sym["status"], "Active")
        self.assertEqual(fever_sym["present"], "True")

        # 2. Contradiction: resolved
        e2 = TranscriptEvent(
            session_id=session_id, sequence_number=2, role="patient", speaker_id="patient",
            transcript="The fever has gone now.", is_final=True, is_partial=False, event_id="ev2", timestamp=102.0
        )
        state = clinical_state_engine.update_state_from_event(e2)
        fever_sym = next((s for s in state.symptoms if s["name"] == "fever"), None)
        self.assertEqual(fever_sym["status"], "Resolved")
        self.assertEqual(fever_sym["present"], "False")

        # 3. Assert return: active again
        e3 = TranscriptEvent(
            session_id=session_id, sequence_number=3, role="patient", speaker_id="patient",
            transcript="Actually my fever returned yesterday.", is_final=True, is_partial=False, event_id="ev3", timestamp=104.0
        )
        state = clinical_state_engine.update_state_from_event(e3)
        fever_sym = next((s for s in state.symptoms if s["name"] == "fever"), None)
        self.assertEqual(fever_sym["status"], "Active")
        self.assertEqual(fever_sym["present"], "True")

        # 4. Negate medical history diabetes
        state.medical_history.append("Diabetes")
        e4 = TranscriptEvent(
            session_id=session_id, sequence_number=4, role="patient", speaker_id="patient",
            transcript="I don't have diabetes.", is_final=True, is_partial=False, event_id="ev4", timestamp=106.0
        )
        state = clinical_state_engine.update_state_from_event(e4)
        self.assertNotIn("Diabetes", state.medical_history)

    def test_medication_parsing_enhancements(self):
        session_id = "test-session-123"

        # Prescribe rich medication details
        e1 = TranscriptEvent(
            session_id=session_id, sequence_number=1, role="doctor", speaker_id="doctor",
            transcript="Take paracetamol 650 mg twice daily after meals for five days by mouth.",
            is_final=True, is_partial=False, event_id="ev1", timestamp=100.0
        )
        state = clinical_state_engine.update_state_from_event(e1)
        med = state.treatment_plan.medicines[0]
        self.assertEqual(med["name"], "Paracetamol")
        self.assertEqual(med["dosage"], "650 mg")
        self.assertEqual(med["frequency"], "Twice daily")
        self.assertEqual(med["duration"], "five days")
        self.assertEqual(med["route"], "By mouth")
        self.assertEqual(med["instructions"], "After meals")
        self.assertEqual(med["prn"], "False")

        # Prescribe PRN
        e2 = TranscriptEvent(
            session_id=session_id, sequence_number=2, role="doctor", speaker_id="doctor",
            transcript="You can also take ibuprofen 400 mg as needed for pain.",
            is_final=True, is_partial=False, event_id="ev2", timestamp=102.0
        )
        state = clinical_state_engine.update_state_from_event(e2)
        med2 = next(m for m in state.treatment_plan.medicines if m["name"] == "Ibuprofen")
        self.assertEqual(med2["dosage"], "400 mg")
        self.assertEqual(med2["prn"], "True")

    def test_symptom_normalization(self):
        session_id = "test-session-123"

        # Check headache normalization
        e1 = TranscriptEvent(
            session_id=session_id, sequence_number=1, role="patient", speaker_id="patient",
            transcript="I am having head pain.", is_final=True, is_partial=False, event_id="ev1", timestamp=100.0
        )
        state = clinical_state_engine.update_state_from_event(e1)
        self.assertEqual(state.symptoms[0]["name"], "headache")

        # Check chest pain normalization
        e2 = TranscriptEvent(
            session_id=session_id, sequence_number=2, role="patient", speaker_id="patient",
            transcript="I have some pain in my chest.", is_final=True, is_partial=False, event_id="ev2", timestamp=102.0
        )
        state = clinical_state_engine.update_state_from_event(e2)
        chest_sym = next(s for s in state.symptoms if s["name"] == "chest pain")
        self.assertEqual(chest_sym["present"], "True")

        # Check honorific name extraction
        e3 = TranscriptEvent(
            session_id=session_id, sequence_number=3, role="doctor", speaker_id="doctor",
            transcript="Good morning, Mr. Johnson.", is_final=True, is_partial=False, event_id="ev3", timestamp=104.0
        )
        state = clinical_state_engine.update_state_from_event(e3)
        self.assertEqual(state.patient_info.patient_name, "Mr. Johnson")

    def test_conversational_context_proximity_association(self):
        session_id = "test-session-123"

        # Multi-symptom proximity association
        e1 = TranscriptEvent(
            session_id=session_id, sequence_number=1, role="patient", speaker_id="patient",
            transcript="I have a severe headache and vomiting for three days.",
            is_final=True, is_partial=False, event_id="ev1", timestamp=100.0
        )
        state = clinical_state_engine.update_state_from_event(e1)
        
        headache = next(s for s in state.symptoms if s["name"] == "headache")
        vomiting = next(s for s in state.symptoms if s["name"] == "vomiting")
        
        # headache should be severe, vomiting should have duration 3 days
        self.assertEqual(headache["severity"], "severe")
        self.assertEqual(vomiting["duration"], "three days")

        # Modifier without symptom
        e2 = TranscriptEvent(
            session_id=session_id, sequence_number=2, role="patient", speaker_id="patient",
            transcript="Actually, it is moderate.", is_final=True, is_partial=False, event_id="ev2", timestamp=102.0
        )
        state = clinical_state_engine.update_state_from_event(e2)
        # Moderate should update the last active symptom context (vomiting)
        vomiting = next(s for s in state.symptoms if s["name"] == "vomiting")
        self.assertEqual(vomiting["severity"], "moderate")

    def test_fact_provenance_and_versioning(self):
        session_id = "test-session-123"

        e1 = TranscriptEvent(
            session_id=session_id, sequence_number=1, role="patient", speaker_id="patient",
            transcript="Hello, my name is John.", is_final=True, is_partial=False, event_id="ev1", timestamp=100.0
        )
        state = clinical_state_engine.update_state_from_event(e1)
        self.assertEqual(state.version, 2) # Increments on state changes (initialized at 1, changed by Turn 1)
        
        prov = clinical_state_engine.get_provenance(session_id)
        self.assertIn("patient_info.patient_name", prov)
        self.assertEqual(prov["patient_info.patient_name"]["event_id"], "ev1")
        self.assertEqual(prov["patient_info.patient_name"]["transcript"], "Hello, my name is John.")

    def test_llm_trigger_readiness_checks(self):
        session_id = "test-session-123"

        # Check initial readiness
        self.assertFalse(clinical_state_engine.ready_for_llm(session_id))
        self.assertEqual(clinical_state_engine.pending_updates_count(session_id), 0)

        # 1. New Diagnosis should trigger ready
        e1 = TranscriptEvent(
            session_id=session_id, sequence_number=1, role="patient", speaker_id="patient",
            transcript="I came in for diabetes check.", is_final=True, is_partial=False, event_id="ev1", timestamp=100.0
        )
        state = clinical_state_engine.update_state_from_event(e1)
        self.assertTrue(clinical_state_engine.has_significant_state_change(session_id))
        self.assertEqual(clinical_state_engine.significant_change_reason(session_id), "New Diagnosis")
        self.assertTrue(clinical_state_engine.ready_for_llm(session_id))

if __name__ == "__main__":
    unittest.main()
