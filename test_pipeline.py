import config
from audio_processor import AudioProcessor
import os

def test_pipeline():
    audio_file = config.AUDIO_FILE
    out_file = "test_output.txt"
    if not os.path.exists(audio_file):
        print(f"Error: {audio_file} not found.", file=open(out_file, "w"))
        return
        
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"Testing new Micro-Segmenter Pipeline on: {audio_file}\n")
        f.write("="*60 + "\n")
        
    ap = AudioProcessor(config.WHISPER_MODEL_SIZE)
    chunks, lang = ap.run_pipeline(
        audio_file, 
        language=config.WHISPER_LANGUAGE,
        silence_threshold_s=config.SILENCE_THRESHOLD_S
    )
    
    with open(out_file, "a", encoding="utf-8") as f:
        f.write("\n" + "="*60 + "\n")
        f.write("FINAL CHUNKS PREVIEW\n")
        f.write("="*60 + "\n")
        for i, c in enumerate(chunks[:50]):
            start = ap.format_time(c["start"])
            end = ap.format_time(c["end"])
            text = c.get("text_final", c.get("text_raw", ""))
            event = c.get("event", "unknown")
            f.write(f"{i+1:02d}. [{start} - {end}] {event:12s} -> {text}\n")

if __name__ == "__main__":
    test_pipeline()
