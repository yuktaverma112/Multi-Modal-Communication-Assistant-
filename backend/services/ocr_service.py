"""
backend/services/ocr_service.py

Blind-mode OCR pipeline:

    Camera/Image -> preprocessing -> OCR -> extracted text -> TTS/display

Two backends are supported, mirroring the strategy already used in
backend/utils/preprocessing.py for sign language (try the heavier,
more accurate model; fall back to something that works fully offline):

1. EasyOCR (project guide's recommendation) -- much better accuracy on
   real-world photos (signs, labels, documents) but pulls in a large
   PyTorch dependency and downloads detector/recognizer weights on
   first use. Use this in your real dev/deployment environment.

2. pytesseract + the Tesseract OCR engine -- lightweight, works fully
   offline once `apt install tesseract-ocr` has been run, no GPU/large
   model download needed. This is what actually runs inside this
   sandboxed environment for the smoke test in scripts/demo_pipeline.py.

Both backends are wrapped behind the same read_text() -> List[{text,
confidence}] interface so backend/api/ocr.py never has to know which
one is active.
"""
from __future__ import annotations

import threading
from typing import List, Dict

import cv2
import numpy as np


class OCRService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._reader = None
                cls._instance._backend = None
            return cls._instance

    def _ensure_loaded(self):
        if self._backend is not None:
            return
        try:
            import easyocr
            self._reader = easyocr.Reader(["en"], gpu=False)
            self._backend = "easyocr"
        except Exception:
            import pytesseract  # noqa: F401  (import check only)
            self._backend = "pytesseract"

    @staticmethod
    def _preprocess(image: np.ndarray) -> np.ndarray:
        """Basic preprocessing: grayscale + contrast boost, per the
        guide's 'OCR reads incorrectly' troubleshooting section --
        helps with blur, tilted text and low contrast."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        gray = cv2.equalizeHist(gray)
        gray = cv2.medianBlur(gray, 3)
        return gray

    def read_text(self, image: np.ndarray) -> List[Dict]:
        self._ensure_loaded()
        processed = self._preprocess(image)

        if self._backend == "easyocr":
            results = self._reader.readtext(processed)
            return [
                {"text": text, "confidence": round(float(conf), 3)}
                for (_box, text, conf) in results
                if text.strip()
            ]

        import pytesseract
        from pytesseract import Output
        data = pytesseract.image_to_data(processed, output_type=Output.DICT)
        out = []
        for i, text in enumerate(data["text"]):
            if not text.strip():
                continue
            conf_raw = data["conf"][i]
            conf = float(conf_raw) / 100.0 if str(conf_raw) not in ("-1", "") else 0.0
            out.append({"text": text.strip(), "confidence": round(max(conf, 0.0), 3)})
        return out

    def read_text_joined(self, image: np.ndarray) -> str:
        """Convenience helper for the communication/TTS pipeline: one
        clean string instead of a list of word-level boxes."""
        pieces = self.read_text(image)
        return " ".join(p["text"] for p in pieces).strip()


ocr_service = OCRService()
