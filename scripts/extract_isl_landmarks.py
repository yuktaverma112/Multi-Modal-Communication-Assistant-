"""
scripts/extract_isl_landmarks.py

Walks datasets/sign_language/custom_ISL/<LABEL>/*.jpg, extracts a feature
vector per image (MediaPipe hand landmarks if available, otherwise an
offline HOG fallback -- see backend/utils/preprocessing.py), and saves
everything to models/sign_language/isl_features.npz for training.

Usage:
    python scripts/extract_isl_landmarks.py
"""
import os
import sys
import glob
import numpy as np
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.utils.preprocessing import read_image, extract_features  # noqa: E402

DATASET_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets", "sign_language", "custom_ISL")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "sign_language", "isl_features.npz")


def main():
    labels_dirs = sorted(
        d for d in os.listdir(DATASET_DIR)
        if os.path.isdir(os.path.join(DATASET_DIR, d))
    )
    print(f"Found {len(labels_dirs)} classes: {labels_dirs}")

    X, y, methods = [], [], []
    skipped = 0

    for label in labels_dirs:
        image_paths = sorted(glob.glob(os.path.join(DATASET_DIR, label, "*.jpg")))
        for path in image_paths:
            try:
                img = read_image(path)
            except ValueError:
                skipped += 1
                continue
            feats, method = extract_features(img, prefer_landmarks=True)
            if feats is None:
                skipped += 1
                continue
            X.append(feats)
            y.append(label)
            methods.append(method)

    method_counts = Counter(methods)
    print(f"Extracted {len(X)} feature vectors, skipped {skipped} unreadable/undetected images.")
    print(f"Extraction method breakdown: {dict(method_counts)}")

    # All vectors must have the same length to stack; if a mix of
    # landmarks (63-d) and HOG (variable-d) ever happens, force HOG-only
    # for consistency (landmarks path already returns early per-image,
    # so in practice this run will be 100% one method or the other).
    lengths = {len(v) for v in X}
    if len(lengths) > 1:
        print(f"WARNING: mixed feature lengths {lengths} -- re-extracting with HOG only for consistency.")
        X = []
        y = []
        for label in labels_dirs:
            image_paths = sorted(glob.glob(os.path.join(DATASET_DIR, label, "*.jpg")))
            for path in image_paths:
                try:
                    img = read_image(path)
                except ValueError:
                    continue
                from backend.utils.preprocessing import extract_hog_features
                X.append(extract_hog_features(img))
                y.append(label)
        method_counts = Counter(["hog"] * len(X))

    X = np.array(X, dtype=np.float32)
    y = np.array(y)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    np.savez(OUT_PATH, X=X, y=y, method=list(method_counts.keys())[0] if method_counts else "unknown")
    print(f"Saved features to {OUT_PATH}  (X shape={X.shape})")


if __name__ == "__main__":
    main()
