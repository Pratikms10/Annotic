# config.py
import os

# URL of the Annotic transcription task page
ANNOTIC_TASK_URL = "https://annotic.in/#/projects/98/AudioTranscriptionLandingPage/36274"

# Whisper Settings
WHISPER_MODEL_SIZE = "base"    # Options: tiny, base, small, medium, large
WHISPER_LANGUAGE = None        # None = auto-detect (English or Hindi)

# Chunking Settings
PAUSE_SPLIT_S = 0.3            # Pauses >0.3s trigger a new segment (micro-chunking)
SILENCE_THRESHOLD_S = 2.0      # Pauses >2.0s trigger a <SIL> tag
MAX_WORDS_PER_CHUNK = 5        # Force split if a chunk gets too long

# Playwright Settings
HEADLESS_MODE = False
PLAYWRIGHT_SESSION_DIR = os.path.join(os.path.dirname(__file__), "playwright_session")

# Audio temp files
AUDIO_FILE = os.path.join(os.path.dirname(__file__), "downloaded_audio.wav")
