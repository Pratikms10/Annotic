import sys
import wave
import config
from audio_processor import AudioProcessor
import os

def chop_audio(input_file, output_file, duration_sec=15):
    try:
        with wave.open(input_file, 'rb') as fin:
            frames = fin.getnframes()
            rate = fin.getframerate()
            
            # Read only first X seconds
            frames_to_read = min(frames, int(rate * duration_sec))
            data = fin.readframes(frames_to_read)
            
            with wave.open(output_file, 'wb') as fout:
                fout.setparams(fin.getparams())
                fout.setnframes(frames_to_read)
                fout.writeframes(data)
        print(f"Created short audio file: {output_file} ({duration_sec}s)")
        return True
    except Exception as e:
        print(f"Error chopping audio: {e}")
        return False

def test_pipeline():
    orig_file = config.AUDIO_FILE
    short_file = orig_file.replace(".wav", "_short.wav")
    
    if not os.path.exists(orig_file):
        print(f"Error: {orig_file} not found.")
        return
        
    if chop_audio(orig_file, short_file, 15):
        print(f"\nTesting Micro-Segmenter Pipeline on: {short_file}")
        print("="*60)
        
        ap = AudioProcessor("base")
        chunks, lang = ap.run_pipeline(
            short_file, 
            language=config.WHISPER_LANGUAGE,
            silence_threshold_s=config.SILENCE_THRESHOLD_S
        )
        
        print("\n" + "="*60)
        print("FINAL CHUNKS PREVIEW")
        print("="*60)
        for i, c in enumerate(chunks):
            start = ap.format_time(c["start"])
            end = ap.format_time(c["end"])
            text = c.get("text_final", c.get("text_raw", ""))
            event = c.get("event", "unknown")
            print(f"{i+1:02d}. [{start} - {end}] {event:12s} -> {text}")

if __name__ == "__main__":
    test_pipeline()
