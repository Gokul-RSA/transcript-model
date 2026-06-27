import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.services.diarization_worker import diarization_worker_manager, _pcm_bytes_to_tensor, _lazy_init_pyannote
from app.services.speaker_timeline import speaker_timeline_manager
import wave

async def main():
    wav_path = "speech-sample.wav"
    if not os.path.exists(wav_path):
        print(f"Error: {wav_path} not found")
        return
        
    print(f"Reading {wav_path}...")
    with wave.open(wav_path, "rb") as wf:
        raw_bytes = wf.readframes(wf.getnframes())
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        
    print(f"Original WAV: channels={channels}, rate={sample_rate}, width={sample_width}")
    
    # Preload the pipeline
    print("Loading Pyannote pipeline...")
    settings.DIARIZATION_MODE = "production"
    await diarization_worker_manager.preload_pipeline()
    
    # Process audio bytes
    # Since we need to match the backend conversion, if channels > 1 we mono it
    import audioop
    if channels > 1:
        raw_bytes = audioop.tomono(raw_bytes, sample_width, 0.5, 0.5)
        channels = 1
    if sample_width != 2:
        raw_bytes = audioop.lin2lin(raw_bytes, sample_width, 2)
        sample_width = 2
    if sample_rate != 16000:
        state = None
        raw_bytes, state = audioop.ratecv(raw_bytes, sample_width, channels, sample_rate, 16000, state)
        sample_rate = 16000
        
    print("Running Pyannote global pass diarization...")
    # Run the pipeline
    local_segments = diarization_worker_manager._run_pyannote_pipeline("test-session", raw_bytes, 0.0)
    
    print("\n--- Raw Segments from Pyannote ---")
    for seg in local_segments:
        print(f"[{seg['start']:.2f}s - {seg['end']:.2f}s]: {seg['label']}")
        
    # Map to Speaker_0, Speaker_1, Speaker_2
    first_appearances = {}
    for seg in local_segments:
        lbl = seg["label"]
        if lbl not in first_appearances:
            first_appearances[lbl] = seg["start"]
    unique_labels = sorted(list(first_appearances.keys()), key=lambda x: first_appearances[x])
    
    from app.services.speaker_timeline import SPEAKER_LABELS
    global_mapping = {}
    for idx, loc_lbl in enumerate(unique_labels):
        if idx < len(SPEAKER_LABELS):
            global_mapping[loc_lbl] = SPEAKER_LABELS[idx]
        else:
            global_mapping[loc_lbl] = SPEAKER_LABELS[-1]
            
    print("\n--- Global Mapping ---")
    print(global_mapping)
    
    mapped_segments = [
        {
            "start": seg["start"],
            "end": seg["end"],
            "label": global_mapping.get(seg["label"], SPEAKER_LABELS[0])
        }
        for seg in local_segments
    ]
    
    # Overwrite timeline
    timeline = speaker_timeline_manager.get_timeline("test-session")
    timeline.overwrite_timeline(mapped_segments)
    
    print("\n--- Smoothed Timeline Segments ---")
    for seg in timeline.segments:
        print(f"[{seg['start']:.2f}s - {seg['end']:.2f}s]: {seg['label']}")

if __name__ == "__main__":
    asyncio.run(main())
