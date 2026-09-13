"""
tests/test_services.py

Lightweight tests covering the pieces that run fully offline in any
environment (no ultralytics/whisper download required). Run with:

    pytest -q
"""
import glob
import os
import sys

import cv2
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_preprocessing_hog_features_shape():
    from backend.utils.preprocessing import extract_hog_features, read_image

    sample = sorted(glob.glob(os.path.join(ROOT, "datasets", "sign_language", "custom_ISL", "A", "*.jpg")))[0]
    img = read_image(sample)
    feats = extract_hog_features(img)
    assert feats.ndim == 1
    assert feats.shape[0] > 0


def test_sign_service_predicts_known_class():
    from backend.services.sign_service import sign_service

    sample = sorted(glob.glob(os.path.join(ROOT, "datasets", "sign_language", "custom_ISL", "A", "*.jpg")))[0]
    img = cv2.imread(sample)
    result = sign_service.predict(img)
    assert result["prediction"] is not None
    assert 0.0 <= result["confidence"] <= 1.0
    assert len(result["top_k"]) == 3


def test_ocr_service_reads_clean_synthetic_sign():
    from backend.services.ocr_service import ocr_service

    path = os.path.join(ROOT, "datasets", "ocr", "custom_OCR", "synthetic", "sample_00.png")
    if not os.path.exists(path):
        pytest.skip("run scripts/generate_ocr_samples.py first")
    img = cv2.imread(path)
    text = ocr_service.read_text_joined(img)
    assert "EXIT" in text.upper()


def test_tts_service_writes_nonempty_wav(tmp_path):
    from backend.services.tts_service import tts_service

    path = tts_service.speak_to_file("test message")
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0


def test_api_health():
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "up"
