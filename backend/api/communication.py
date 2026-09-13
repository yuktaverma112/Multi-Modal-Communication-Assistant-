"""
backend/api/communication.py

Communication-mode pipeline (two-way speech/sign <-> text <-> speech),
per the guide's architecture diagram:

    Camera/Mic -> Speech/Sign -> Text -> TTS

Rather than duplicating logic, this router composes the other three
services so the frontend's single "Communication" screen has one
endpoint per direction instead of juggling three.
"""
from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session

from backend.services.whisper_service import whisper_service
from backend.services.sign_service import sign_service
from backend.services.tts_service import tts_service
from backend.utils.preprocessing import decode_image_bytes
from backend.utils.audio import save_upload_bytes, cleanup
from backend.utils.response import ok, error
from backend.database.database import get_db
from backend.database import crud

router = APIRouter(prefix="/api/communicate", tags=["communication"])


@router.post("/hearing-to-deaf")
async def hearing_to_deaf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """A hearing person speaks -> transcribed to text on screen for the
    deaf/hard-of-hearing participant to read."""
    suffix = "." + (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "wav")
    path = save_upload_bytes(await file.read(), suffix=suffix)
    try:
        result = whisper_service.transcribe(path)
    except Exception as e:
        return error(f"Whisper backend not available ({e}).", code=503)
    finally:
        cleanup(path)
    crud.log_prediction(db, "speech", result["text"])
    return ok({"text": result["text"]})


@router.post("/deaf-to-hearing")
async def deaf_to_hearing(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """A deaf/hard-of-hearing person signs -> recognized -> spoken aloud
    for the hearing participant to listen to."""
    try:
        image = decode_image_bytes(await file.read())
    except ValueError as e:
        return error(str(e))

    result = sign_service.predict(image)
    if result.get("prediction") is None:
        return error(result.get("error", "No sign recognized."), code=422)

    crud.log_prediction(db, "sign_language", result["prediction"], confidence=result["confidence"])
    audio_path = tts_service.speak_to_file(result["prediction"])
    return ok({"text": result["prediction"], "confidence": result["confidence"], "audio_path": audio_path})


@router.post("/type-to-hearing")
async def type_to_hearing(text: str = Form(...)):
    """Fallback direction for when sign recognition isn't confident
    enough: the deaf/hard-of-hearing user types instead, still gets
    spoken aloud to the hearing participant."""
    audio_path = tts_service.speak_to_file(text)
    return ok({"text": text, "audio_path": audio_path})
