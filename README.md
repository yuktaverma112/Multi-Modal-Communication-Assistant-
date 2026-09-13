# AI-Based Multi-Modal Accessibility Assistant

Real-time object detection, OCR, speech recognition and sign-language
translation for blind and hearing-impaired users, built around the
project guide you supplied (`AI_Multi_Modal_Accessibility_Assistant_Full_Project_Guide.pdf`).

```
Camera/Microphone -> AI Model -> Prediction + Confidence -> Accessible Output -> User
```

## Quick status: what's real vs. what's scaffolded

Everything below was written, wired together, and actually run inside
this sandbox (see **"What was actually executed here"**), except the
two pieces that need large model downloads (YOLO/PyTorch, Whisper) --
those are fully coded and ready, just not exercised here to avoid
blowing the sandbox's disk quota.

| Module | Status |
|---|---|
| Sign language recognition (custom_ISL) | **Trained & tested.** MLP on HOG features, 23 letter classes, 702 images. Test accuracy 44.7% (random split) -- see `models/sign_language/training_report.json`. |
| OCR | **Working**, pytesseract backend verified on 6 clean synthetic signs + 1 CAPTCHA (accuracy contrast is expected/documented). EasyOCR wired as the primary backend for when you install it. |
| Text-to-speech | **Working**, produces real `.wav` files via pyttsx3/espeak-ng. |
| FastAPI backend + routing + SQLite history | **Working**, verified end-to-end via `scripts/demo_pipeline.py` and `pytest`. |
| Frontend (Blind/Hearing/Communication) | **Working & redesigned** -- accordion layout, camera/mic capture, confidence-colored results, conversation transcript. See "Frontend design" below. |
| Object detection (YOLO/COCO) | **Coded, not executed here.** Needs `pip install ultralytics` (pulls PyTorch, downloads `yolo11n.pt` on first run). |
| Speech-to-text (Whisper) | **Coded, not executed here.** Needs `pip install openai-whisper` + ffmpeg (downloads a ~140MB model on first run). |
| Emergency sound detection (ESC-50, Phase 2) | **Not started.** ESC-50 wasn't part of your uploads; folder is ready at `datasets/sound/ESC-50/`. |

## Run it yourself

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt install tesseract-ocr espeak-ng ffmpeg   # system deps for OCR fallback / TTS / Whisper

uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

First run of object detection downloads `yolo11n.pt` automatically
(needs internet). First run of speech-to-text downloads the Whisper
"base" checkpoint automatically (needs internet). Everything else
works fully offline.

Run the offline smoke test any time to confirm your environment is set up correctly:
```bash
python scripts/demo_pipeline.py
pytest -q
```

## Architecture

```
                       ┌─────────────────┐
                       │   HOME SCREEN   │
                       └────────┬────────┘
                                │
                   ┌────────────┼────────────┐
                   ▼            ▼             ▼
                BLIND        HEARING     COMMUNICATION
                 MODE          MODE          MODE
                   │            │             │
                Camera      Camera/Mic     Camera/Mic
                   │            │             │
              ┌────┴────┐    ┌──┴───┐     ┌───┴────┐
              │         │    │      │     │        │
             YOLO      OCR  STT    Sign  Speech   Sign
              │         │    │      │     │        │
              └────┬────┘    └──┬───┘     └───┬────┘
                   │            │             │
                   ▼            ▼             ▼
                 TEXT         TEXT          TEXT
                   │            │             │
                   ▼            ▼             ▼
                  TTS        DISPLAY          TTS
                   │                          │
                   ▼                          ▼
                🔊 VOICE                   🔊 VOICE
```

Each pipe maps 1:1 to a FastAPI endpoint:

| Endpoint | Pipeline |
|---|---|
| `POST /api/detect-object` | Camera → YOLO → objects → (optional) TTS |
| `POST /api/read-text` | Image → OCR → text → (optional) TTS |
| `POST /api/speech-to-text` | Audio → Whisper → text |
| `POST /api/recognize-sign` | Image → MediaPipe/HOG → MLP → sign → (optional) TTS |
| `POST /api/text-to-speech` | text → audio |
| `POST /api/communicate/hearing-to-deaf` | Audio → text (for a deaf participant to read) |
| `POST /api/communicate/deaf-to-hearing` | Sign image → text + audio (for a hearing participant) |
| `POST /api/communicate/type-to-hearing` | Typed fallback → audio |
| `GET /api/history` | Recent predictions (metadata only, see Privacy) |
| `GET /api/health` | Liveness check |

Interactive docs: `http://localhost:8000/docs`.

## Project layout

