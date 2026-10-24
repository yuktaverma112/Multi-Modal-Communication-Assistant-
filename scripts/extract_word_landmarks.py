"""
scripts/extract_word_landmarks.py

Turns short video clips of whole WORD signs into fixed-length feature
vectors for training a word-level classifier -- the sequel to
extract_isl_landmarks.py (which handles single LETTERS from static
images). A word sign is a short motion, not one held pose, so instead
of one frame's features we sample a clip's frames and POOL them into
a fixed-size descriptor (mean / std / min / max across frames, plus a
first-to-last delta capturing overall motion direction). This keeps
word recognition on the same lightweight sklearn MLP architecture
already used for letters, rather than requiring a new deep-learning
framework (e.g. an LSTM) just to get a working baseline.

INPUT video folder layout (you build this yourself -- see below):
    datasets/sign_language/word_clips/
        hello/
            clip1.mp4
            clip2.mp4
        water/
            clip1.mp4
            ...
    One subfolder per gloss (word), any number of short clips inside.

Where do clips come from? This project ships WLASL100 *metadata* only
(datasets/sign_language/WLASL100/) -- 100 English glosses and ~2,000
video URLs, but no actual video files. Two ways to get real clips:

  1. Run scripts/download_wlasl_clips.py on a machine with normal
     internet access. This sandbox's egress proxy blocks every WLASL
     video host -- confirmed directly: YouTube, aslbricks.org, Yale's
     ASL sign bank, aslpro.com, handspeak.com and the rest all fail to
     resolve from here. Your own machine will not have this problem.
  2. Record your own short clips of real signs -- genuinely the better
     option if your target is Indian Sign Language, since WLASL is
     American Sign Language (same limitation already noted for the
     custom_ISL letter dataset).

OUTPUT: models/sign_language/word_features.npz (X, y, feature_dim,
extraction_method, classes) -- what scripts/train_word_model.py then
trains on. Mirrors extract_isl_landmarks.py's output shape/contract.
"""
from __future__ import annotations

import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.utils.preprocessing import extract_features  # noqa: E402

DEFAULT_CLIPS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "datasets", "sign_language", "word_clips"
)
DEFAULT_OUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "models", "sign_language", "word_features.npz"
)

MAX_FRAMES_SAMPLED = 24   # cap per clip, for speed and consistency
MIN_VALID_FRAMES = 3      # clips with fewer detected-hand frames are skipped


def sample_frame_indices(total_frames: int, max_frames: int) -> list[int]:
    if total_frames <= max_frames:
        return list(range(total_frames))
    # evenly spaced sample across the whole clip, not just the start
    return list(np.linspace(0, total_frames - 1, max_frames).astype(int))


def pool_clip_features(frame_vectors: list[np.ndarray]) -> np.ndarray:
    """Collapse a variable-length list of per-frame feature vectors
    into one fixed-length descriptor: mean, std, min, max across the
    clip (captures the range of hand shapes/positions seen), plus a
    first-to-last delta (captures net motion direction)."""
    arr = np.stack(frame_vectors)  # (n_frames, D)
    mean = arr.mean(axis=0)
    std = arr.std(axis=0)
    mn = arr.min(axis=0)
    mx = arr.max(axis=0)
    delta = arr[-1] - arr[0]
    return np.concatenate([mean, std, mn, mx, delta])


def extract_clip(video_path: str) -> tuple[np.ndarray | None, str | None]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None, None

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    indices = set(sample_frame_indices(total, MAX_FRAMES_SAMPLED)) if total else None

    frame_vectors = []
    method = None
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if indices is None or i in indices:
            vec, m = extract_features(frame, prefer_landmarks=True)
            frame_vectors.append(vec)
            method = method or m
        i += 1
    cap.release()

    if len(frame_vectors) < MIN_VALID_FRAMES:
        return None, None
    return pool_clip_features(frame_vectors), method


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clips_dir", default=DEFAULT_CLIPS_DIR)
    parser.add_argument("--out", default=DEFAULT_OUT_PATH)
    args = parser.parse_args()

    if not os.path.isdir(args.clips_dir):
        print(f"No clips directory found at {args.clips_dir}")
        print("Create it with one subfolder per word, each containing short video clips. See this script's docstring.")
        sys.exit(1)

    glosses = sorted(d for d in os.listdir(args.clips_dir) if os.path.isdir(os.path.join(args.clips_dir, d)))
    if not glosses:
        print(f"{args.clips_dir} exists but has no word subfolders yet.")
        sys.exit(1)

    X, y = [], []
    overall_method = None
    for gloss in glosses:
        gloss_dir = os.path.join(args.clips_dir, gloss)
        clips = [f for f in os.listdir(gloss_dir) if f.lower().endswith((".mp4", ".webm", ".mov", ".avi"))]
        if not clips:
            continue
        kept = 0
        for clip in clips:
            vec, method = extract_clip(os.path.join(gloss_dir, clip))
            if vec is None:
                print(f"  [skip] {gloss}/{clip}: fewer than {MIN_VALID_FRAMES} frames with a detectable hand")
                continue
            X.append(vec)
            y.append(gloss)
            overall_method = overall_method or method
            kept += 1
        print(f"{gloss}: {kept}/{len(clips)} clips usable")

    if not X:
        print("No usable clips found across any word folder. Nothing to save.")
        sys.exit(1)

    X = np.stack(X)
    y = np.array(y)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    np.savez(args.out, X=X, y=y, extraction_method=overall_method, classes=sorted(set(y.tolist())))

    print(f"\nSaved {X.shape[0]} clip descriptors ({X.shape[1]}-d each, method={overall_method}) across {len(set(y.tolist()))} words -> {args.out}")
    print("Next: python scripts/train_word_model.py")


if __name__ == "__main__":
    main()
