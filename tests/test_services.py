"""
tests/test_services.py

Lightweight tests covering the pieces that run fully offline in any
environment (no ultralytics/whisper download required). Run with:

    pytest -q
"""
import glob
import io
import os
import subprocess
import sys
import wave

import cv2
# pyrefly: ignore[missing-import]
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _get_sample_sign_image() -> str:
    """Finds a valid sample sign image from DataSet_Augmented or DataSet."""
    candidates = [
        os.path.join(ROOT, "DataSet_Augmented", "A"),
        os.path.join(ROOT, "DataSet", "A"),
        os.path.join(ROOT, "datasets", "sign_language", "custom_ISL", "A"),
    ]
    for d in candidates:
        if os.path.isdir(d):
            imgs = sorted([
                os.path.join(d, f) for f in os.listdir(d)
                if f.lower().endswith((".jpg", ".jpeg", ".png"))
            ])
            if imgs:
                return imgs[0]
    raise FileNotFoundError("No sample sign image found in dataset directories.")


def test_whisper_ffmpeg_is_available_without_system_install():
    from backend.services.whisper_service import _ensure_ffmpeg_available

    _ensure_ffmpeg_available()
    result = subprocess.run(
        ["ffmpeg", "-version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "ffmpeg version" in result.stdout.lower()


def test_preprocessing_hog_features_shape():
    from backend.utils.preprocessing import extract_hog_features, read_image

    sample = _get_sample_sign_image()
    img = read_image(sample)
    feats = extract_hog_features(img)
    assert feats.ndim == 1
    assert feats.shape[0] > 0


def test_sign_service_predicts_known_class():
    from backend.services.sign_service import sign_service

    sample = _get_sample_sign_image()
    img = cv2.imread(sample)
    result = sign_service.predict(img)
    assert result["prediction"] is not None
    assert 0.0 <= result["confidence"] <= 1.0
    assert len(result["top_k"]) >= 1
    assert len(result["hand_landmarks"]) in (0, 21)
    assert all(len(point) == 2 for point in result["hand_landmarks"])


def test_ocr_service_reads_clean_synthetic_sign():
    from backend.services.ocr_service import ocr_service

    path = os.path.join(ROOT, "datasets", "ocr", "custom_OCR", "synthetic", "sample_00.png")
    if not os.path.exists(path):
        pytest.skip("run scripts/generate_ocr_samples.py first")
    img = cv2.imread(path)
    text = ocr_service.read_text_joined(img)
    assert "EXIT" in text.upper()


def test_tts_service_writes_nonempty_wav(tmp_path):
    from fastapi.testclient import TestClient
    from backend.config import TTS_OUTPUT_DIR
    from backend.main import app
    from backend.services.tts_service import tts_service

    path = tts_service.speak_to_file("test message")
    try:
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0
        assert os.path.dirname(os.path.abspath(path)) == os.path.abspath(TTS_OUTPUT_DIR)
        with TestClient(app) as client:
            response = client.get(f"/media/{os.path.basename(path)}")
            assert response.status_code == 200
            assert response.content[:4] == b"RIFF"
    finally:
        if os.path.exists(path):
            os.remove(path)


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

    sample = _get_sample_sign_image()
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

    sample = _get_sample_sign_image()
    with TestClient(app) as client:
        with open(sample, "rb") as f:
            r = client.post("/api/detect-object", files={"file": ("photo.jpg", f, "image/jpeg")})
        assert r.status_code == 200  # our envelope -- real status is in the body
        body = r.json()
        assert body["code"] in (200, 503)
        if body["code"] == 200:
            assert "description" in body["data"]


def test_word_model_status_reflects_reality():
    """No separate WLASL video model ships with this project (see README) -- this
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


def test_sign_vocabulary_serves_augmented_classes():
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        r = client.get("/api/sign-vocabulary")
        assert r.status_code == 200
        classes = r.json()["data"]["classes"]
        assert len(classes) == 21
        assert "A" in classes
        assert "Book" in classes
        assert "how are you" in classes


def test_hearing_and_communication_actions_complete(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.services.sign_service import sign_service
    from backend.services.whisper_service import whisper_service

    audio_file = io.BytesIO()
    with wave.open(audio_file, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 1600)
    audio_bytes = audio_file.getvalue()
    image_path = _get_sample_sign_image()
    with open(image_path, "rb") as image_file:
        image_bytes = image_file.read()

    monkeypatch.setattr(
        whisper_service,
        "transcribe",
        lambda path, language="en": {"text": " hello there ", "language": language},
    )
    monkeypatch.setattr(
        sign_service,
        "predict",
        lambda image: {
            "prediction": "A",
            "confidence": 0.95,
            "top_k": [{"label": "A", "confidence": 0.95}],
            "extraction_method": "landmarks",
            "hand_landmarks": [],
        },
    )

    generated_audio = []
    try:
        with TestClient(app) as client:
            caption = client.post(
                "/api/speech-to-text",
                files={"file": ("speech.wav", audio_bytes, "audio/wav")},
            )
            assert caption.json()["data"]["text"] == " hello there "

            shared_caption = client.post(
                "/api/communicate/hearing-to-deaf",
                files={"file": ("speech.wav", audio_bytes, "audio/wav")},
            )
            assert shared_caption.json()["data"]["text"] == " hello there "

            sign = client.post(
                "/api/communicate/deaf-to-hearing",
                files={"file": ("sign.jpg", image_bytes, "image/jpeg")},
            )
            assert sign.json()["data"]["text"] == "A"
            sign_audio = sign.json()["data"]["audio_path"]
            generated_audio.append(sign_audio)
            assert client.get(f"/media/{os.path.basename(sign_audio)}").status_code == 200

            typed = client.post("/api/communicate/type-to-hearing", data={"text": "  Need help  "})
            assert typed.json()["data"]["text"] == "Need help"
            typed_audio = typed.json()["data"]["audio_path"]
            generated_audio.append(typed_audio)
            assert client.get(f"/media/{os.path.basename(typed_audio)}").status_code == 200
            speech_history = client.get("/api/history?modality=speech").json()["data"]
            assert any(row["result_text"] == "Need help" for row in speech_history)

            blank = client.post("/api/communicate/type-to-hearing", data={"text": "   "})
            assert blank.json()["code"] == 400
    finally:
        for path in generated_audio:
            if os.path.exists(path):
                os.remove(path)


def test_recognize_word_without_a_trained_model_fails_clearly():
    """Must return a clear, actionable error -- never a silent wrong
    guess -- when no word model has been trained yet."""
    from fastapi.testclient import TestClient
    from backend.main import app

    sample = _get_sample_sign_image()
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