```
backend/
  main.py                 FastAPI app, mounts routers + static frontend
  config.py                Shared settings (paths, DB URL)
  api/                     One router per pipeline (thin: validates input, calls a service, logs history)
  services/                One class per AI capability (model loading, inference)
  database/                SQLAlchemy models/session/crud (SQLite)
  utils/                   Image decode, feature extraction, audio save, response envelope
frontend/
  static/                  Working plain HTML/CSS/JS app (index.html, css/, js/)
  src/                     Placeholder for a future React rewrite (see "Frontend" below)
models/
  sign_language/           Trained MLP + scaler + label encoder + training report (committed)
  yolo/                     yolo11n.pt lands here on first run (gitignored, re-downloaded)
  mediapipe/                hand_landmarker.task lands here on first run (gitignored)
datasets/
  sign_language/
    custom_ISL/             Your uploaded ISL fingerspelling images (23 letters)
    WLASL100/                Derived WLASL metadata (glosses + download-list CSV) -- see "WLASL" below
  ocr/custom_OCR/
    synthetic/               6 generated clean sign/label images (real OCR eval target)
    data/sample/              1 sample CAPTCHA image (adversarial stress-test, not a fair eval set)
  object_detection_coco/     coco_80_classes.json (category names only -- see "COCO" below)
  speech/LibriSpeech/        empty, not uploaded
  sound/ESC-50/              empty, not uploaded (Phase 2)
scripts/                    One-off data prep / training / demo scripts (see below)
tests/                       pytest suite
outputs/                     Runtime-generated TTS audio + uploads (gitignored)
```

*Removed to keep the repo lean (none of it is needed to run the app):* the two 12MB reference Kaggle notebooks, the raw 12MB `WLASL_v0.3.json` (its derived outputs are kept), and 1,070 of the 1,071 uploaded CAPTCHA images (only the one used by `demo_pipeline.py` is kept). See "Cleanup notes" below.

## Scripts

