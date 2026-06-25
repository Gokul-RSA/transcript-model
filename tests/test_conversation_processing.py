import unittest
from app.services.conversation.filler_remover import FillerRemover
from app.services.conversation.utterance_merger import UtteranceMerger
from app.services.conversation.terminology_normalizer import ClinicalTerminologyNormalizer
from app.services.conversation.conversation_processor import ConversationProcessor

class TestConversationProcessing(unittest.TestCase):
    def setUp(self):
        self.processor = ConversationProcessor(max_completed_utterances=100)
        self.filler_remover = FillerRemover()
        self.merger = UtteranceMerger(max_completed_utterances=100)
        self.normalizer = ClinicalTerminologyNormalizer()

    def test_filler_word_removal(self):
        # 1. Verification requirement: "Uh doctor I have um fever" becomes "doctor I have fever"
        input_text = "Uh doctor I have um fever"
        expected = "doctor I have fever"
        self.assertEqual(self.filler_remover.clean(input_text), expected)

        # Additional complex case with capitalization and punctuation
        # "like" and "actually" are preserved because they have clinical significance
        input_complex = "Uh Doctor, I actually have um sort of like, kind of, er, severe headaches."
        expected_complex = "Doctor, I actually have like, severe headaches."
        self.assertEqual(self.filler_remover.clean(input_complex), expected_complex)

    def test_clinical_like_preservation(self):
        # Verifies that "like" is not removed when expressing clinical comparisons
        input_text = "The patient reports a pain like a burning sensation."
        expected = "The patient reports a pain like a burning sensation."
        self.assertEqual(self.filler_remover.clean(input_text), expected)

    def test_clinical_conversational_fillers(self):
        # Verifies that "mm-hmm" and "uh-huh" are cleanly removed as fillers
        input_text = "Uh-huh, tell me more about that. Mm-hmm."
        expected = "tell me more about that."
        self.assertEqual(self.filler_remover.clean(input_text), expected)

    def test_utterance_merging(self):
        # 2. Verification requirement:
        # doctor: "I have"
        # doctor: "severe headaches"
        # merges into "I have severe headaches"
        session_id = "session-1"

        # Adding first segment (active)
        res1 = self.merger.add(session_id, "doctor", "I have", is_final=True, timestamp=100.0)
        self.assertIsNone(res1)  # Stays active, nothing completed yet

        # Adding second segment (same speaker, gap <= 2s)
        # Should merge and still return None because it is still active
        res2 = self.merger.add(session_id, "doctor", "severe headaches", is_final=True, timestamp=101.5)
        self.assertIsNone(res2)

        # Trigger completion by changing speaker
        res3 = self.merger.add(session_id, "patient", "How long?", is_final=True, timestamp=103.0)
        self.assertIsNotNone(res3)
        self.assertEqual(res3["speaker_id"], "doctor")
        self.assertEqual(res3["transcript"], "I have severe headaches")
        self.assertEqual(res3["timestamp"], 100.0)
        self.assertEqual(res3["end_timestamp"], 101.5)

    def test_no_merge_different_speaker(self):
        # 3. Verification requirement:
        # doctor: "I have headache"
        # patient: "How long?"
        # must NOT merge.
        session_id = "session-2"

        res1 = self.merger.add(session_id, "doctor", "I have headache", is_final=True, timestamp=200.0)
        self.assertIsNone(res1)

        res2 = self.merger.add(session_id, "patient", "How long?", is_final=True, timestamp=201.0)
        # Since speaker changed, the first speaker's block should be completed and returned
        self.assertIsNotNone(res2)
        self.assertEqual(res2["speaker_id"], "doctor")
        self.assertEqual(res2["transcript"], "I have headache")
        self.assertEqual(res2["timestamp"], 200.0)
        self.assertEqual(res2["end_timestamp"], 200.0)

    def test_no_merge_large_time_gap(self):
        # Same speaker, but time gap > 2s must NOT merge
        session_id = "session-3"

        res1 = self.merger.add(session_id, "doctor", "I have a cold", is_final=True, timestamp=300.0)
        self.assertIsNone(res1)

        # Adding same speaker, but time gap is 2.5 seconds (> 2s)
        res2 = self.merger.add(session_id, "doctor", "also a fever", is_final=True, timestamp=302.5)
        # This should complete the first one due to time gap
        self.assertIsNotNone(res2)
        self.assertEqual(res2["speaker_id"], "doctor")
        self.assertEqual(res2["transcript"], "I have a cold")
        self.assertEqual(res2["timestamp"], 300.0)
        self.assertEqual(res2["end_timestamp"], 300.0)

    def test_terminology_normalization_case_preservation(self):
        # 4. Verification requirement: "high blood pressure" becomes "hypertension"
        self.assertEqual(self.normalizer.normalize("high blood pressure"), "hypertension")

        # Test preservation of case:
        self.assertEqual(self.normalizer.normalize("High blood pressure"), "Hypertension")
        self.assertEqual(self.normalizer.normalize("High Blood Pressure"), "Hypertension")
        self.assertEqual(self.normalizer.normalize("HIGH BLOOD PRESSURE"), "HYPERTENSION")

        # Test regular expression boundaries (should not match inside other words)
        self.assertEqual(
            self.normalizer.normalize("The patient is on high blood pressure medications."),
            "The patient is on hypertension medications."
        )

    def test_processor_pipeline_integration(self):
        # Checks the pipeline order and correctness:
        # text -> FillerRemover -> UtteranceMerger -> TerminologyNormalizer
        # We test if layman terms split across merge boundaries normalize correctly
        session_id = "session-pipeline"

        # Word 1 of layman term: "high blood"
        self.assertIsNone(
            self.processor.process(session_id, "doctor", "Uh I actually have high blood", is_final=True, timestamp=10.0)
        )
        # Word 2 of layman term: "pressure"
        self.assertIsNone(
            self.processor.process(session_id, "doctor", "pressure", is_final=True, timestamp=11.0)
        )
        # We change speaker to trigger completion of doctor block
        completed = self.processor.process(session_id, "patient", "Okay.", is_final=True, timestamp=11.5)

        self.assertIsNotNone(completed)
        self.assertEqual(completed["speaker_id"], "doctor")
        # Notice:
        # 1. Fillers removed: "Uh"
        # 2. Capitalization and important descriptors preserved: "actually"
        # 3. Merged: "I actually have high blood" + "pressure" -> "I actually have high blood pressure"
        # 4. Normalized: "high blood pressure" -> "hypertension"
        self.assertEqual(completed["transcript"], "I actually have hypertension")

        # 5. Check new metadata fields
        self.assertEqual(completed["raw_text"], "Uh I actually have high blood pressure")
        self.assertEqual(completed["cleaned_text"], "I actually have high blood pressure")
        self.assertEqual(completed["normalized_text"], "I actually have hypertension")
        self.assertEqual(completed["timestamp"], 10.0)
        self.assertEqual(completed["end_timestamp"], 11.0)

    def test_memory_leak_prevention_pop_completed(self):
        # Verifies that pop_completed clears memory buffers
        session_id = "session-leak"

        # Populate merger
        self.merger.add(session_id, "doctor", "Hello", is_final=True, timestamp=10.0)
        self.merger.add(session_id, "patient", "World", is_final=True, timestamp=11.0)

        # The first utterance is completed because speaker changed
        completed = self.merger.pop_completed(session_id)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["transcript"], "Hello")

        # A second pop should be empty since it was cleared
        self.assertEqual(len(self.merger.pop_completed(session_id)), 0)

    def test_clear_session(self):
        session_id = "session-to-clear"
        self.processor.process(session_id, "doctor", "fever", is_final=True, timestamp=10.0)
        self.processor.process(session_id, "patient", "cough", is_final=True, timestamp=11.0)

        # Active buffers should contain data before clear
        self.assertTrue(len(self.processor.merger.active_utterances) > 0)
        self.assertTrue(len(self.processor.merger.completed_utterances) > 0)

        # Clear session
        self.processor.clear_session(session_id)

        # Active buffers for this session should be empty
        self.assertNotIn(session_id, self.processor.merger.active_utterances)
        self.assertNotIn(session_id, self.processor.merger.completed_utterances)

    def test_bounded_completed_utterances_deque(self):
        session_id = "session-bounded-deque"
        # We add 110 completed utterances to a session. 
        # Since speaker changes trigger completion, we alternate speakers.
        for i in range(110):
            speaker = "doctor" if (i % 2 == 0) else "patient"
            self.merger.add(session_id, speaker, f"word {i}", is_final=True, timestamp=float(i))

        # The size of completed list returned by pop_completed should be capped at 100.
        completed = self.merger.pop_completed(session_id)
        self.assertEqual(len(completed), 100)
        # The first item popped should be index 9 (since 0-8 were discarded)
        self.assertEqual(completed[0]["transcript"], "word 9")

    def test_concurrent_add_same_session(self):
        import threading
        session_id = "concurrent-session"
        num_threads = 10
        num_items_per_thread = 50

        # Spawn threads that concurrently add items to the merger
        def worker(thread_idx):
            for i in range(num_items_per_thread):
                speaker = "doctor" if (thread_idx % 2 == 0) else "patient"
                timestamp = float(thread_idx * num_items_per_thread + i) * 5.0
                self.merger.add(
                    session_id=session_id,
                    speaker_id=speaker,
                    transcript=f"Thread {thread_idx} utterance {i}",
                    is_final=True,
                    timestamp=timestamp
                )

        threads = []
        for t in range(num_threads):
            thread = threading.Thread(target=worker, args=(t,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Flush any remaining active utterance to make sure everything completes
        self.merger.flush(session_id)

        # Retrieve completed utterances. We check that no exceptions occurred.
        completed = self.merger.pop_completed(session_id)
        # Since max_completed_utterances is 100, the list should be capped at 100
        self.assertEqual(len(completed), 100)
        for block in completed:
            self.assertEqual(block["session_id"], session_id)
            self.assertIn(block["speaker_id"], ["doctor", "patient"])

if __name__ == "__main__":
    unittest.main()
