"""
backend/utils/audio.py

Helpers for turning an uploaded audio file (FastAPI UploadFile bytes)
into a temp path on disk, since whisper.transcribe() and most audio
libraries want a file path rather than raw bytes.
"""
import os
import uuid

from backend.config import UPLOAD_DIR


def save_upload_bytes(data: bytes, suffix: str = ".wav") -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{suffix}")
    with open(path, "wb") as f:
        f.write(data)
    return path


def cleanup(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
