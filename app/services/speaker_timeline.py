# =====================================================================
# SPEAKER TIMELINE TRACKER (app/services/speaker_timeline.py)
# =====================================================================
# Purpose: Manages global speaker timeline segments and provides time-range
#          queries to map transcripts to speakers with fallback logic.
# =====================================================================

import threading
from typing import Dict, List, Optional
from app.utils.logging import logger
from app.core.config import settings

MAX_SPEAKERS = settings.DIARIZATION_MAX_SPEAKERS
SPEAKER_LABELS = [f"Speaker_{i}" for i in range(MAX_SPEAKERS)]


class SpeakerTimeline:
    """
    Manages the global sequence of speaker segments for a single session.
    A segment is a dict: {"start": float, "end": float, "label": str}
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.segments: List[Dict[str, any]] = []
        self._lock = threading.Lock()

    def update_timeline(self, new_segments: List[Dict[str, any]], window_start: float) -> None:
        """
        Updates the global timeline with new diarized segments from window_start onwards.
        Replaces any existing timeline segments starting from or after window_start,
        and truncates any segments overlapping with window_start.
        """
        with self._lock:
            updated = []
            
            # Keep and/or truncate existing segments ending before window_start
            for seg in self.segments:
                if seg["end"] <= window_start:
                    updated.append(seg)
                elif seg["start"] < window_start:
                    # Truncate overlapping segment
                    seg_copy = seg.copy()
                    seg_copy["end"] = window_start
                    updated.append(seg_copy)
                    
            # Append the new mapped segments
            for new_seg in new_segments:
                # Ensure we only append allowed global speaker labels (Hard Cap: Max 3)
                if new_seg["label"] not in SPEAKER_LABELS:
                    continue

                if new_seg["end"] <= window_start:
                    continue
                
                adjusted_seg = {
                    "start": max(new_seg["start"], window_start),
                    "end": new_seg["end"],
                    "label": new_seg["label"]
                }
                updated.append(adjusted_seg)
                
            self.segments = self._smooth_and_filter_tiny_segments(updated)
            logger.debug(
                "SpeakerTimeline: Timeline updated",
                extra={"session_id": self.session_id, "segment_count": len(self.segments)}
            )

    def overwrite_timeline(self, new_segments: List[Dict[str, any]]) -> None:
        """
        Completely overwrites the timeline with a new set of global segments.
        Filters for allowed speakers, sorts, and merges adjacent identical speakers.
        """
        with self._lock:
            # Filter and ensure only allowed global speaker labels (Hard Cap: Max 3)
            filtered = []
            for seg in new_segments:
                if seg["label"] in SPEAKER_LABELS:
                    filtered.append(seg)
            self.segments = self._smooth_and_filter_tiny_segments(filtered)
            logger.info(
                "SpeakerTimeline: Timeline overwritten with global pass segments",
                extra={"session_id": self.session_id, "segment_count": len(self.segments)}
            )

    def _smooth_and_filter_tiny_segments(self, segments: List[Dict[str, any]], threshold: float = 0.5) -> List[Dict[str, any]]:
        """
        Filters out tiny speaker segments (duration < threshold) by merging them into neighbors.
        Then merges adjacent segments with identical labels for cleanliness.
        """
        if not segments:
            return []

        # Sort segments chronologically
        sorted_segs = sorted(segments, key=lambda x: x["start"])

        # First pass: identify and smooth out any flickers (duration < threshold)
        smoothed = []
        for i, seg in enumerate(sorted_segs):
            dur = seg["end"] - seg["start"]
            seg_copy = seg.copy()
            if dur < threshold:
                # Find left neighbor in the already-smoothed list
                left = smoothed[-1] if smoothed else None
                # Find right neighbor in the remaining sorted segments
                right = sorted_segs[i + 1] if i + 1 < len(sorted_segs) else None

                if left and right:
                    # Merge into the speaker with the larger adjacent duration to preserve identity
                    left_dur = left["end"] - left["start"]
                    right_dur = right["end"] - right["start"]
                    if right_dur > left_dur:
                        seg_copy["label"] = right["label"]
                    else:
                        seg_copy["label"] = left["label"]
                elif left:
                    seg_copy["label"] = left["label"]
                elif right:
                    seg_copy["label"] = right["label"]
            smoothed.append(seg_copy)

        # Second pass: merge adjacent segments sharing the same label
        merged = []
        if smoothed:
            smoothed.sort(key=lambda x: x["start"])
            curr = smoothed[0]
            for nxt in smoothed[1:]:
                # Merge if same speaker and close together
                if nxt["label"] == curr["label"] and nxt["start"] <= curr["end"] + 0.1:
                    curr["end"] = max(curr["end"], nxt["end"])
                else:
                    merged.append(curr)
                    curr = nxt
            merged.append(curr)

        return merged

    def get_speaker_for_range(self, start: float, end: float, return_details: bool = False) -> any:
        """
        Determines the active speaker for a time range [start, end].
        Priority Logic:
        1. Maximum overlap duration: Choose speaker with greatest overlap.
        2. Temporal proximity: If overlap = 0, choose speaker segment closest in time.
        3. Continuity fallback: If proximity ties, choose the speaker whose segment ended
           most recently BEFORE the start of the current range.
        4. Hard cap fallback: Always return one of Speaker_0, Speaker_1, or Speaker_2.
        """
        with self._lock:
            # Filter segments to enforce hard cap safety
            valid_segs = [s for s in self.segments if s["label"] in SPEAKER_LABELS]
            if not valid_segs:
                if return_details:
                    return "UNKNOWN", "No valid segments", {}
                return "UNKNOWN"

            # Priority 1: Overlap duration calculation
            overlaps = {}
            for seg in valid_segs:
                int_start = max(start, seg["start"])
                int_end = min(end, seg["end"])
                duration = int_end - int_start
                if duration > 0.01:
                    overlaps[seg["label"]] = overlaps.get(seg["label"], 0.0) + duration
                    
            if overlaps:
                best_speaker = max(overlaps, key=overlaps.get)
                if overlaps[best_speaker] > 0.01:
                    if return_details:
                        return best_speaker, "Maximum overlap", {"overlaps": overlaps}
                    return best_speaker
                    
            # Priority 2: Temporal proximity calculation (find segment closest to [start, end])
            proximity_scores = {}
            for seg in valid_segs:
                dist = min(abs(start - seg["end"]), abs(end - seg["start"]))
                proximity_scores[seg["label"]] = min(proximity_scores.get(seg["label"], float("inf")), dist)
                
            min_dist = min(proximity_scores.values())
            closest_speakers = [spk for spk, dist in proximity_scores.items() if dist == min_dist]
            
            if len(closest_speakers) == 1:
                if return_details:
                    return closest_speakers[0], "Temporal proximity", {"proximity_scores": proximity_scores}
                return closest_speakers[0]
                
            # Priority 3: Continuity fallback (choose segment that ended most recently before start)
            latest_end_before_start = -1.0
            best_spk = closest_speakers[0]
            for seg in valid_segs:
                if seg["label"] in closest_speakers:
                    if seg["end"] <= start and seg["end"] > latest_end_before_start:
                        latest_end_before_start = seg["end"]
                        best_spk = seg["label"]
            if return_details:
                return best_spk, "Continuity fallback", {
                    "proximity_scores": proximity_scores,
                    "latest_end_before_start": latest_end_before_start,
                    "tied_speakers": closest_speakers
                }
            return best_spk



class SpeakerTimelineManager:
    def __init__(self):
        self._timelines: Dict[str, SpeakerTimeline] = {}
        self._lock = threading.Lock()

    def get_timeline(self, session_id: str) -> SpeakerTimeline:
        with self._lock:
            if session_id not in self._timelines:
                self._timelines[session_id] = SpeakerTimeline(session_id)
            return self._timelines[session_id]

    def clear_timeline(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._timelines:
                del self._timelines[session_id]
                logger.info("SpeakerTimelineManager: Cleared timeline", extra={"session_id": session_id})

# Singleton Manager Instance
speaker_timeline_manager = SpeakerTimelineManager()
