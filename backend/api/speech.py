from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session

from backend.services.whisper_service import whisper_service
from backend.services.tts_service import tts_service
from backend.utils.audio import save_upload_bytes, cleanup
from backend.utils.response import ok, error
from backend.database.database import get_db
from backend.database import crud

router = APIRouter(prefix="/api", tags=["speech"])


@router.post("/speech-to-text")
async def speech_to_text(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Hearing-mode pipeline: Microphone -> Whisper -> text -> screen."""
    suffix = "." + (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "wav")
    path = save_upload_bytes(await file.read(), suffix=suffix)
    try:
        result = whisper_service.transcribe(path)
    except Exception as e:
        return error(
            f"Whisper backend not available ({e}). Run "
            f"`pip install openai-whisper` (needs ffmpeg + ~140MB model download "
            f"on first use).",
            code=503,
        )
    finally:
        cleanup(path)

    crud.log_prediction(db, "speech", result["text"])
    return ok(result)


@router.post("/text-to-speech")
async def text_to_speech(text: str = Form(...)):
    """Reverse direction: typed/recognized text -> spoken audio, so a
    hearing participant can listen instead of read (communication mode)."""
    path = tts_service.speak_to_file(text)
    return ok({"audio_path": path})
