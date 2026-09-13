from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session

from backend.services.yolo_service import yolo_service
from backend.services.tts_service import tts_service
from backend.utils.preprocessing import decode_image_bytes
from backend.utils.response import ok, error
from backend.database.database import get_db
from backend.database import crud

router = APIRouter(prefix="/api", tags=["object_detection"])


@router.post("/detect-object")
async def detect_object(
    file: UploadFile = File(...),
    speak: bool = False,
    db: Session = Depends(get_db),
):
    """Blind-mode pipeline: Camera frame -> YOLO -> objects -> (optional) TTS."""
    try:
        image = decode_image_bytes(await file.read())
    except ValueError as e:
        return error(str(e))

    try:
        detections = yolo_service.detect(image)
    except Exception as e:
        return error(
            f"YOLO backend not available ({e}). Run `pip install ultralytics` "
            f"and ensure models/yolo/yolo11n.pt can be downloaded on first use.",
            code=503,
        )

    description = yolo_service.describe(detections)
    crud.log_prediction(db, "object_detection", description,
                         confidence=max([d["confidence"] for d in detections], default=None))

    audio_path = tts_service.speak_to_file(description) if speak else None
    return ok({"detections": detections, "description": description, "audio_path": audio_path})
