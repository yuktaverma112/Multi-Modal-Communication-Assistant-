from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session

from backend.services.ocr_service import ocr_service
from backend.services.tts_service import tts_service
from backend.utils.preprocessing import decode_image_bytes
from backend.utils.response import ok, error
from backend.database.database import get_db
from backend.database import crud

router = APIRouter(prefix="/api", tags=["ocr"])


@router.post("/read-text")
async def read_text(
    file: UploadFile = File(...),
    speak: bool = False,
    db: Session = Depends(get_db),
):
    """Blind-mode pipeline: Camera/Image -> preprocessing -> OCR -> text -> (optional) TTS."""
    try:
        image = decode_image_bytes(await file.read())
    except ValueError as e:
        return error(str(e))

    results = ocr_service.read_text(image)
    joined = " ".join(r["text"] for r in results).strip()

    avg_conf = (sum(r["confidence"] for r in results) / len(results)) if results else None
    crud.log_prediction(db, "ocr", joined, confidence=avg_conf)

    audio_path = tts_service.speak_to_file(joined) if (speak and joined) else None
    return ok({"words": results, "text": joined, "audio_path": audio_path})
