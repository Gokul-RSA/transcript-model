# =====================================================================
# TRANSCRIPT EVENT BUS (app/services/transcript_bus.py)
# =====================================================================
# Purpose: Routes transcription events to subscribers and caches recent
#          transcripts per session in-memory.
#
# Recent Modifications:
# 1. Added `threading.RLock()` synchronization to make it thread-safe.
#    Since methods like publish(), get_recent_events(), and clear_buffer()
#    are synchronous and invoked from various concurrent context handlers,
#    using RLock protects the internal data structures without needing
#    complex async wrappers or monkey-patching.
# 2. Configurable buffer size using `settings.TRANSCRIPT_BUFFER_SIZE`
#    instead of a hardcoded value of 100.
# =====================================================================

import asyncio
from typing import List, Dict, Callable
from collections import deque
from threading import RLock
from app.utils.logging import logger
from app.services.providers.models import TranscriptEvent
from app.core.config import settings

class TranscriptEventBus:
    """
    In-memory publication/subscription event bus for routing TranscriptEvents
    to downstream processing engines (e.g. Conversation Normalizer, Clinical State Engine).
    """
    def __init__(self):
        self._subscribers: List[Callable[[TranscriptEvent], None]] = []
        # Sliding buffer mapping session_id -> deque of recent events (caches last N events)
        self._buffers: Dict[str, deque] = {}
        self._max_buffer_size = settings.TRANSCRIPT_BUFFER_SIZE
        # Set of seen event keys to prevent duplicates: session_id -> set of (role, sequence_number, transcript, is_final)
        self._seen_events: Dict[str, set] = {}
        # Lock to ensure thread safety across concurrent FastAPI/uvicorn requests
        self._lock = RLock()

    def subscribe(self, callback: Callable[[TranscriptEvent], None]) -> None:
        """Registers a new listener callback."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[TranscriptEvent], None]) -> None:
        """Unregisters an existing listener callback."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def publish(self, event: TranscriptEvent) -> None:
        """
        Thread-safely caches the incoming transcript event in the session's sliding buffer,
        and broadcasts it to all registered subscribers.
        """
        # Skip publishing empty final transcripts (silence)
        if event.is_final and (not event.transcript or event.transcript.strip() == ""):
            return

        with self._lock:
            session_id = event.session_id
            event_key = (event.role, event.sequence_number, event.transcript, event.is_final)

            if session_id not in self._seen_events:
                self._seen_events[session_id] = set()
                
            if event_key in self._seen_events[session_id]:
                logger.debug(
                    "Skipping duplicate transcript event",
                    extra={"session_id": session_id, "role": event.role, "seq": event.sequence_number, "final": event.is_final}
                )
                return
                
            self._seen_events[session_id].add(event_key)
            
            # Cache event in session buffer
            if session_id not in self._buffers:
                self._buffers[session_id] = deque(maxlen=self._max_buffer_size)
                
            # Overlap replacement logic: if this is a final event, remove any older overlapping events
            if event.is_final and event.start_time is not None and event.end_time is not None:
                overlapping_events = []
                for old_event in self._buffers[session_id]:
                    if old_event.start_time is not None and old_event.end_time is not None:
                        overlap_start = max(old_event.start_time, event.start_time)
                        overlap_end = min(old_event.end_time, event.end_time)
                        if (overlap_end - overlap_start) > 0.1:
                            overlapping_events.append(old_event)
                for old_event in overlapping_events:
                    try:
                        self._buffers[session_id].remove(old_event)
                        logger.info(
                            "Removed overlapping transcript event from buffer",
                            extra={
                                "session_id": session_id,
                                "removed_seq": old_event.sequence_number,
                                "removed_text": old_event.transcript,
                                "new_seq": event.sequence_number,
                                "new_text": event.transcript
                            }
                        )
                    except ValueError:
                        pass  # Already removed

            self._buffers[session_id].append(event)
            
            # Broadcast to all registered callback subscribers
            for callback in self._subscribers:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(event))
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(
                        "Error invoking transcript subscriber callback",
                        exc_info=True,
                        extra={"session_id": session_id, "error": str(e)}
                    )

    def get_recent_events(self, session_id: str) -> List[TranscriptEvent]:
        """Thread-safely retrieves all currently buffered transcript events for a given session, sorted chronologically."""
        with self._lock:
            if session_id in self._buffers:
                events_list = list(self._buffers[session_id])
                # Sort chronologically by start_time to guarantee perfect dialogue sequence
                events_list.sort(key=lambda x: x.start_time if x.start_time is not None else 0.0)
                return events_list
            return []

    def clear_buffer(self, session_id: str) -> None:
        """Thread-safely deletes the buffered transcript events cache for a completed session."""
        with self._lock:
            if session_id in self._buffers:
                del self._buffers[session_id]
            if session_id in self._seen_events:
                del self._seen_events[session_id]


# Singleton Event Bus
transcript_bus = TranscriptEventBus()
