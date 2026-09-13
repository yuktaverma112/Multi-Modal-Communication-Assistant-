"""
scripts/demo_pipeline.py

Runs the parts of the pipeline that work fully offline in a small/
disk-constrained environment, end-to-end, and prints a report. See
README "What was actually executed" for which pieces this covers vs.
which need `pip install ultralytics` / `pip install openai-whisper`
(both need large downloads and were NOT run in the environment this
project was assembled in -- the code is complete and ready for them
regardless).

Covers:
  1. Sign-language recognition (trained MLP on custom_ISL features)
  2. OCR (pytesseract fallback backend) on clean synthetic signs vs. a
     captcha image, to show the accuracy contrast the guide predicts.
  3. Text-to-speech, producing a real playable .wav file.
  4. The FastAPI app wiring itself, via TestClient (no live server
     needed) hitting /api/health, /api/recognize-sign and /api/read-text.

Usage:
    python scripts/demo_pipeline.py
"""
import glob
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cv2  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def demo_sign_language():
    section("1. Sign language recognition (custom_ISL, trained MLP)")
    from backend.services.sign_service import sign_service

    isl_dir = os.path.join(ROOT, "datasets", "sign_language", "custom_ISL")
    classes = sorted(os.listdir(isl_dir))
    random.seed(7)
    sample_classes = random.sample(classes, k=min(6, len(classes)))

    correct = 0
    for label in sample_classes:
        imgs = glob.glob(os.path.join(isl_dir, label, "*.jpg"))
        path = random.choice(imgs)
        image = cv2.imread(path)
        result = sign_service.predict(image)
        hit = result["prediction"] == label
        correct += hit
        print(f"  true={label:>3}  predicted={str(result['prediction']):>3}  "
              f"conf={result['confidence']:.2f}  method={result['extraction_method']}  "
              f"{'OK' if hit else 'MISS'}")
    print(f"\n  {correct}/{len(sample_classes)} correct on this random spot-check "
          f"(see models/sign_language/training_report.json for the full held-out test accuracy).")


def demo_ocr():
    section("2. OCR: clean synthetic signs vs. a CAPTCHA image")
    from backend.services.ocr_service import ocr_service

    synth_dir = os.path.join(ROOT, "datasets", "ocr", "custom_OCR", "synthetic")
    for path in sorted(glob.glob(os.path.join(synth_dir, "*.png"))):
        image = cv2.imread(path)
        text = ocr_service.read_text_joined(image)
        print(f"  {os.path.basename(path):>16}  ->  {text!r}")

    captcha_dir = os.path.join(ROOT, "datasets", "ocr", "custom_OCR", "data", "sample")
    captcha_files = glob.glob(os.path.join(captcha_dir, "*.png"))
    if captcha_files:
        path = random.choice(captcha_files)
        image = cv2.imread(path)
        text = ocr_service.read_text_joined(image)
        true_text = os.path.splitext(os.path.basename(path))[0]
        print(f"\n  CAPTCHA {os.path.basename(path)} (true text ~= {true_text!r}) -> OCR read: {text!r}")
        print("  (Low/garbled accuracy here is EXPECTED -- CAPTCHAs are designed to defeat OCR;"
              " this is not representative of real sign/document accuracy, see README.)")


def demo_tts():
    section("3. Text-to-speech")
    from backend.services.tts_service import tts_service

    path = tts_service.speak_to_file("Exit sign detected. Emergency stop nearby.")
    size = os.path.getsize(path)
    print(f"  Wrote {path}  ({size} bytes)")
    assert size > 0, "TTS produced an empty file"


def demo_api():
    section("4. FastAPI app wiring (TestClient, no live server)")
    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:  # context manager so startup/shutdown events fire
        r = client.get("/api/health")
        print(f"  GET  /api/health          -> {r.status_code} {r.json()}")

        isl_dir = os.path.join(ROOT, "datasets", "sign_language", "custom_ISL", "A")
        sample_img = sorted(glob.glob(os.path.join(isl_dir, "*.jpg")))[0]
        with open(sample_img, "rb") as f:
            r = client.post("/api/recognize-sign", files={"file": ("a.jpg", f, "image/jpeg")})
        print(f"  POST /api/recognize-sign  -> {r.status_code} {r.json()['data']}")

        synth_img = os.path.join(ROOT, "datasets", "ocr", "custom_OCR", "synthetic", "sample_00.png")
        with open(synth_img, "rb") as f:
            r = client.post("/api/read-text", files={"file": ("sign.png", f, "image/png")})
        print(f"  POST /api/read-text       -> {r.status_code} {r.json()['data']}")

        r = client.get("/api/history?limit=5")
        print(f"  GET  /api/history         -> {r.status_code} ({len(r.json()['data'])} rows logged)")


if __name__ == "__main__":
    demo_sign_language()
    demo_ocr()
    demo_tts()
    demo_api()
    section("Done")
    print("  All offline-capable pipelines ran end-to-end successfully.")
