"""
backend/main.py

FastAPI entry point. Run with:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

Serves:
  - JSON API under /api/... (see backend/api/*.py)
  - The static frontend (frontend/static/) at /
  - Interactive API docs at /docs
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import TTS_OUTPUT_DIR
from backend.database.database import init_db
from backend.api import object_detection, ocr, speech, sign_language, word_sign, communication, history


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI-Based Multi-Modal Accessibility Assistant",
    description=(
        "Real-time object detection, OCR, speech recognition and sign "
        "language translation for blind and hearing-impaired users."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(object_detection.router)
app.include_router(ocr.router)
app.include_router(speech.router)
app.include_router(sign_language.router)
app.include_router(word_sign.router)
app.include_router(communication.router)
app.include_router(history.router)


@app.get("/api/health")
def health():
    return {"code": 200, "message": "OK", "data": {"status": "up"}}


os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=TTS_OUTPUT_DIR), name="media")

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "static")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
