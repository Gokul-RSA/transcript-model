import sys
import unittest
from app.services.speaker_timeline import SpeakerTimeline
from app.services.providers.models import TranscriptEvent

class TestSpeakerDiarization(unittest.TestCase):
    def setUp(self):
        self.timeline = SpeakerTimeline("test-session")

    def test_scenario_1_doctor_only(self):
        """Scenario 1: Doctor only. Expect all segments to match doctor."""
        self.timeline.segments = [
            {"start": 0.0, "end": 10.0, "label": "doctor"},
            {"start": 10.0, "end": 20.0, "label": "doctor"}
        ]
        
        # Word lookup check
        self.assertEqual(self.timeline.get_speaker_for_range(2.0, 3.0), "doctor")
        self.assertEqual(self.timeline.get_speaker_for_range(12.0, 14.0), "doctor")

    def test_scenario_2_doctor_patient_alternating(self):
        """Scenario 2: Doctor -> Patient -> Doctor -> Patient (doctor -> patient -> doctor -> patient)."""
        self.timeline.segments = [
            {"start": 0.0, "end": 5.0, "label": "doctor"},
            {"start": 5.0, "end": 10.0, "label": "patient"},
            {"start": 10.0, "end": 15.0, "label": "doctor"},
            {"start": 15.0, "end": 20.0, "label": "patient"}
        ]
        
        self.assertEqual(self.timeline.get_speaker_for_range(2.0, 3.0), "doctor")
        self.assertEqual(self.timeline.get_speaker_for_range(7.0, 8.0), "patient")
        self.assertEqual(self.timeline.get_speaker_for_range(11.0, 12.0), "doctor")
        self.assertEqual(self.timeline.get_speaker_for_range(16.0, 18.0), "patient")

    def test_scenario_3_three_speakers(self):
        """Scenario 3: Doctor -> Patient -> Attender -> Doctor -> Attender."""
        self.timeline.segments = [
            {"start": 0.0, "end": 5.0, "label": "doctor"},
            {"start": 5.0, "end": 10.0, "label": "patient"},
            {"start": 10.0, "end": 15.0, "label": "attender"},
            {"start": 15.0, "end": 20.0, "label": "doctor"},
            {"start": 20.0, "end": 25.0, "label": "attender"}
        ]
        
        self.assertEqual(self.timeline.get_speaker_for_range(2.0, 4.0), "doctor")
        self.assertEqual(self.timeline.get_speaker_for_range(6.0, 8.0), "patient")
        self.assertEqual(self.timeline.get_speaker_for_range(12.0, 14.0), "attender")
        self.assertEqual(self.timeline.get_speaker_for_range(16.0, 18.0), "doctor")
        self.assertEqual(self.timeline.get_speaker_for_range(22.0, 24.0), "attender")

    def test_scenario_4_interruptions_and_overlaps(self):
        """
        Scenario 4: Interruptions and overlapping speech regions.
        Doctor speaks [0, 5], Patient interrupts at [4, 6] (overlap region),
        Doctor continues [6, 10], Attender joins late at [9, 12].
        """
        self.timeline.segments = [
            {"start": 0.0, "end": 5.0, "label": "doctor"},
            {"start": 4.0, "end": 6.0, "label": "patient"},
            {"start": 6.0, "end": 10.0, "label": "doctor"},
            {"start": 9.0, "end": 12.0, "label": "attender"}
        ]
        
        # Word lookup checks
        # Word 1: [1.0, 2.0] -> only overlaps Doctor [0, 5] -> doctor
        self.assertEqual(self.timeline.get_speaker_for_range(1.0, 2.0), "doctor")
        
        # Word 2: [5.2, 5.8] -> inside Patient's segment, overlaps Patient [4, 6]
        self.assertEqual(self.timeline.get_speaker_for_range(5.2, 5.8), "patient")
        
        # Word 3: [9.5, 10.5] -> overlaps doctor [6, 10] by 0.5s, attender [9, 12] by 1.0s.
        # attender has larger overlap -> attender
        self.assertEqual(self.timeline.get_speaker_for_range(9.5, 10.5), "attender")

    def test_priority_1_maximum_overlap(self):
        """Priority 1: Maximum overlap duration wins."""
        self.timeline.segments = [
            {"start": 0.0, "end": 4.0, "label": "doctor"},
            {"start": 3.0, "end": 7.0, "label": "patient"}
        ]
        # Range [2.5, 4.5] overlaps doctor by 1.5s, patient by 1.0s.
        # doctor wins.
        self.assertEqual(self.timeline.get_speaker_for_range(2.5, 4.5), "doctor")
        
        # Range [3.5, 6.5] overlaps doctor by 0.5s, patient by 2.5s.
        # patient wins.
        self.assertEqual(self.timeline.get_speaker_for_range(3.5, 6.5), "patient")

    def test_priority_2_proximity(self):
        """Priority 2: If overlap is 0, choose speaker closest in time."""
        self.timeline.segments = [
            {"start": 0.0, "end": 2.0, "label": "doctor"},
            {"start": 6.0, "end": 8.0, "label": "patient"}
        ]
        # Range [3.0, 4.0] is at distance 1.0 from doctor (3 - 2), and distance 2.0 from patient (6 - 4).
        # doctor is closer -> doctor.
        self.assertEqual(self.timeline.get_speaker_for_range(3.0, 4.0), "doctor")
        
        # Range [4.5, 5.5] is at distance 2.5 from doctor (4.5 - 2), and distance 0.5 from patient (6 - 5.5).
        # patient is closer -> patient.
        self.assertEqual(self.timeline.get_speaker_for_range(4.5, 5.5), "patient")

    def test_priority_3_continuity_tie_breaker(self):
        """Priority 3: Continuity tie-breaker (ended most recently before current start)."""
        self.timeline.segments = [
            {"start": 0.0, "end": 2.0, "label": "doctor"}, # ended at 2.0
            {"start": 4.0, "end": 6.0, "label": "patient"}  # starts at 4.0
        ]
        # Range [3.0, 3.0] (point in time) is at distance 1.0 from doctor (3.0 - 2.0 = 1.0),
        # and distance 1.0 from patient (4.0 - 3.0 = 1.0).
        # Distance is tied!
        # Continuity tie-breaker: Choose speaker whose segment ended most recently before 3.0.
        # doctor ended at 2.0 (<= 3.0).
        # patient ended at 6.0 (not <= 3.0).
        # So doctor wins!
        self.assertEqual(self.timeline.get_speaker_for_range(3.0, 3.0), "doctor")

    def test_priority_4_hard_cap(self):
        """Priority 4: Speaker cap logic ensures only doctor, patient, or attender are returned."""
        self.timeline.segments = [
            {"start": 0.0, "end": 5.0, "label": "doctor"},
            {"start": 5.0, "end": 10.0, "label": "Speaker_3"}, # invalid label
            {"start": 10.0, "end": 15.0, "label": "patient"}
        ]
        # Query in Speaker_3 range [6.0, 7.0] -> Speaker_3 is ignored.
        # Proximity maps to doctor (distance 1.0: 6 - 5) or patient (distance 3.0: 10 - 7).
        # doctor is closer -> doctor.
        self.assertEqual(self.timeline.get_speaker_for_range(6.0, 7.0), "doctor")

    def test_event_enrichment_versioning(self):
        """Verify that retroactive event enrichment increments version and sets updated_at."""
        from app.services.speaker_alignment import speaker_alignment_service
        from app.services.transcript_bus import transcript_bus
        from app.services.speaker_timeline import speaker_timeline_manager
        import time

        session_id = "test-session-version"
        # Register timeline in singleton manager
        speaker_timeline_manager._timelines[session_id] = self.timeline
        self.timeline.segments = [
            {"start": 0.0, "end": 5.0, "label": "patient"}
        ]

        event = TranscriptEvent(
            session_id=session_id,
            role="doctor",
            sequence_number=1,
            timestamp=time.time(),
            transcript="Hello",
            is_partial=False,
            is_final=True,
            event_id="test-uuid-123",
            speaker_id="UNKNOWN",
            speaker_label="UNKNOWN",
            start_time=1.0,
            end_time=3.0,
            text="Hello"
        )
        
        # Publish to cache in the bus
        transcript_bus.publish(event)
        
        # Initial checks
        self.assertEqual(event.version, 1)
        self.assertIsNone(event.updated_at)
        
        # Trigger enrichment
        speaker_alignment_service.enrich_cached_events(session_id)
        
        # Verify version and timestamp updates
        self.assertEqual(event.speaker_id, "patient")
        self.assertEqual(event.version, 2)
        self.assertIsNotNone(event.updated_at)

    def test_sentence_level_alignment_with_words(self):
        """Verify that committed transcripts are segmented and aligned at the sentence level when words are present."""
        from app.services.speaker_alignment import speaker_alignment_service
        from app.services.speaker_timeline import speaker_timeline_manager
        
        session_id = "test-sentence-words"
        timeline = speaker_timeline_manager.get_timeline(session_id)
        timeline.segments = [
            {"start": 0.0, "end": 2.0, "label": "doctor"},
            {"start": 2.0, "end": 5.0, "label": "patient"}
        ]
        
        res = {
            "type": "committed",
            "text": "Good morning. I have an appointment.",
            "confidence": 0.98,
            "words": [
                {"text": "Good", "start": 0.1, "end": 0.5},
                {"text": " morning.", "start": 0.5, "end": 1.0},
                {"text": " I", "start": 2.1, "end": 2.3},
                {"text": " have", "start": 2.3, "end": 2.6},
                {"text": " an", "start": 2.6, "end": 2.8},
                {"text": " appointment.", "start": 2.8, "end": 3.5}
            ]
        }
        
        events = speaker_alignment_service.align_and_segment(session_id, "doctor", res, None)
        
        # We expect 2 events:
        # Event 1: "Good morning." mapped to doctor
        # Event 2: "I have an appointment." mapped to patient
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].transcript, "Good morning.")
        self.assertEqual(events[0].speaker_id, "doctor")
        self.assertEqual(events[0].is_final, True)
        
        self.assertEqual(events[1].transcript, "I have an appointment.")
        self.assertEqual(events[1].speaker_id, "patient")
        self.assertEqual(events[1].is_final, True)

    def test_sentence_level_alignment_fallback(self):
        """Verify that sentence alignment falls back gracefully when words are missing, using proportional estimation."""
        from app.services.speaker_alignment import speaker_alignment_service
        from app.services.speaker_timeline import speaker_timeline_manager
        
        session_id = "test-sentence-fallback"
        timeline = speaker_timeline_manager.get_timeline(session_id)
        timeline.segments = [
            {"start": 0.0, "end": 5.0, "label": "doctor"},
            {"start": 5.0, "end": 10.0, "label": "patient"}
        ]
        
        # Simulate stream data by injecting DiarizationSessionState directly
        from app.services.diarization_worker import diarization_worker_manager, DiarizationSessionState
        state = DiarizationSessionState(session_id)
        state.total_bytes_received = 320000  # 10.0 seconds of audio (32000 bytes/sec)
        diarization_worker_manager._states[session_id] = state
        
        res = {
            "type": "committed",
            "text": "Hello doctor. I have a fever.",
            "confidence": 0.95,
            "words": []
        }
        
        events = speaker_alignment_service.align_and_segment(session_id, "doctor", res, None)
        
        # Text length is 29 characters.
        # "Hello doctor." is 13 characters.
        # "I have a fever." is 15 characters.
        # Total duration is 29/15.0 = 1.93 seconds.
        # start_time = 10.0 - 1.93 = 8.07 seconds.
        # Hello doctor starts at 8.07, ends at 8.07 + (13/29)*1.93 = 8.93 seconds -> mapped to patient.
        # I have a fever starts at 8.93, ends at 10.0 -> mapped to patient.
        # Since they are both patient, they should be grouped into a single event:
        # "Hello doctor. I have a fever."
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].transcript, "Hello doctor. I have a fever.")
        self.assertEqual(events[0].speaker_id, "patient")

if __name__ == "__main__":
    unittest.main()