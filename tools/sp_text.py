import os
import subprocess
import numpy as np
import imageio_ffmpeg
import warnings
import sys

from agents.text_db_agent import main

sys.stdout.reconfigure(encoding="utf-8")

# (Optional) Remove FP16 warnings
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")


# -------------------------------
# 1️⃣  Setup FFmpeg from imageio
# -------------------------------
ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

# Force Whisper model downloads to D:
os.environ["WHISPER_CACHE_DIR"] = "D:/WhisperCache"
os.makedirs(os.environ["WHISPER_CACHE_DIR"], exist_ok=True)


# -------------------------------
# 2️⃣  Patch Whisper audio loader
# -------------------------------
def load_audio(file: str, sr: int = 16000):
    """
    Load audio using FFmpeg from imageio_ffmpeg
    """
    cmd = [
        ffmpeg_path,
        "-nostdin",
        "-i", file,
        "-ac", "1",
        "-ar", str(sr),
        "-f", "s16le",
        "-"
    ]

    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    audio = np.frombuffer(out, np.int16).astype(np.float32) / 32768.0
    return audio.flatten()


# Override Whisper audio function BEFORE importing whisper
import whisper.audio
whisper.audio.load_audio = load_audio


# -------------------------------
# 3️⃣  Load Whisper + Transcribe
# -------------------------------
import whisper
print("Loading Whisper Base model...")
model_base = whisper.load_model("base")

print("Loading Whisper Turbo model...")
model_turbo = whisper.load_model("large-v3-turbo")

def speech_to_text_base(audio_path: str, lang: str):
    """
    Converts audio to text using the fast Base model.
    """
    result = model_base.transcribe(
        audio_path,
        language=lang,
        task="translate"   # ensures English output always
    )
    
    text = result.get("text", "").strip()
    print(f"[Whisper Base] Extracted Text: {text}")
    return text


def speech_to_text_turbo(audio_path: str, lang: str):
    """
    Converts audio to text using the highly accurate Turbo model.
    """
    result = model_turbo.transcribe(
        audio_path,
        language=lang,
        task="translate"   # ensures English output always
    )
    
    text = result.get("text", "").strip()
    print(f"[Whisper Turbo] Extracted Text: {text}")
    return text