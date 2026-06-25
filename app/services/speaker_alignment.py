# =====================================================================
# SPEAKER ALIGNMENT LAYER (app/services/speaker_alignment.py)
# =====================================================================
# Purpose: Maps transcripts/timestamps to speakers and retroactively
#          enriches cached events in-place.
# =====================================================================

import uuid
import time
from typing import List
from app.services.providers.models import TranscriptEvent
from app.services.speaker_timeline import speaker_timeline_manager
from app.utils.logging import logger

class SpeakerAlignmentService:
    def __init__(self):
        self._committed_cache = {}
        self._in_realignment = False

    def align_and_segment(self, session_id: str, role: str, res: dict, provider) -> List[TranscriptEvent]:
        """
        Maps ElevenLabs Scribe transcript output words to the SpeakerTimeline.
        Groups contiguous speaker segments at the sentence level, assigns monotonic
        sequence numbers, and generates a list of TranscriptEvents.
        """
        import re
        from app.services.session import session_manager
        
        session = session_manager.get_session(session_id)
        timeline = speaker_timeline_manager.get_timeline(session_id)
        
        is_partial = (res.get("type") == "partial")
        
        # Cache raw committed responses for global re-alignment
        if not is_partial and res.get("type") == "committed" and not getattr(self, "_in_realignment", False):
            if session_id not in self._committed_cache:
                self._committed_cache[session_id] = []
            if res not in [x[1] for x in self._committed_cache[session_id]]:
                self._committed_cache[session_id].append((role, res, provider))
        text = res.get("text", "")
        confidence = res.get("confidence")
        words = res.get("words", [])
        
        # 1. Handle Partial Transcripts: return as a single event mapped to the active speaker in the last 3 seconds
        if is_partial:
            # Estimate current audio time based on total bytes processed
            if session and session.streams.get(role):
                current_time = session.streams.get(role).buffer.total_bytes_received / 32000.0
            else:
                from app.services.diarization_worker import diarization_worker_manager
                state = diarization_worker_manager._states.get(session_id)
                current_time = (state.total_bytes_received / 32000.0) if state else 0.0
                    
            start_time = max(0.0, current_time - 3.0)
            end_time = current_time
            speaker = timeline.get_speaker_for_range(start_time, end_time)
            
            seq = session.get_and_increment_transcript_seq(role) if session else (provider.get_and_increment_event_seq() if provider else 0)
            
            event = TranscriptEvent(
                session_id=session_id,
                role=role,
                sequence_number=seq,
                timestamp=time.time(),
                transcript=text,
                is_partial=True,
                is_final=False,
                confidence=confidence,
                provider="scribe_v2",
                event_id=str(uuid.uuid4()),
                speaker_id=speaker,
                speaker_label=speaker,
                start_time=start_time,
                end_time=end_time,
                text=text
            )
            return [event]

        # 2. Committed/Final transcripts: Segment by sentence and align to speaker timeline
        sentences_data = []  # List of tuples: (sentence_text, start_time, end_time, speaker)
        
        if words:
            # Group words into sentences based on punctuation (. ? !)
            current_sent_words = []
            for w in words:
                current_sent_words.append(w)
                w_text = w.get("text", "").strip()
                if w_text and w_text[-1] in ('.', '?', '!'):
                    # Finalize sentence
                    s_text = "".join(x.get("text", "") for x in current_sent_words).strip()
                    if s_text:
                        # Find the true boundaries of the sentence by looking at all valid word timestamps
                        valid_starts = [x.get("start") for x in current_sent_words if x.get("start") is not None and x.get("start") > 0.001]
                        valid_ends = [x.get("end") for x in current_sent_words if x.get("end") is not None and x.get("end") > 0.001]
                        s_start = min(valid_starts) if valid_starts else (current_sent_words[0].get("start", 0.0) if current_sent_words[0].get("start") is not None else 0.0)
                        s_end = max(valid_ends) if valid_ends else (current_sent_words[-1].get("end", 0.0) if current_sent_words[-1].get("end") is not None else 0.0)
                        
                        speaker = timeline.get_speaker_for_range(s_start, s_end)
                        sentences_data.append((s_text, s_start, s_end, speaker))
                    current_sent_words = []
            if current_sent_words:
                s_text = "".join(x.get("text", "") for x in current_sent_words).strip()
                if s_text:
                    # Find the true boundaries of the sentence by looking at all valid word timestamps
                    valid_starts = [x.get("start") for x in current_sent_words if x.get("start") is not None and x.get("start") > 0.001]
                    valid_ends = [x.get("end") for x in current_sent_words if x.get("end") is not None and x.get("end") > 0.001]
                    s_start = min(valid_starts) if valid_starts else (current_sent_words[0].get("start", 0.0) if current_sent_words[0].get("start") is not None else 0.0)
                    s_end = max(valid_ends) if valid_ends else (current_sent_words[-1].get("end", 0.0) if current_sent_words[-1].get("end") is not None else 0.0)
                    
                    speaker = timeline.get_speaker_for_range(s_start, s_end)
                    sentences_data.append((s_text, s_start, s_end, speaker))
        else:
            # Fallback when words is empty/not present: split by regex and estimate time range
            sentence_texts = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
            
            if sentence_texts:
                # Estimate current audio time
                if session and session.streams.get(role):
                    current_time = session.streams.get(role).buffer.total_bytes_received / 32000.0
                else:
                    from app.services.diarization_worker import diarization_worker_manager
                    state = diarization_worker_manager._states.get(session_id)
                    current_time = (state.total_bytes_received / 32000.0) if state else 0.0
                
                # Estimate total duration based on 15 characters per second
                duration = len(text) / 15.0
                start_time = max(0.0, current_time - duration)
                end_time = current_time
                total_len = max(1, len(text))
                
                curr_start = start_time
                for s_text in sentence_texts:
                    s_dur = (len(s_text) / total_len) * (end_time - start_time)
                    s_end = curr_start + s_dur
                    speaker = timeline.get_speaker_for_range(curr_start, s_end)
                    sentences_data.append((s_text, curr_start, s_end, speaker))
                    curr_start = s_end

        # Group contiguous sentences belonging to the same speaker
        groups = []
        if sentences_data:
            curr_speaker = sentences_data[0][3]
            curr_texts = [sentences_data[0][0]]
            curr_start = sentences_data[0][1]
            curr_end = sentences_data[0][2]
            
            for s_text, s_start, s_end, speaker in sentences_data[1:]:
                if speaker == curr_speaker:
                    curr_texts.append(s_text)
                    curr_end = s_end
                else:
                    groups.append((curr_speaker, curr_texts, curr_start, curr_end))
                    curr_speaker = speaker
                    curr_texts = [s_text]
                    curr_start = s_start
                    curr_end = s_end
            groups.append((curr_speaker, curr_texts, curr_start, curr_end))

        # Create a TranscriptEvent for each grouped segment
        events = []
        for speaker, g_texts, g_start, g_end in groups:
            group_text = " ".join(g_texts).strip()
            # Clean up double spaces if they occur during joins
            group_text = re.sub(r'\s+', ' ', group_text)
            if not group_text:
                continue
                
            seq = session.get_and_increment_transcript_seq(role) if session else (provider.get_and_increment_event_seq() if provider else 0)
            
            event = TranscriptEvent(
                session_id=session_id,
                role=role,
                sequence_number=seq,
                timestamp=time.time(),
                transcript=group_text,
                is_partial=False,
                is_final=True,
                confidence=confidence,
                provider="scribe_v2",
                event_id=str(uuid.uuid4()),
                speaker_id=speaker,
                speaker_label=speaker,
                start_time=g_start,
                end_time=g_end,
                text=group_text
            )
            events.append(event)
            
        return events

    def realign_session(self, session_id: str) -> None:
        """
        Re-aligns and re-segments all cached committed STT responses for a session
        using the final correct SpeakerTimeline, and updates the TranscriptEventBus.
        """
        if session_id not in self._committed_cache:
            logger.info("SpeakerAlignmentService: No cached committed responses for session", extra={"session_id": session_id})
            return
            
        logger.info(
            "SpeakerAlignmentService: Starting global re-alignment for session",
            extra={"session_id": session_id, "cached_count": len(self._committed_cache[session_id])}
        )
        
        # 1. Clear all existing final events for this session in the TranscriptEventBus
        from app.services.transcript_bus import transcript_bus
        transcript_bus.clear_buffer(session_id)
        
        # 2. Reset the session sequence counter so the sequence numbers are perfectly monotonic and start from 0
        from app.services.session import session_manager
        session = session_manager.get_session(session_id)
        if session:
            for r in ["doctor", "patient", "attender"]:
                session.transcript_seq_counters[r] = 0
                
        # 3. Temporarily disable caching in align_and_segment during the re-alignment pass
        self._in_realignment = True
        try:
            for role, res, provider in self._committed_cache[session_id]:
                events = self.align_and_segment(session_id, role, res, provider)
                for event in events:
                    transcript_bus.publish(event)
        finally:
            self._in_realignment = False

    def enrich_cached_events(self, session_id: str) -> None:
        """
        Scans the cached events in the TranscriptEventBus and retroactively
        resolves 'UNKNOWN' speaker labels based on the updated SpeakerTimeline.
        Updates the events in-place, preserving event_id and sequence_number.
        """
        from app.services.transcript_bus import transcript_bus
        
        timeline = speaker_timeline_manager.get_timeline(session_id)
        recent_events = transcript_bus.get_recent_events(session_id)
        
        for event in recent_events:
            # Enrich completed events that have an UNKNOWN speaker
            if event.is_final and event.speaker_id == "UNKNOWN":
                if event.start_time is not None and event.end_time is not None:
                    resolved = timeline.get_speaker_for_range(event.start_time, event.end_time)
                    if resolved != "UNKNOWN":
                        event.speaker_id = resolved
                        event.speaker_label = resolved
                        event.version += 1
                        event.updated_at = time.time()
                        logger.info(

                            "SpeakerAlignmentService: Retroactively enriched speaker label",
                            extra={
                                "session_id": session_id,
                                "event_id": event.event_id,
                                "seq": event.sequence_number,
                                "speaker": resolved,
                                "text": event.text
                            }
                        )

# Singleton Instance
speaker_alignment_service = SpeakerAlignmentService()
