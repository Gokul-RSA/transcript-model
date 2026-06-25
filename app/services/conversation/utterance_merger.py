from typing import Dict, List, Optional
from threading import RLock
from collections import deque

class UtteranceMerger:
    def __init__(self, max_completed_utterances: int = 1000):
        # Maps session_id -> active utterance dict
        self.active_utterances: Dict[str, dict] = {}
        # Maps session_id -> deque of completed utterance dicts (bounded to max_completed_utterances to prevent leaks)
        self.completed_utterances: Dict[str, deque] = {}
        self.max_completed_utterances = max_completed_utterances
        # Lock to ensure thread safety across concurrent requests
        self._lock = RLock()

    def add(
        self,
        session_id: str,
        speaker_id: str,
        transcript: str,
        is_final: bool,
        timestamp: float,
        raw_transcript: Optional[str] = None
    ) -> Optional[dict]:
        """
        Processes a new utterance. Merges it with the active utterance if the speaker
        is the same and the time gap is <= 2.0 seconds. Otherwise, finalizes the previous
        utterance, starts a new one, and returns the finalized utterance.

        Note: Conversation Processing consumes committed transcripts only.
        Partial transcripts are intentionally ignored to avoid duplicate merges 
        and corrections.
        """
        # IMPORTANT:
        # This merger assumes cumulative partial transcripts are ignored.
        # Feeding partial transcripts may create duplicated text.
        if not is_final:
            return None

        # Clean transcript to handle blank inputs
        transcript = transcript.strip()
        if not transcript:
            return None

        # Fallback raw transcript
        raw_text = raw_transcript.strip() if raw_transcript else transcript

        with self._lock:
            active = self.active_utterances.get(session_id)
            if active:
                # Check if same speaker and time gap <= 2.0 seconds
                if active["speaker_id"] == speaker_id and (timestamp - active["last_timestamp"]) <= 2.0:
                    # Merge the transcript text
                    active["transcript"] = (active["transcript"] + " " + transcript).strip()
                    active["raw_text"] = (active["raw_text"] + " " + raw_text).strip()
                    active["end_timestamp"] = timestamp
                    active["last_timestamp"] = timestamp
                    return None
                else:
                    # Different speaker or time gap > 2.0 seconds -> complete the active one
                    completed = {
                        "session_id": session_id,
                        "speaker_id": active["speaker_id"],
                        "transcript": active["transcript"],
                        "raw_text": active["raw_text"],
                        "timestamp": active["timestamp"],  # start timestamp
                        "end_timestamp": active["end_timestamp"]
                    }
                    if session_id not in self.completed_utterances:
                        self.completed_utterances[session_id] = deque(maxlen=self.max_completed_utterances)
                    self.completed_utterances[session_id].append(completed)

                    # Start a new active utterance
                    self.active_utterances[session_id] = {
                        "speaker_id": speaker_id,
                        "transcript": transcript,
                        "raw_text": raw_text,
                        "timestamp": timestamp,
                        "end_timestamp": timestamp,
                        "last_timestamp": timestamp
                    }
                    return completed
            else:
                # No active utterance, start one
                self.active_utterances[session_id] = {
                    "speaker_id": speaker_id,
                    "transcript": transcript,
                    "raw_text": raw_text,
                    "timestamp": timestamp,
                    "end_timestamp": timestamp,
                    "last_timestamp": timestamp
                }
                return None

    def flush(self, session_id: str) -> Optional[dict]:
        """
        Forces finalization of the current active utterance for the session.
        Useful when a stream terminates.
        """
        with self._lock:
            active = self.active_utterances.pop(session_id, None)
            if active:
                completed = {
                    "session_id": session_id,
                    "speaker_id": active["speaker_id"],
                    "transcript": active["transcript"],
                    "raw_text": active["raw_text"],
                    "timestamp": active["timestamp"],
                    "end_timestamp": active["end_timestamp"]
                }
                if session_id not in self.completed_utterances:
                    self.completed_utterances[session_id] = deque(maxlen=self.max_completed_utterances)
                self.completed_utterances[session_id].append(completed)
                return completed
            return None

    def pop_completed(self, session_id: Optional[str] = None) -> List[dict]:
        """
        Returns and clears (pops) all completed utterances to prevent memory leaks.
        Can be filtered by session_id.
        """
        with self._lock:
            if session_id is not None:
                completed_deque = self.completed_utterances.pop(session_id, None)
                return list(completed_deque) if completed_deque else []
            else:
                all_completed = []
                for sid in list(self.completed_utterances.keys()):
                    completed_deque = self.completed_utterances.pop(sid, None)
                    if completed_deque:
                        all_completed.extend(list(completed_deque))
                return all_completed

    def clear_session(self, session_id: str) -> None:
        """
        Removes all buffers associated with session_id to prevent memory growth.
        """
        with self._lock:
            self.active_utterances.pop(session_id, None)
            self.completed_utterances.pop(session_id, None)
