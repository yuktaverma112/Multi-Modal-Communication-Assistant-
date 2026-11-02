"""
backend/services/tts_service.py

Text-to-speech service with robust Windows & cross-platform support:
1. Native Windows SAPI.SpVoice via win32com (fast, rock-solid, zero dependency issues)
2. pyttsx3 fallback (cross-platform, espeak-ng on Linux)
3. Synthetic WAV fallback if audio engine is completely absent.
"""
from __future__ import annotations

import os
import uuid
import wave
import struct

from backend.config import TTS_OUTPUT_DIR

AUDIO_OUTPUT_DIR = os.path.abspath(os.getenv("TTS_OUTPUT_DIR", TTS_OUTPUT_DIR))


class TTSService:
    def speak_to_file(self, text: str, rate: int = 170) -> str:
        """Synthesizes `text` to a .wav file and returns its path."""
        os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(AUDIO_OUTPUT_DIR, f"{uuid.uuid4().hex}.wav")

        # 1. Try win32com SAPI on Windows (avoids pyttsx3 comtypes version mismatch)
        if os.name == "nt":
            try:
                import win32com.client
                stream = win32com.client.Dispatch("SAPI.SpFileStream")
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                stream.Open(out_path, 3, False)  # 3 = SSFMCreateForWrite
                voice.AudioOutputStream = stream
                voice.Speak(text)
                stream.Close()
                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    return out_path
            except Exception:
                pass

        # 2. Try pyttsx3
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", rate)
            engine.save_to_file(text, out_path)
            engine.runAndWait()
            engine.stop()
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return out_path
        except Exception:
            pass

        # 3. Safe fallback: write valid silent/dummy WAV so API doesn't 500
        with wave.open(out_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            data = struct.pack("<h", 0) * 16000
            wav_file.writeframes(data)

        return out_path

    def speak_now(self, text: str, rate: int = 170) -> None:
        """Speaks immediately through local audio device."""
        if os.name == "nt":
            try:
                import win32com.client
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                voice.Speak(text)
                return
            except Exception:
                pass

        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", rate)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception:
            pass


tts_service = TTSService()
