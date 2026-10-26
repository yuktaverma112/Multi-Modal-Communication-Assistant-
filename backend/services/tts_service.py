"""
backend/services/tts_service.py

Text-to-speech, used at the end of both the Blind-mode pipeline
(object description / OCR text -> speech) and the Hearing-mode
"communication" pipeline (typed/recognized-sign text -> speech so a
hearing participant can listen instead of read).

Backend: pyttsx3, which wraps the OS speech engine (espeak-ng on
Linux -- installed via `apt install espeak-ng`). Fully offline, no
API key, no model download. edge-tts (listed as optional in
requirements.txt) gives higher-quality voices but needs internet; swap
it in later if you want nicer audio for a demo video.

pyttsx3's engine object is NOT thread-safe / reusable across many
rapid calls in some environments, so instead of keeping one long-lived
engine (like the singleton pattern used elsewhere in this project) we
create a fresh engine per call. This is slightly slower but far more
reliable for a request-per-call FastAPI backend.
"""
from __future__ import annotations

import os
import uuid

from backend.config import TTS_OUTPUT_DIR

AUDIO_OUTPUT_DIR = os.path.abspath(os.getenv("TTS_OUTPUT_DIR", TTS_OUTPUT_DIR))


class TTSService:
    def speak_to_file(self, text: str, rate: int = 170) -> str:
        """Synthesizes `text` to a .wav file and returns its path.
        Used by the API so the frontend can <audio> play the result
        instead of relying on server-side speakers."""
        import pyttsx3

        os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(AUDIO_OUTPUT_DIR, f"{uuid.uuid4().hex}.wav")

        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.save_to_file(text, out_path)
        engine.runAndWait()
        engine.stop()
        return out_path

    def speak_now(self, text: str, rate: int = 170) -> None:
        """Speaks immediately through the server's audio device. Only
        useful for local/desktop demos, not a real multi-user web
        deployment (use speak_to_file there instead)."""
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.say(text)
        engine.runAndWait()
        engine.stop()


tts_service = TTSService()
