from sqlalchemy.orm import Session

from backend.database.models import PredictionHistory


def log_prediction(db: Session, modality: str, result_text: str, confidence: float | None = None):
    entry = PredictionHistory(modality=modality, result_text=result_text, confidence=confidence)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_history(db: Session, modality: str | None = None, limit: int = 50):
    q = db.query(PredictionHistory)
    if modality:
        q = q.filter(PredictionHistory.modality == modality)
    return q.order_by(PredictionHistory.created_at.desc()).limit(limit).all()