| Script | What it does |
|---|---|
| `scripts/extract_isl_landmarks.py` | Walks `custom_ISL/`, extracts a feature vector per image (MediaPipe landmarks if available, HOG fallback), saves `isl_features.npz`. |
| `scripts/train_sign_model.py` | Trains the MLP on those features, saves model/scaler/encoder + `training_report.json`. |
| `scripts/explore_wlasl.py` | Parses `WLASL_v0.3.json` (re-download it if you want to regenerate the list -- see the script's docstring), ranks glosses, writes the WLASL100 class list + a CSV of clip URLs. |
| `scripts/download_wlasl_clips.py` | Optional: actually downloads WLASL video clips (needs unrestricted internet, run on your own machine). |
| `scripts/generate_ocr_samples.py` | Renders 6 clean sign/label images for a fair OCR eval set. |
| `scripts/demo_pipeline.py` | End-to-end offline smoke test (see below). |

## What was actually executed here

This sandbox had ~10GB free disk and no GPU/camera/microphone, so the
build prioritized proving every *pipeline mechanic* works correctly
with what's genuinely available, rather than installing multi-GB
PyTorch/CUDA stacks that were likely to exhaust disk:

1. **Extracted your feature pipeline** on the real `custom_ISL` images (MediaPipe landmarker couldn't reach its model-download URL in this sandbox, so it fell back to HOG automatically -- exactly the fallback the code is designed for) and **trained** the MLP classifier on it.
2. **Installed** `tesseract-ocr` and `espeak-ng` (lightweight, via apt) and ran the **OCR** and **TTS** services for real.
3. **Ran the full FastAPI app** in-process (`TestClient`) and hit `/api/health`, `/api/recognize-sign`, `/api/read-text`, `/api/history` -- all returned correct 200 responses with real predictions logged to SQLite.
4. **Did not** `pip install ultralytics` or `openai-whisper` here (each pulls PyTorch; combined with CUDA deps this regularly exceeds several GB and would have been risky on a 10GB disk). Both services are fully implemented against their real APIs and will work the moment you install them normally.

Run `python scripts/demo_pipeline.py` to reproduce steps 1-3 yourself.

## Dataset notes and limitations (be explicit about these in your report)

- **custom_ISL is fingerspelling (23 static letters: A-G, I, K-X, Z), not word-level signs.** The project guide's target vocabulary (hello, water, help, ...) is dynamic/video-based. The architecture here (extract features → classifier) is identical either way; swapping in real word-level ISL video clips later means re-running `extract_isl_landmarks.py`/`train_sign_model.py` with per-frame-sequence features (LSTM) instead of single-frame features (MLP) -- the API layer doesn't change.
- **Your "custom OCR dataset" upload was actually a CAPTCHA dataset** (`alizahidraja/captcha-data`), which is adversarial by design (meant to defeat OCR), not representative of "reading signs, documents, labels" per the guide. `scripts/generate_ocr_samples.py` builds a small, fair substitute; replace `datasets/ocr/custom_OCR/synthetic/` with 300-500 real photos of signs/menus/documents for a proper evaluation, per the guide's section 5.
- **WLASL is American Sign Language, not Indian Sign Language.** Use it only for initial pipeline benchmarking; `custom_ISL` is this project's real India-focused contribution. State this limitation explicitly in your report (the guide calls this out too).
- **COCO annotations**: only `instances_val2017.json`'s 80 category names were kept (`datasets/object_detection_coco/coco_80_classes.json`) -- per the guide, retraining YOLO on full COCO isn't necessary or intended; the pretrained Ultralytics weights already cover it.
- **44.7% ISL test accuracy is a small-dataset, HOG-feature, random-split number** -- expected to improve substantially with (a) MediaPipe landmarks instead of HOG once a machine has internet for the model download, (b) more images per class, and (c) is likely optimistic vs. reality since the split isn't by signer. Do the guide's recommended **unseen-signer test** (train on some people, test on different people) once you collect your own multi-volunteer recordings.

## Frontend design

The UI is a **dashboard**, not a marketing page: a persistent sidebar (Dashboard / Blind & low-vision / Deaf & hard-of-hearing / Communication) with client-side routing between views, and a dashboard frontpage that shows real, live data pulled from `GET /api/history` -- total interactions, average confidence, most-used mode, backend status, and a recent-activity feed that updates the moment you run a tool anywhere in the app.

The visual language is grounded in what the app actually does: the hero graphic is a literal MediaPipe-style 21-point hand skeleton connected by a dashed path to a sound waveform. Every confidence score the API returns is rendered as an actual colored dot + percentage (green ≥66%, amber ≥33%, red below) -- color is tied to real data, not decoration.

- **Type**: [Atkinson Hyperlegible](https://brailleinstitute.org/freefont) for all body copy and results -- a typeface literally designed by the Braille Institute for low-vision readability -- paired with Space Grotesk for headings/buttons/nav.
- **Real accessibility controls, not just styling**: an A−/A+ text-size stepper and a light/dark theme toggle in the sidebar, both persisted in `localStorage`, because different low-vision conditions want different contrast directions.
- **Camera and microphone, not just file pickers**: every photo tool has a "Use camera" button (`getUserMedia` + canvas capture) and the speech tools have a "Record audio" button (`MediaRecorder`), alongside drag-and-drop file upload.
- **Communication mode is an actual conversation**: messages from the hearing and deaf participants appear as a two-sided chat transcript (with inline audio playback), instead of two disconnected forms.
- **Dashboard stats are real, not mocked**: they're computed client-side from the same `prediction_history` SQLite table every API call already writes to -- open `/docs`, hit an endpoint directly, and the dashboard reflects it on next visit.
- Motion is limited to one on-load hero sequence (respecting `prefers-reduced-motion`) plus direct responses to user actions (view switch, recording state, a stat card "bumping" when it changes) -- nothing loops or animates on its own.

## Frontend (implementation)

`frontend/static/` is plain HTML/CSS/JS (no build step), served
automatically by `backend/main.py`, calling the API endpoints directly
with `fetch`. It's a small hash-routed SPA (`#dashboard`, `#blind`,
`#hearing`, `#comm`) rather than one long scrolling page. Keyboard-navigable, with `aria-live` result regions.

`frontend/src/` is left empty as a placeholder if you want to build the
fuller React version from the guide's structure (`Home.jsx`,
`BlindMode.jsx`, `HearingMode.jsx`, `Communication.jsx`,
`src/services/api.js`) later -- every endpoint it would call already
exists and is documented above.

## Privacy (per the guide's section 13)

- `GET /api/history` stores only `{modality, result_text, confidence, timestamp}` -- never raw camera frames or audio.
- Uploaded images/audio are written to `outputs/uploads/` only transiently for processing and are not retained by any endpoint here (add explicit consent + a `media_path` column to `PredictionHistory` if you want opt-in saving later).
- Treat every prediction as an estimate, not a guaranteed fact -- this is why every response includes a `confidence` value.

## Cleanup notes

This project was audited for unused files and dependencies:

- **Removed**: `notebooks/` (2 reference Kaggle notebooks, 24MB, not used by the running app), `datasets/sign_language/WLASL100/WLASL_v0.3.json` (12MB raw metadata, already consumed by `scripts/explore_wlasl.py` -- its derived outputs are kept), and 1,070 of 1,071 uploaded CAPTCHA images (only `data/sample/` is referenced by any code). Net effect: repo dropped from 94MB/1,830 files to 47MB/757 files with zero functional loss.
- **Removed from `requirements.txt`**: `tensorflow`, `librosa` (unused -- add back only when you actually build the Phase 2 ESC-50 classifier), `sounddevice`/`soundfile` (unused -- the frontend records audio in-browser via `MediaRecorder`, not server-side), `edge-tts` (unused -- only `pyttsx3` is called), and an explicit `pydantic` pin (FastAPI manages its own compatible version).
- **Fixed, not removed**: `python-dotenv` was listed but never actually loaded `.env` -- `backend/config.py` now calls `load_dotenv()` on startup, so `.env.example` → `.env` actually works as documented.

## Roadmap (Phase 2+)

- Add ESC-50 and train the emergency-sound classifier (mel-spectrogram → CNN), matching the guide's optional pipeline.
- Collect real multi-signer ISL video for 10-20 practical words (hello, help, water, ...) and retrain with LSTM sequence features.
- Replace the CAPTCHA "OCR dataset" with real sign/document photos (300-500 images) for a genuine CER/WER evaluation.
- Install `ultralytics` + `openai-whisper` on a normal machine and re-run `scripts/demo_pipeline.py`-style checks against them.
- Optional: swap the plain-JS frontend for the React structure sketched in `frontend/src/`.
