import wave

def check_wav(file_path):
    try:
        with wave.open(file_path, 'rb') as wf:
            channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            sample_width = wf.getsampwidth()
            frames = wf.getnframes()
            duration = frames / float(sample_rate)
            print(f"File: {file_path}")
            print(f"Channels: {channels}")
            print(f"Sample Rate: {sample_rate} Hz")
            print(f"Sample Width: {sample_width} bytes ({sample_width * 8}-bit)")
            print(f"Frames: {frames}")
            print(f"Duration: {duration:.2f} seconds ({duration / 60.0:.2f} minutes)")
    except Exception as e:
        print(f"Error checking WAV file: {e}")

if __name__ == "__main__":
    check_wav("CAR0001.wav")
