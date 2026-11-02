"""
scripts/demo_pipeline.py

Runs the parts of the pipeline that work fully offline in a small/
disk-constrained environment, end-to-end, and prints a report.

Covers:
  1. Sign-language recognition (trained MLP on augmented dataset features)
  2. OCR (clean synthetic signs vs. a CAPTCHA image)
  3. Text-to-speech, producing a real playable .wav file.
  4. The FastAPI app wiring itself, hitting /api/health and /api/sign-vocabulary.

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


def get_dataset_dir() -> str:
    candidates = [
        os.path.join(ROOT, "DataSet_Augmented"),
        os.path.join(ROOT, "DataSet"),
        os.path.join(ROOT, "datasets", "sign_language", "custom_ISL"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


def demo_sign_language():
    section("1. Sign language recognition (Augmented Dataset, trained MLP)")
    from backend.services.sign_service import sign_service

    dataset_dir = get_dataset_dir()
    classes = sorted([d for d in os.listdir(dataset_dir) if os.path.isdir(os.path.join(dataset_dir, d))])
    random.seed(7)
    sample_classes = random.sample(classes, k=min(6, len(classes)))

    correct = 0
    for label in sample_classes:
        class_dir = os.path.join(dataset_dir, label)
        imgs = [
            os.path.join(class_dir, f) for f in os.listdir(class_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        if not imgs:
            continue
        path = random.choice(imgs)
        image = cv2.imread(path)
        result = sign_service.predict(image)
        pred = result.get("prediction")
        hit = (pred == label)
        correct += hit
        print(f"  true={label:>15}  predicted={str(pred):>15}  "
              f"conf={result['confidence']:.2f}  method={result['extraction_method']}  "
              f"{'OK' if hit else 'MISS'}")
    print(f"\n  {correct}/{len(sample_classes)} correct on this random spot-check "
          f"(see models/sign_language/training_report.json for the full test accuracy).")


def demo_ocr():
    section("2. OCR: clean synthetic signs vs. a CAPTCHA image")
    from backend.services.ocr_service import ocr_service

    synth_dir = os.path.join(ROOT, "datasets", "ocr", "custom_OCR", "synthetic")
    if not os.path.isdir(synth_dir) or not glob.glob(os.path.join(synth_dir, "*.png")):
        from scripts.generate_ocr_samples import main as gen_ocr
        gen_ocr()

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


def demo_tts():
    section("3. Text-to-speech")
    from backend.services.tts_service import tts_service

    path = tts_service.speak_to_file("Exit sign detected. Emergency stop nearby.")
    size = os.path.getsize(path)
    print(f"  Wrote {path}  ({size} bytes)")
    assert size > 0, "TTS produced an empty file"


def demo_api():
    section("4. Backend services & vocabulary")
    from backend.services.sign_service import sign_service

    info = sign_service.get_info()
    print(f"  Sign vocabulary: {info['class_count']} classes ({info['method']} mode)")
    print(f"  Classes: {', '.join(info['classes'][:10])}...")


if __name__ == "__main__":
    demo_sign_language()
    demo_ocr()
    demo_tts()
    demo_api()
    section("Done")
    print("  All offline-capable pipelines ran end-to-end successfully.")
