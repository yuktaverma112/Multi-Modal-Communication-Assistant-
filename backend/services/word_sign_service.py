"""
backend/services/word_sign_service.py

Word-level sign recognition: a short video clip of a whole sign (not
one static letter pose) -> a word. Mirrors sign_service.py's
lazy-singleton pattern, but its feature extraction pools per-frame
hand features across the clip instead of using a single frame (see
scripts/extract_word_landmarks.py's pool_clip_features(), which this
reuses so training and inference stay in exact agreement).

No model is trained by default -- this project ships only WLASL
*metadata*, not video, because every WLASL video host is unreachable
from the sandbox this was developed in. predict_from_video() returns
a clear "not trained yet" error until you've run:
    scripts/extract_word_landmarks.py
    scripts/train_word_model.py
on a machine with real word-sign video clips. See their docstrings.
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Dict, List

import cv2
import joblib
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from backend.utils.preprocessing import extract_features  # noqa: E402
from scripts.extract_word_landmarks import (  # noqa: E402
    pool_clip_features,
    sample_frame_indices,
    MAX_FRAMES_SAMPLED,
    MIN_VALID_FRAMES,
)

MODEL_DIR = os.getenv(
    "WORD_MODEL_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "models", "sign_language"),
)


class WordSignService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._model = None
                cls._instance._scaler = None
                cls._instance._encoder = None
                cls._instance._load_attempted = False
            return cls._instance

    def is_trained(self) -> bool:
        return os.path.exists(os.path.join(MODEL_DIR, "word_model.pkl"))

    def _ensure_loaded(self):
        if self._model is not None or self._load_attempted:
            return
        self._load_attempted = True
        if not self.is_trained():
            return
        self._model = joblib.load(os.path.join(MODEL_DIR, "word_model.pkl"))
        self._scaler = joblib.load(os.path.join(MODEL_DIR, "word_scaler.pkl"))
        self._encoder = joblib.load(os.path.join(MODEL_DIR, "word_label_encoder.pkl"))

    def predict_from_video(self, video_path: str, top_k: int = 3) -> Dict:
        self._ensure_loaded()
        if self._model is None:
            return {
                "prediction": None,
                "error": (
                    "No word-level model has been trained yet. This ships with WLASL "
                    "metadata only, not video (see scripts/extract_word_landmarks.py). "
                    "Run that script, then scripts/train_word_model.py, on a machine "
                    "with real word-sign clips."
                ),
            }

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {"prediction": None, "error": "Could not open the uploaded clip."}

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        indices = set(sample_frame_indices(total, MAX_FRAMES_SAMPLED)) if total else None

        frame_vectors = []
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if indices is None or i in indices:
                vec, _method = extract_features(frame, prefer_landmarks=True)
                frame_vectors.append(vec)
            i += 1
        cap.release()

        if len(frame_vectors) < MIN_VALID_FRAMES:
            return {"prediction": None, "error": "Clip too short, or no hand detected in enough frames."}

        descriptor = pool_clip_features(frame_vectors)
        expected_dim = self._scaler.mean_.shape[0]
        if descriptor.shape[0] != expected_dim:
            return {
                "prediction": None,
                "error": (
                    f"Feature size mismatch ({descriptor.shape[0]} vs {expected_dim} expected) -- "
                    "the live MediaPipe/HOG availability differs from when the model was trained. "
                    "Re-run the extract+train scripts in the same environment you're serving from."
                ),
            }

        X = self._scaler.transform(descriptor.reshape(1, -1))
        probs = self._model.predict_proba(X)[0]
        order = np.argsort(probs)[::-1][:top_k]
        labels = self._encoder.inverse_transform(order)

        top_k_list: List[Dict] = [
            {"label": str(lbl), "confidence": round(float(probs[i]), 3)} for lbl, i in zip(labels, order)
        ]
        return {
            "prediction": top_k_list[0]["label"],
            "confidence": top_k_list[0]["confidence"],
            "top_k": top_k_list,
        }


word_sign_service = WordSignService()
