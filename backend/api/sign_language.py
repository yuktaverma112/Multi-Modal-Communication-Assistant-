from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session

from backend.services.sign_service import sign_service
from backend.services.tts_service import tts_service
from backend.utils.preprocessing import decode_image_bytes
from backend.utils.response import ok, error
from backend.database.database import get_db
from backend.database import crud

router = APIRouter(prefix="/api", tags=["sign_language"])


@router.post("/recognize-sign")
async def recognize_sign(
    file: UploadFile = File(...),
    speak: bool = False,
    db: Session = Depends(get_db),
):
    """Hearing-mode / communication-mode pipeline:
    Camera -> MediaPipe/HOG -> MLP -> sign -> text/voice."""
    try:
        image = decode_image_bytes(await file.read())
    except ValueError as e:
        return error(str(e))

    result = sign_service.predict(image)
    if result.get("prediction") is None:
        return error(result.get("error", "No sign recognized."), code=422)

    crud.log_prediction(db, "sign_language", result["prediction"], confidence=result["confidence"])

    audio_path = tts_service.speak_to_file(result["prediction"]) if speak else None
    result["audio_path"] = audio_path
    return ok(result)
