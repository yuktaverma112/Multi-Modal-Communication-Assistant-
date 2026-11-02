"""
backend/services/sign_service.py

Hearing-mode / communication-mode sign-language pipeline:

    Camera -> MediaPipe Hands (or HOG fallback) -> landmarks/features
           -> MLP -> sign -> text/voice

Loads the artifacts produced by:
    scripts/extract_isl_landmarks.py   -> models/sign_language/isl_features.npz
    scripts/train_sign_model.py        -> sign_model.pkl, scaler.pkl, label_encoder.pkl

Trained on the augmented dataset across 21 classes (both alphabet fingerspelling
and whole-word/phrase signs: A-X, Book, Congratulations, goodmorning, HappyBirthday,
how are you, Please, Sun).
"""
from __future__ import annotations

import os
import threading
from typing import Dict, List

import joblib
import numpy as np

from backend.utils.preprocessing import extract_features

MODEL_DIR = os.getenv(
    "SIGN_MODEL_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "models", "sign_language"),
)


class SignService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._model = None
                cls._instance._scaler = None
                cls._instance._encoder = None
            return cls._instance

    def _ensure_loaded(self):
        if self._model is None:
            self._model = joblib.load(os.path.join(MODEL_DIR, "sign_model.pkl"))
            self._scaler = joblib.load(os.path.join(MODEL_DIR, "scaler.pkl"))
            self._encoder = joblib.load(os.path.join(MODEL_DIR, "label_encoder.pkl"))

    def get_classes(self) -> List[str]:
        self._ensure_loaded()
        return [str(c) for c in self._encoder.classes_]

    def get_info(self) -> Dict:
        self._ensure_loaded()
        expected_dim = self._scaler.mean_.shape[0]
        classes = self.get_classes()
        return {
            "feature_dim": expected_dim,
            "method": "landmarks" if expected_dim == 63 else "hog",
            "class_count": len(classes),
            "classes": classes,
        }

    def predict(self, image: np.ndarray, top_k: int = 3) -> Dict:
        """image: a BGR frame/crop containing (ideally) a single hand.
        Returns {"prediction": str, "confidence": float,
        "top_k": [{"label":..., "confidence":...}, ...],
        "extraction_method": "landmarks"|"hog"}."""
        self._ensure_loaded()

        feats, method, landmarks = extract_features(
            image,
            prefer_landmarks=True,
            include_landmarks=True,
        )
        expected_dim = self._scaler.mean_.shape[0]
        if feats.shape[0] != expected_dim:
            # Model was trained on landmarks (63-d) or HOG -- force the
            # matching extractor rather than silently mis-predicting.
            from backend.utils.preprocessing import extract_hog_features, extract_hand_landmarks
            if expected_dim == 63:
                feats = extract_hand_landmarks(image)
                method = "landmarks"
                landmarks = None
                if feats is None:
                    return {
                        "prediction": None,
                        "confidence": 0.0,
                        "top_k": [],
                        "extraction_method": "none",
                        "error": "No hand detected in frame.",
                    }
            else:
                feats = extract_hog_features(image)
                method = "hog"

        X = self._scaler.transform(feats.reshape(1, -1))
        probs = self._model.predict_proba(X)[0]
        order = np.argsort(probs)[::-1][:top_k]
        labels = self._encoder.inverse_transform(order)

        top_k_list: List[Dict] = [
            {"label": str(lbl), "confidence": round(float(probs[i]), 3)}
            for lbl, i in zip(labels, order)
        ]

        return {
            "prediction": top_k_list[0]["label"],
            "confidence": top_k_list[0]["confidence"],
            "top_k": top_k_list,
            "extraction_method": method,
            "hand_landmarks": (
                np.round(landmarks[:, :2], 4).tolist()
                if landmarks is not None
                else []
            ),
        }


sign_service = SignService()
