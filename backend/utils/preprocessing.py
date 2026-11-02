"""
backend/utils/preprocessing.py

Image preprocessing helpers shared across services.

Sign-language feature extraction
---------------------------------
Two extraction strategies are provided:

1. `extract_hand_landmarks()`  -> MediaPipe Hand Landmarker (Tasks API).
   This is the RECOMMENDED method for production. It returns 63 numbers
   per hand (21 landmarks x [x, y, z]), normalized relative to the wrist,
   which is what the project guide's MLP (Input 63 -> ... -> Softmax)
   expects.

   The first time you use it, MediaPipe needs to download a small
   `hand_landmarker.task` model file. If your machine has no internet
   access at that moment (as in some sandboxed/offline environments),
   this call will raise, and the caller should fall back to option 2.

2. `extract_hog_features()` -> classic HOG descriptor computed directly
   on the cropped hand image with OpenCV. Works fully offline, no model
   download needed. It is a weaker signal than hand landmarks (it does
   not explicitly encode finger joints) but is enough to get a working
   end-to-end pipeline while you don't have MediaPipe's model file yet.

`extract_features()` is the function the rest of the project should call:
it tries (1) and transparently falls back to (2), and records which
method actually produced the feature vector so training/inference stay
consistent.
"""

from __future__ import annotations

import os
import cv2
import numpy as np

MEDIAPIPE_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "models", "mediapipe", "hand_landmarker.task"
)
MEDIAPIPE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

HOG_WIN_SIZE = (128, 128)
HOG_FEATURE_DIM = None  # computed lazily from the descriptor

_hog = cv2.HOGDescriptor(
    _winSize=HOG_WIN_SIZE,
    _blockSize=(32, 32),
    _blockStride=(16, 16),
    _cellSize=(16, 16),
    _nbins=9,
)

_landmarker = None
_landmarker_unavailable = False


def _try_download_mediapipe_model() -> bool:
    """Best-effort download of the MediaPipe hand landmark model.
    Returns True if the model file is present after this call."""
    if os.path.exists(MEDIAPIPE_MODEL_PATH):
        return True
    os.makedirs(os.path.dirname(MEDIAPIPE_MODEL_PATH), exist_ok=True)
    try:
        import urllib.request
        urllib.request.urlretrieve(MEDIAPIPE_MODEL_URL, MEDIAPIPE_MODEL_PATH)
        return os.path.exists(MEDIAPIPE_MODEL_PATH)
    except Exception:
        return False


def _get_landmarker():
    """Lazily create a MediaPipe HandLandmarker. Returns None if it
    cannot be created (no internet / model missing)."""
    global _landmarker, _landmarker_unavailable
    if _landmarker is not None:
        return _landmarker
    if _landmarker_unavailable:
        return None

    if not _try_download_mediapipe_model():
        _landmarker_unavailable = True
        return None

    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        base_options = mp_python.BaseOptions(model_asset_path=MEDIAPIPE_MODEL_PATH)
        options = mp_vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=2,
            min_hand_detection_confidence=0.15,
            min_hand_presence_confidence=0.15,
            min_tracking_confidence=0.15,
        )
        _landmarker = mp_vision.HandLandmarker.create_from_options(options)
        return _landmarker
    except Exception:
        _landmarker_unavailable = True
        return None


def extract_hand_landmarks(image: np.ndarray) -> np.ndarray | None:
    """Return a 63-d feature vector (21 landmarks x xyz) normalized
    relative to the wrist, or None if no hand was detected / MediaPipe
    is unavailable."""
    points = extract_hand_landmark_points(image)
    if points is None:
        return None

    coords = points.copy()
    coords -= coords[0].copy()
    max_val = np.max(np.abs(coords)) or 1.0
    return (coords / max_val).flatten()


def extract_hand_landmark_points(image: np.ndarray) -> np.ndarray | None:
    """Return the detected hand's 21 image-relative landmarks for visualization."""
    import mediapipe as mp

    landmarker = _get_landmarker()
    if landmarker is None:
        return None

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect(mp_image)

    if not result.hand_landmarks:
        return None

    if len(result.hand_landmarks) > 1:
        # Pick the most prominent / largest hand in the detection area
        lm = max(
            result.hand_landmarks,
            key=lambda h: (max(p.x for p in h) - min(p.x for p in h)) * (max(p.y for p in h) - min(p.y for p in h))
        )
    else:
        lm = result.hand_landmarks[0]
    return np.array([[p.x, p.y, p.z] for p in lm], dtype=np.float32)


def extract_hog_features(image: np.ndarray) -> np.ndarray:
    """Offline fallback: HOG descriptor on the resized image. Always
    succeeds (no hand-detection step), so it's used when MediaPipe's
    model file cannot be downloaded."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    resized = cv2.resize(gray, HOG_WIN_SIZE)
    features = _hog.compute(resized)
    return features.flatten()


def extract_features(
    image: np.ndarray,
    prefer_landmarks: bool = True,
    include_landmarks: bool = False,
):
    """Unified entry point used by both training scripts and the live
    sign_service. Returns (feature_vector, method) where method is
    'landmarks' or 'hog'. When requested, also returns image-relative
    hand landmarks for the live recognition diagram."""
    points = None
    if prefer_landmarks:
        try:
            points = extract_hand_landmark_points(image)
            feats = None
            if points is not None:
                coords = points.copy()
                coords -= coords[0].copy()
                max_val = np.max(np.abs(coords)) or 1.0
                feats = (coords / max_val).flatten()
            if feats is not None:
                if include_landmarks:
                    return feats, "landmarks", points
                return feats, "landmarks"
        except Exception:
            pass
    feats = extract_hog_features(image)
    if include_landmarks:
        return feats, "hog", points
    return feats, "hog"


def read_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    return img


def decode_image_bytes(data: bytes) -> np.ndarray:
    """Decode raw uploaded image bytes (from a FastAPI UploadFile) into
    a BGR numpy array, as used by every service in this project."""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image bytes -- unsupported or corrupt image.")
    return img
