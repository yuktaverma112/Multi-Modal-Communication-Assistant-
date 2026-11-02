from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session

from backend.services.sign_service import sign_service
from backend.services.tts_service import tts_service
from backend.utils.preprocessing import decode_image_bytes
from backend.utils.response import ok, error
from backend.database.database import get_db
from backend.database import crud

router = APIRouter(prefix="/api", tags=["sign_language"])


@router.get("/sign-vocabulary")
def sign_vocabulary():
    """Returns the list of classes supported by the trained sign model."""
    info = sign_service.get_info()
    return ok(info)


@router.post("/recognize-sign")
async def recognize_sign(
    file: UploadFile = File(...),
    speak: bool = False,
    log: bool = True,
    db: Session = Depends(get_db),
):
    """Hearing-mode / communication-mode / live-translate pipeline:
    Camera -> MediaPipe/HOG -> MLP -> sign -> text/voice.

    log=False is used by the real-time polling loop in the Live
    Translate view (frontend/static/js/app.js), which calls this
    endpoint several times a second -- logging every poll would flood
    /api/history with noise instead of meaningful interactions. The
    one-shot "Recognize sign" button elsewhere still logs by default."""
    try:
        image = decode_image_bytes(await file.read())
    except ValueError as e:
        return error(str(e))

    result = sign_service.predict(image)
    if result.get("prediction") is None:
        return error(result.get("error", "No sign recognized."), code=422)

    if log:
        crud.log_prediction(db, "sign_language", result["prediction"], confidence=result["confidence"])

    audio_path = tts_service.speak_to_file(result["prediction"]) if speak else None
    result["audio_path"] = audio_path
    return ok(result)
