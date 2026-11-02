"""
scripts/extract_isl_landmarks.py

Walks the dataset directory (<LABEL>/*.jpg, *.jpeg, *.png), extracts a feature
vector per image (MediaPipe hand landmarks preferred -- 63 dimensions,
background-invariant; offline HOG fallback only if MediaPipe model is missing),
and saves everything to models/sign_language/isl_features.npz for training.

Usage:
    python scripts/extract_isl_landmarks.py
    python scripts/extract_isl_landmarks.py --method landmarks
    python scripts/extract_isl_landmarks.py --method hog
"""
import os
import sys
import glob
import argparse
import numpy as np
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.utils.preprocessing import (  # noqa: E402
    read_image,
    extract_features,
    extract_hand_landmarks,
    extract_hog_features,
    _landmarker_unavailable,
    MEDIAPIPE_MODEL_PATH,
)


def get_default_dataset_dir() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    candidates = [
        os.path.join(root, "DataSet_Augmented"),
        os.path.join(root, "DataSet"),
        os.path.join(root, "datasets", "sign_language", "custom_ISL"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


def find_class_images(class_dir: str) -> list:
    images = []
    valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    if not os.path.isdir(class_dir):
        return images
    for f in os.listdir(class_dir):
        ext = os.path.splitext(f)[1].lower()
        if ext in valid_exts:
            images.append(os.path.join(class_dir, f))
    return sorted(images)


def main():
    parser = argparse.ArgumentParser(description="Extract landmarks / HOG features from sign dataset.")
    parser.add_argument(
        "--dataset-dir", "-d",
        type=str,
        default=get_default_dataset_dir(),
        help="Path to dataset directory (defaults to DataSet_Augmented or DataSet)",
    )
    parser.add_argument(
        "--out-path", "-o",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "models", "sign_language", "isl_features.npz"),
        help="Output path for .npz features",
    )
    parser.add_argument(
        "--method", "-m",
        choices=["auto", "landmarks", "hog"],
        default="auto",
        help="Feature extraction method. 'landmarks' (63-d, background-invariant) or 'hog' (1764-d)",
    )
    args = parser.parse_args()

    dataset_dir = os.path.abspath(args.dataset_dir)
    out_path = os.path.abspath(args.out_path)

    if not os.path.isdir(dataset_dir):
        print(f"Error: dataset directory not found: {dataset_dir}")
        sys.exit(1)

    labels_dirs = sorted(
        d for d in os.listdir(dataset_dir)
        if os.path.isdir(os.path.join(dataset_dir, d))
    )
    print("=" * 70)
    print("FEATURE EXTRACTION PIPELINE")
    print("=" * 70)
    print(f"Dataset:         {dataset_dir}")
    print(f"Output Path:     {out_path}")
    print(f"Target Method:   {args.method}")
    print(f"Classes Found:   {len(labels_dirs)} ({', '.join(labels_dirs[:8])}...)")
    print("-" * 70)

    use_landmarks = (args.method == "landmarks") or (args.method == "auto" and os.path.exists(MEDIAPIPE_MODEL_PATH))

    X, y = [], []
    skipped = 0
    per_class_counts = Counter()

    for label in labels_dirs:
        class_path = os.path.join(dataset_dir, label)
        image_paths = find_class_images(class_path)
        for path in image_paths:
            try:
                img = read_image(path)
            except Exception:
                skipped += 1
                continue

            if use_landmarks:
                feats = extract_hand_landmarks(img)
                if feats is None:
                    # If landmarks not detected in this particular frame, skip it
                    # to keep the training set pure 63-d background-invariant joints
                    skipped += 1
                    continue
                X.append(feats)
                y.append(label)
                per_class_counts[label] += 1
            else:
                feats = extract_hog_features(img)
                X.append(feats)
                y.append(label)
                per_class_counts[label] += 1

    method_used = "landmarks" if use_landmarks else "hog"
    print(f"Successfully extracted {len(X)} feature vectors (method: {method_used}).")
    print(f"Skipped {skipped} images without valid detection.")
    print("-" * 70)
    print("Per-class samples with valid features:")
    for label in labels_dirs:
        print(f"  {label:>16}: {per_class_counts[label]:>3} samples")
    print("=" * 70)

    X = np.array(X, dtype=np.float32)
    y = np.array(y)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    np.savez(out_path, X=X, y=y, method=method_used)
    print(f"Saved feature dataset to {out_path} (X shape={X.shape}, y={len(y)})")


if __name__ == "__main__":
    main()
