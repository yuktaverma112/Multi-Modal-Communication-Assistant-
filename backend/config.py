"""
backend/config.py

Small centralized settings module. Individual services still read
their own specific env vars (YOLO_MODEL_PATH, WHISPER_MODEL_SIZE, ...)
so they stay independently testable; this module only holds settings
genuinely shared across the app (paths, DB URL).
"""
import os

from dotenv import load_dotenv

load_dotenv()  # loads .env if present; no-op (and harmless) if it isn't

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/backend/database/app.db")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "outputs", "uploads"))
TTS_OUTPUT_DIR = os.getenv("TTS_OUTPUT_DIR", os.path.join(BASE_DIR, "outputs", "tts"))

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
