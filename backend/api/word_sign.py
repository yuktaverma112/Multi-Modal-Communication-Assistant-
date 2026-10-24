import json
import os

from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session

from backend.services.word_sign_service import word_sign_service
from backend.services.tts_service import tts_service
from backend.utils.audio import save_upload_bytes, cleanup
from backend.utils.response import ok, error
from backend.database.database import get_db
from backend.database import crud

router = APIRouter(prefix="/api", tags=["word_sign"])

GLOSSES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "datasets", "sign_language", "WLASL100", "wlasl100_glosses.json"
)


@router.get("/word-model-status")
def word_model_status():
    """So the frontend can show/hide word-sign UI instead of letting
    every attempt fail with a 503."""
    return ok({"trained": word_sign_service.is_trained()})


@router.get("/word-vocabulary")
def word_vocabulary():
    """The 100 WLASL glosses already staged in this project
    (datasets/sign_language/WLASL100/) -- a suggested starting
    vocabulary for recording or downloading word clips, exposed here
    so it's genuinely used by the app, not just a dead file on disk."""
    if not os.path.exists(GLOSSES_PATH):
        return ok({"glosses": []})
    with open(GLOSSES_PATH) as f:
        glosses = json.load(f)
    return ok({"glosses": sorted(glosses)})


@router.post("/recognize-word")
async def recognize_word(
    file: UploadFile = File(...),
    speak: bool = False,
    log: bool = True,
    db: Session = Depends(get_db),
):
    """Word-level pipeline: a short video clip (not one photo) of a
    whole sign -> MediaPipe/HOG per frame -> pooled clip descriptor ->
    MLP -> word -> (optional) TTS. Returns a clear error, not a
    silent wrong guess, if no word model has been trained yet."""
    suffix = "." + (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "webm")
    path = save_upload_bytes(await file.read(), suffix=suffix)
    try:
        result = word_sign_service.predict_from_video(path)
    finally:
        cleanup(path)

    if result.get("prediction") is None:
        return error(result.get("error", "No word recognized."), code=503)

    if log:
        crud.log_prediction(db, "sign_language", result["prediction"], confidence=result["confidence"])

    audio_path = tts_service.speak_to_file(result["prediction"]) if speak else None
    result["audio_path"] = audio_path
    return ok(result)
