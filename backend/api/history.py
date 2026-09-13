from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.database import crud
from backend.utils.response import ok

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/history")
def history(modality: str | None = Query(default=None), limit: int = 50, db: Session = Depends(get_db)):
    rows = crud.get_history(db, modality=modality, limit=limit)
    return ok([
        {
            "id": r.id,
            "modality": r.modality,
            "result_text": r.result_text,
            "confidence": r.confidence,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ])
