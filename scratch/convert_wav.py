# pyrefly: ignore [missing-import]
import soundfile as sf
import os

def convert():
    input_path = "CAR0001.wav"
    output_path = "CAR0001_pcm.wav"
    
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found")
        return
        
    print(f"Reading {input_path}...")
    try:
        data, samplerate = sf.read(input_path)
        print(f"Input file info: channels={data.shape[1] if len(data.shape) > 1 else 1}, rate={samplerate}Hz, length={len(data)} samples")
        
        # Write as standard PCM 16-bit WAV
        sf.write(output_path, data, samplerate, subtype='PCM_16')
        print(f"Successfully converted and saved to {output_path}")
    except Exception as e:
        print(f"Error converting WAV file: {e}")

if __name__ == "__main__":
    convert()
