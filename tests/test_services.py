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


def test_recognize_sign_log_false_skips_history():
    """The Live Translate polling loop passes log=false so it doesn't
    flood /api/history with a row every ~400ms."""
    from fastapi.testclient import TestClient
    from backend.main import app

    sample = sorted(glob.glob(os.path.join(ROOT, "datasets", "sign_language", "custom_ISL", "A", "*.jpg")))[0]
    with TestClient(app) as client:
        before = len(client.get("/api/history").json()["data"])
        with open(sample, "rb") as f:
            r = client.post("/api/recognize-sign?log=false", files={"file": ("a.jpg", f, "image/jpeg")})
        assert r.status_code == 200
        after = len(client.get("/api/history").json()["data"])
        assert after == before  # unchanged -- the poll was not logged


def test_detect_object_degrades_cleanly_or_works():
    """Object detection needs ultralytics installed (+ a one-time YOLO
    weight download). This must never 500-crash either way -- a clean
    200 with real detections if it's available, or a clean 503 with an
    actionable message if it isn't."""
    from fastapi.testclient import TestClient
    from backend.main import app

    sample = os.path.join(ROOT, "datasets", "ocr", "custom_OCR", "synthetic", "sample_00.png")
    with TestClient(app) as client:
        with open(sample, "rb") as f:
            r = client.post("/api/detect-object", files={"file": ("photo.png", f, "image/png")})
        assert r.status_code == 200  # our envelope -- real status is in the body
        body = r.json()
        assert body["code"] in (200, 503)
        if body["code"] == 200:
            assert "description" in body["data"]


def test_word_model_status_reflects_reality():
    """No word-level model ships with this project (see README) -- this
    must report trained:false, not silently claim otherwise."""
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        r = client.get("/api/word-model-status")
        assert r.status_code == 200
        assert r.json()["data"]["trained"] is False


def test_word_vocabulary_serves_the_staged_glosses():
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        r = client.get("/api/word-vocabulary")
        assert r.status_code == 200
        glosses = r.json()["data"]["glosses"]
        assert len(glosses) == 100
        assert "help" in glosses


def test_recognize_word_without_a_trained_model_fails_clearly():
    """Must return a clear, actionable error -- never a silent wrong
    guess -- when no word model has been trained yet."""
    from fastapi.testclient import TestClient
    from backend.main import app

    sample = sorted(glob.glob(os.path.join(ROOT, "datasets", "sign_language", "custom_ISL", "A", "*.jpg")))[0]
    with TestClient(app) as client:
        with open(sample, "rb") as f:
            r = client.post("/api/recognize-word", files={"file": ("clip.webm", f, "video/webm")})
        assert r.status_code == 200  # our {code, message, data} envelope, not an HTTP error
        body = r.json()
        assert body["code"] == 503
        assert "not been trained" in body["message"] or "has been trained" in body["message"]


def test_history_log_endpoint_records_a_committed_event():
    """Live Translate logs one meaningful event (a spoken sentence, a
    finished caption session) via this endpoint instead of every poll."""
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        r = client.post("/api/history/log", data={"modality": "sign_language", "text": "HELLO", "confidence": "0.9"})
        assert r.status_code == 200
        rows = client.get("/api/history?modality=sign_language").json()["data"]
        assert any(row["result_text"] == "HELLO" for row in rows)
