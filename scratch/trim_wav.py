import wave
import os

def trim_wav(input_path, output_path, max_duration_sec=300):
    print(f"Trimming {input_path} to max {max_duration_sec} seconds...")
    if not os.path.exists(input_path):
        print(f"Error: {input_path} does not exist.")
        return

    with wave.open(input_path, 'rb') as infile:
        params = infile.getparams()
        framerate = infile.getframerate()
        nframes = infile.getnframes()
        
        # Calculate target frames
        target_frames = int(max_duration_sec * framerate)
        if nframes <= target_frames:
            print(f"File is already shorter than {max_duration_sec} seconds ({nframes / framerate:.2f}s). No trimming needed.")
            return
            
        print(f"Original duration: {nframes / framerate:.2f} seconds ({nframes} frames)")
        print(f"Trimming to: {max_duration_sec} seconds ({target_frames} frames)")
        
        frames_to_read = target_frames
        audio_data = infile.readframes(frames_to_read)
        
    temp_output_path = output_path + ".tmp"
    with wave.open(temp_output_path, 'wb') as outfile:
        # Update params for the new file (set nframes to target_frames)
        new_params = params._replace(nframes=target_frames)
        outfile.setparams(new_params)
        outfile.writeframes(audio_data)
        
    # Replace the original file or final output path
    if os.path.exists(output_path):
        os.remove(output_path)
    os.rename(temp_output_path, output_path)
    print(f"Successfully trimmed and saved to {output_path}")

if __name__ == "__main__":
    trim_wav("CAR0001_pcm.wav", "CAR0001_pcm.wav", 300)
