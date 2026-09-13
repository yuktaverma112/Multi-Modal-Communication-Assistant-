"""
backend/services/whisper_service.py

Hearing-mode speech-to-text pipeline:

    Microphone -> Whisper -> text -> screen

NOTE on this sandbox: openai-whisper pulls in PyTorch and downloads a
model checkpoint (~140MB for "base") on first use. That install was
deliberately NOT run inside the limited-disk demo sandbox used to
build this project (see README "What was actually executed here" /
requirements.txt) -- but this service is fully implemented and will
work as-is once you `pip install -r requirements.txt` on a normal
machine with a few GB of free disk and run it once with internet
access so the model checkpoint can download.
"""
from __future__ import annotations

import os
import threading
from typing import Dict

MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")


class WhisperService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._model = None
            return cls._instance

    def _ensure_loaded(self):
        if self._model is None:
            import whisper
            self._model = whisper.load_model(MODEL_SIZE)

    def transcribe(self, audio_path: str, language: str | None = "en") -> Dict:
        """audio_path: path to a wav/mp3/m4a file on disk (see
        backend/utils/audio.py for saving an uploaded file to a temp
        path first). Returns {"text": ..., "language": ...}."""
        self._ensure_loaded()
        result = self._model.transcribe(audio_path, language=language)
        return {"text": result["text"].strip(), "language": result.get("language", language)}


whisper_service = WhisperService()
