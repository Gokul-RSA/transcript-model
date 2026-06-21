# =====================================================================
# BACKGROUND DIARIZATION WORKER (app/services/diarization_worker.py)
# =====================================================================
# Purpose: Periodically runs Speaker Diarization on the sliding audio window,
#          performs greedy overlap matching, and updates SpeakerTimeline.
# =====================================================================

import asyncio
import io
import wave
import time
import threading
import collections
from typing import Dict, List, Optional
from app.core.config import settings
from app.utils.logging import logger
from app.services.speaker_timeline import speaker_timeline_manager

# Lazy imports for production dependencies
torch = None
Pipeline = None

def _lazy_init_pyannote():
    global torch, Pipeline
    if torch is None or Pipeline is None:
        try:
            import torch as t
            from pyannote.audio import Pipeline as P
            torch = t
            Pipeline = P
        except ImportError as e:
            logger.error("DiarizationWorker: Failed to import torch/pyannote.audio", exc_info=True)
            raise ImportError(
                "Failed to import 'torch' or 'pyannote.audio'. "
                "Ensure they are installed before using production diarization mode."
            ) from e

def pcm_to_wav_io(pcm_bytes: bytes, sample_rate: int = 16000) -> io.BytesIO:
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit = 2 bytes
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    wav_io.seek(0)
    return wav_io

def get_mock_speaker(timestamp: float) -> str:
    cycle = timestamp % 30.0
    if cycle < 5.0:
        return "Speaker_0"
    elif cycle < 12.0:
        return "Speaker_1"
    elif cycle < 18.0:
        return "Speaker_0"
    elif cycle < 22.0:
        return "Speaker_2"
    else:
        return "Speaker_0"

def get_mock_segments(window_start: float, window_end: float) -> list:
    segments = []
    step = 0.1
    current_speaker = None
    segment_start = None
    
    t = window_start
    while t < window_end + 0.05:
        current_t = min(t, window_end)
        speaker = get_mock_speaker(current_t)
        
        if current_speaker is None:
            current_speaker = speaker
            segment_start = current_t
        elif speaker != current_speaker:
            segments.append({
                "start": segment_start,
                "end": current_t,
                "label": current_speaker
            })
            current_speaker = speaker
            segment_start = current_t
            
        t += step
        
    if current_speaker is not None and segment_start < window_end:
        segments.append({
            "start": segment_start,
            "end": window_end,
            "label": current_speaker
        })
    return segments


class DiarizationSessionState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        # Double-ended queue storing chunks of audio bytes dynamically
        self.chunks_deque = collections.deque()
        self.total_bytes_in_chunks = 0
        self.total_bytes_received = 0
        self.lock = asyncio.Lock()
        self.task: Optional[asyncio.Task] = None
        self.is_active = True
        self.prev_window_start = 0.0
        self.prev_window_end = 0.0
        self.has_new_audio = False


