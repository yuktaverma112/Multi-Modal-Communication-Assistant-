"""
scripts/train_word_model.py

Trains an MLP classifier on the pooled clip descriptors produced by
scripts/extract_word_landmarks.py, and saves the model + label encoder
to models/sign_language/word_*.{pkl,json}. Deliberately mirrors
train_sign_model.py's architecture and output format -- same
lightweight sklearn approach, same artifact naming convention, just a
"word_" prefix so it sits alongside the letter model without
overwriting it.

Usage:
    python scripts/extract_word_landmarks.py   # first
    python scripts/train_word_model.py
"""
import os
import sys
import json
import numpy as np
import joblib
from collections import Counter
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

FEATURES_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "sign_language", "word_features.npz")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "sign_language")
TEST_SIZE = 0.2
MIN_PER_CLASS = 5  # see the check below for exactly why 5


def main():
    if not os.path.exists(FEATURES_PATH):
        print(f"No features file at {FEATURES_PATH}.")
        print("Run scripts/extract_word_landmarks.py first (after populating datasets/sign_language/word_clips/).")
        sys.exit(1)

    data = np.load(FEATURES_PATH, allow_pickle=True)
    X, y = data["X"], data["y"]
    method = str(data["extraction_method"])
    print(f"Loaded {X.shape[0]} clip descriptors, {X.shape[1]} features each (extraction method: {method})")

    counts = Counter(y.tolist())
    # A stratified split needs at least 1 test sample PER CLASS, i.e.
    # each class's own count * TEST_SIZE >= 1 -- so every class needs
    # at least ceil(1 / TEST_SIZE) samples (5, at TEST_SIZE=0.2),
    # regardless of how many classes there are in total.
    min_required = max(MIN_PER_CLASS, int(np.ceil(1 / TEST_SIZE)))
    too_few = {gloss: n for gloss, n in counts.items() if n < min_required}
    if too_few:
        print(f"\nThese words have fewer than {min_required} usable clips, so a stratified "
              f"train/test split (which needs at least one test example per class) isn't "
              f"possible yet: {too_few}")
        print(f"Record or download at least {min_required} clips for each word and re-run "
              "scripts/extract_word_landmarks.py before training.")
        sys.exit(1)

    encoder = LabelEncoder()
    y_enc = encoder.fit_transform(y)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=TEST_SIZE, random_state=42, stratify=y_enc
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    clf = MLPClassifier(
        hidden_layer_sizes=(128, 64),
        activation="relu",
        alpha=1e-3,
        max_iter=800,
        early_stopping=True,
        random_state=42,
    )
    clf.fit(X_train_s, y_train)

    y_pred = clf.predict(X_test_s)
    acc = accuracy_score(y_test, y_pred)
    print(f"\nTest accuracy: {acc:.3f}\n")
    print(classification_report(y_test, y_pred, target_names=encoder.classes_, zero_division=0))

    cm = confusion_matrix(y_test, y_pred)

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(clf, os.path.join(MODEL_DIR, "word_model.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, "word_scaler.pkl"))
    joblib.dump(encoder, os.path.join(MODEL_DIR, "word_label_encoder.pkl"))

    with open(os.path.join(MODEL_DIR, "word_training_report.json"), "w") as f:
        json.dump({
            "extraction_method": method,
            "pooling": "mean/std/min/max across sampled frames + first-to-last delta",
            "n_samples": int(X.shape[0]),
            "n_features": int(X.shape[1]),
            "n_classes": len(encoder.classes_),
            "classes": encoder.classes_.tolist(),
            "test_accuracy": float(acc),
            "confusion_matrix": cm.tolist(),
        }, f, indent=2)

    print(f"Saved word_model.pkl, word_scaler.pkl, word_label_encoder.pkl and "
          f"word_training_report.json to {MODEL_DIR}")
    print("\nNOTE: like the letter model, this split is random, not by signer -- treat this "
          "accuracy as optimistic. Do an unseen-signer split once you have multiple people's clips.")


if __name__ == "__main__":
    main()
