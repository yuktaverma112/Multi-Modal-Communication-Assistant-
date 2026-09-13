"""
backend/services/yolo_service.py

Wraps a pretrained Ultralytics YOLO model (trained on COCO, 80 classes)
for the Blind-mode object-detection pipeline:

    Camera -> OpenCV -> YOLO -> object + confidence -> text description -> TTS

We deliberately use the pretrained COCO weights rather than retraining on
the full COCO dataset ourselves (per the project guide's dataset
strategy, section 5) -- the annotations you uploaded are useful for
evaluation / understanding the class list, not for retraining a model
that Ultralytics already ships pretrained.
"""
from __future__ import annotations

import os
import threading
from typing import List, Dict

import numpy as np

MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "models/yolo/yolo11n.pt")
CONFIDENCE_THRESHOLD = float(os.getenv("YOLO_CONF_THRESHOLD", "0.4"))


class YOLOService:
    """Loads the model once (lazy singleton) and reuses it across requests.
    Loading per-request is called out in the guide as a real backend
    stability problem, so we avoid it here."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._model = None
            return cls._instance

    def _ensure_loaded(self):
        if self._model is None:
            from ultralytics import YOLO
            # Ultralytics auto-downloads the .pt weights from GitHub
            # releases the first time this runs, if MODEL_PATH doesn't
            # already exist locally.
            self._model = YOLO(MODEL_PATH)

    def detect(self, image: np.ndarray) -> List[Dict]:
        """Run detection on a BGR numpy image (as returned by cv2.imread /
        cv2.VideoCapture). Returns a list of {object, confidence, box}."""
        self._ensure_loaded()
        results = self._model(image, verbose=False)

        detections = []
        for result in results:
            for box in result.boxes:
                confidence = float(box.conf[0])
                if confidence < CONFIDENCE_THRESHOLD:
                    continue
                cls_id = int(box.cls[0])
                xyxy = box.xyxy[0].tolist()
                detections.append({
                    "object": self._model.names[cls_id],
                    "confidence": round(confidence, 3),
                    "box": [round(v, 1) for v in xyxy],
                })
        return detections

    @staticmethod
    def describe(detections: List[Dict]) -> str:
        """Turn raw detections into a short spoken-friendly sentence,
        e.g. 'I can see a person, a chair and a laptop.' Repeated
        objects are counted instead of repeated in a list, and this
        text is what should be cooled-down / de-duplicated by the
        caller across consecutive frames (see the guide's "Repeated TTS"
        problem in section 11)."""
        if not detections:
            return "I don't see any recognizable objects right now."

        from collections import Counter
        counts = Counter(d["object"] for d in detections)
        parts = []
        for name, n in counts.items():
            parts.append(f"{n} {name}{'s' if n > 1 else ''}")
        if len(parts) == 1:
            return f"I can see {parts[0]}."
        return "I can see " + ", ".join(parts[:-1]) + f" and {parts[-1]}."


yolo_service = YOLOService()