class DiarizationWorkerManager:
    """
    Manages active diarization sessions and handles Pyannote pipeline initialization.
    
    Locking Hierarchy & Concurrency Model:
    1. Manager Lock (self._lock - threading.Lock):
       - Purpose: Protects CPU-bound, synchronous state dict operations (fetching, clearing, or creating session states).
       - Constraints: Never held across `await` points or nested within any other lock. Released immediately.
    2. Session Lock (state.lock - asyncio.Lock):
       - Purpose: Protects concurrent window processing for a specific session to prevent race conditions during sliding window analysis.
       - Constraints: Held across `asyncio.to_thread` calls during pipeline execution.
    """
    def __init__(self):
        self._states: Dict[str, DiarizationSessionState] = {}
        self._lock = threading.Lock()
        self._pipeline = None


    def feed_audio(self, session_id: str, chunk: bytes) -> None:
        """Appends audio bytes and triggers/wakes the background processing loop."""
        with self._lock:
            if session_id not in self._states:
                logger.info("DiarizationWorker: Creating new session state", extra={"session_id": session_id})
                self._states[session_id] = DiarizationSessionState(session_id)
            state = self._states[session_id]

        state.chunks_deque.append(chunk)
        state.total_bytes_in_chunks += len(chunk)
        state.total_bytes_received += len(chunk)
        state.has_new_audio = True
        
        # Bounded sliding buffer: discard chunks older than 7 seconds (constant memory O(1))
        bytes_per_second = settings.AUDIO_SAMPLE_RATE * settings.AUDIO_CHANNELS * settings.bytes_per_sample
        max_bytes = 7 * bytes_per_second
        while state.total_bytes_in_chunks > max_bytes:
            oldest = state.chunks_deque.popleft()
            state.total_bytes_in_chunks -= len(oldest)

        # Start background loop if not already running
        if state.task is None or state.task.done():
            state.task = asyncio.create_task(self._run_loop(session_id))

    async def stop_worker(self, session_id: str) -> None:
        """Signals background loop to stop gracefully, processes final audio, and cleans up."""
        state = None
        with self._lock:
            state = self._states.get(session_id)
            
        if state:
            logger.info("DiarizationWorker: Stopping worker loop", extra={"session_id": session_id})
            state.is_active = False
            if state.task:
                try:
                    await state.task
                except Exception as e:
                    logger.error("DiarizationWorker: Error waiting for worker task exit", exc_info=True, extra={"session_id": session_id})
            
            try:
                await self._process_latest_window(session_id, force=True)
            except Exception as e:
                logger.error("DiarizationWorker: Error during final window diarization", exc_info=True, extra={"session_id": session_id})

    def clear_session(self, session_id: str) -> None:
        """Clears in-memory session buffer states to avoid leaks."""
        with self._lock:
            if session_id in self._states:
                del self._states[session_id]
                logger.info("DiarizationWorker: Session state cleared", extra={"session_id": session_id})

    async def _run_loop(self, session_id: str) -> None:
        """Background loop executing diarization periodically."""
        logger.info("DiarizationWorker: Worker loop started", extra={"session_id": session_id})
        state = None
        with self._lock:
            state = self._states.get(session_id)
            
        if not state:
            return

        step_interval = 2.0
        try:
            while state.is_active:
                await asyncio.sleep(step_interval)
                if state.has_new_audio:
                    state.has_new_audio = False
                    await self._process_latest_window(session_id)
        except asyncio.CancelledError:
            logger.debug("DiarizationWorker: Loop task cancelled", extra={"session_id": session_id})
        except Exception as e:
            logger.error("DiarizationWorker: Exception in worker loop", exc_info=True, extra={"session_id": session_id})
        finally:
            logger.info("DiarizationWorker: Worker loop stopped", extra={"session_id": session_id})

    async def _process_latest_window(self, session_id: str, force: bool = False) -> None:
        """Extracts the latest 5-second window of audio, runs Pyannote, and updates SpeakerTimeline."""
        state = None
        with self._lock:
            state = self._states.get(session_id)
            
        if not state:
            return

        async with state.lock:
            audio_bytes = b"".join(state.chunks_deque)
            total_bytes = state.total_bytes_received
            
            bytes_per_second = settings.AUDIO_SAMPLE_RATE * settings.AUDIO_CHANNELS * settings.bytes_per_sample
            total_seconds = total_bytes / float(bytes_per_second)
            
            window_size = 5.0
            window_start = max(0.0, total_seconds - window_size)
            window_end = total_seconds
            
            if not force and (window_end - window_start < 1.0):
                return
                
            if not force and (window_end - state.prev_window_end < 0.5):
                return
                
            # Map absolute window_start and window_end to current local audio_bytes offsets
            audio_data_start_time = max(0.0, (state.total_bytes_received - len(audio_bytes)) / float(bytes_per_second))
            start_offset_sec = window_start - audio_data_start_time
            end_offset_sec = window_end - audio_data_start_time
            
            start_byte = int(start_offset_sec * bytes_per_second)
            end_byte = int(end_offset_sec * bytes_per_second)
            
            start_byte = max(0, min(start_byte, len(audio_bytes)))
            end_byte = max(0, min(end_byte, len(audio_bytes)))
            
            # Align boundaries to 2-byte sample blocks (16-bit)
            start_byte = (start_byte // 2) * 2
            end_byte = (end_byte // 2) * 2
            
            window_audio = audio_bytes[start_byte:end_byte]
            
            try:
                if settings.DIARIZATION_MODE == "development" or not settings.HUGGINGFACE_TOKEN:
                    local_segments = await asyncio.to_thread(
                        get_mock_segments, window_start, window_end
                    )
                else:
                    local_segments = await asyncio.to_thread(
                        self._run_pyannote_pipeline, window_audio, window_start
                    )
            except Exception as e:
                logger.error(
                    "DiarizationWorker: Diarization execution failed",
                    exc_info=True,
                    extra={"session_id": session_id, "error": str(e)}
                )
                return

            # Perform Greedy Conflict-Free Bipartite Overlap Matching
            timeline = speaker_timeline_manager.get_timeline(session_id)
            global_timeline = timeline.segments
            
            overlap_start = window_start
            overlap_end = state.prev_window_end
            
            unique_local = list(set(seg["label"] for seg in local_segments))
            mapping = {}
            
            if overlap_start < overlap_end and global_timeline:
                triples = []
                for loc in unique_local:
                    for glob_seg in global_timeline:
                        for loc_seg in local_segments:
                            if loc_seg["label"] != loc:
                                continue
                                
                            # Calculate intersection in the overlap region
                            int_start = max(loc_seg["start"], glob_seg["start"], overlap_start)
                            int_end = min(loc_seg["end"], glob_seg["end"], overlap_end)
                            duration = int_end - int_start
                            if duration > 0.05:
                                triples.append((loc, glob_seg["label"], duration))
                                
                # Aggregate durations
                aggregated = {}
                for loc, glob, dur in triples:
                    key = (loc, glob)
                    aggregated[key] = aggregated.get(key, 0.0) + dur
                    
                # Sort descending
                sorted_pairs = sorted(aggregated.items(), key=lambda x: x[1], reverse=True)
                
                # Greedy assignment
                claimed_global = set()
                for (loc, glob), dur in sorted_pairs:
                    if loc not in mapping and glob not in claimed_global:
                        mapping[loc] = glob
                        claimed_global.add(glob)
                        
            # Map unmapped local labels
            allowed_labels = ["Speaker_0", "Speaker_1", "Speaker_2"]
            allocated_labels = set(mapping.values())
            timeline_labels = set(seg["label"] for seg in global_timeline)
            used_labels = allocated_labels.union(timeline_labels)
            
            for loc in unique_local:
                if loc not in mapping:
                    # Find unused allowed labels
                    unused_allowed = [lbl for lbl in allowed_labels if lbl not in used_labels]
                    if unused_allowed:
                        mapped_label = unused_allowed[0]
                        mapping[loc] = mapped_label
                        used_labels.add(mapped_label)
                    else:
                        # Hard Speaker Cap Fallback (Priority mapping)
                        mapped_label = self._map_unmapped_to_existing(loc, local_segments, global_timeline)
                        mapping[loc] = mapped_label
                        
                        logger.warning(
                            "Exceeded maximum speaker cap",
                            extra={
                                "session_id": session_id,
                                "window_start": window_start,
                                "window_end": window_end,
                                "local_label": loc,
                                "mapped_to": mapped_label
                            }
                        )
                    
            # Apply mapping and convert local to global segments
            mapped_segments = []
            for loc_seg in local_segments:
                mapped_segments.append({
                    "start": loc_seg["start"],
                    "end": loc_seg["end"],
                    "label": mapping[loc_seg["label"]]
                })
                
            # Update global timeline
            timeline.update_timeline(mapped_segments, window_start)
            
            state.prev_window_start = window_start
            state.prev_window_end = window_end
            
            # Retroactively enrich any cached "UNKNOWN" events in the TranscriptEventBus
            try:
                from app.services.speaker_alignment import speaker_alignment_service
                speaker_alignment_service.enrich_cached_events(session_id)
            except Exception as e:
                logger.error(
                    "DiarizationWorker: Error trigger event enrichment",
                    exc_info=True,
                    extra={"session_id": session_id, "error": str(e)}
                )

    def _map_unmapped_to_existing(self, loc: str, local_segments: list, global_timeline: list) -> str:
        """
        Fallback matching logic when all 3 global speaker slots are occupied.
        Priority:
        1. Greatest overlap duration
        2. Proximity closest in time
        3. Continuity (ended most recently before current segments start)
        """
        allowed = ["Speaker_0", "Speaker_1", "Speaker_2"]
        
        # 1. Overlap duration calculation
        overlaps = {lbl: 0.0 for lbl in allowed}
        for loc_seg in local_segments:
            if loc_seg["label"] != loc:
                continue
            for glob_seg in global_timeline:
                if glob_seg["label"] not in allowed:
                    continue
                int_start = max(loc_seg["start"], glob_seg["start"])
                int_end = min(loc_seg["end"], glob_seg["end"])
                dur = int_end - int_start
                if dur > 0:
                    overlaps[glob_seg["label"]] += dur
                    
        best_overlap_speaker = max(overlaps, key=overlaps.get)
        if overlaps[best_overlap_speaker] > 0.01:
            return best_overlap_speaker
            
        # 2. Proximity calculation
        proximity = {lbl: float("inf") for lbl in allowed}
        loc_segs_for_lbl = [s for s in local_segments if s["label"] == loc]
        
        for loc_seg in loc_segs_for_lbl:
            for glob_seg in global_timeline:
                if glob_seg["label"] not in allowed:
                    continue
                dist = min(abs(loc_seg["start"] - glob_seg["end"]), abs(loc_seg["end"] - glob_seg["start"]))
                proximity[glob_seg["label"]] = min(proximity[glob_seg["label"]], dist)
                
        min_dist = min(proximity.values())
        if min_dist != float("inf"):
            closest_speakers = [lbl for lbl, d in proximity.items() if d == min_dist]
            if len(closest_speakers) == 1:
                return closest_speakers[0]
        else:
            closest_speakers = allowed
            
        # 3. Continuity fallback (ended most recently before the start of the local segments)
        first_loc_start = min(s["start"] for s in loc_segs_for_lbl) if loc_segs_for_lbl else 0.0
        
        latest_end_before_start = -1.0
        best_spk = closest_speakers[0]
        for glob_seg in global_timeline:
            if glob_seg["label"] in closest_speakers:
                if glob_seg["end"] <= first_loc_start and glob_seg["end"] > latest_end_before_start:
                    latest_end_before_start = glob_seg["end"]
                    best_spk = glob_seg["label"]
                    
        return best_spk

    def _run_pyannote_pipeline(self, audio_bytes: bytes, window_start: float) -> list:
        _lazy_init_pyannote()
        
        if self._pipeline is None:
            logger.info("DiarizationWorker: Initializing Pyannote Pipeline...")
            self._pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=settings.HUGGINGFACE_TOKEN
            )
            if torch.cuda.is_available():
                self._pipeline.to(torch.device("cuda"))
                logger.info("DiarizationWorker: Pipeline loaded on CUDA")
            else:
                logger.info("DiarizationWorker: Pipeline loaded on CPU")
                
        wav_io = pcm_to_wav_io(audio_bytes)
        annotation = self._pipeline(wav_io)
        
        local_segments = []
        for segment, track, label in annotation.itertracks(yield_label=True):
            local_segments.append({
                "start": window_start + segment.start,
                "end": window_start + segment.end,
                "label": label
            })
        return local_segments


# Singleton Instance
diarization_worker_manager = DiarizationWorkerManager()
