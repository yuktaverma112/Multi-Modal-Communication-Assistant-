"""
backend/database/models.py

Per the guide's privacy section: store only prediction/confidence/
timestamp metadata by default, never raw camera/audio frames, unless
a user explicitly opts in to saving media (not implemented here --
add a `media_path` column + explicit consent flag if you need it).
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, func

from backend.database.database import Base


class PredictionHistory(Base):
    __tablename__ = "prediction_history"

    id = Column(Integer, primary_key=True, index=True)
    modality = Column(String, index=True)       # "object_detection" | "ocr" | "speech" | "sign_language"
    result_text = Column(String)                # e.g. "person, chair" / recognized text / predicted sign
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
