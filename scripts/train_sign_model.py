"""
scripts/train_sign_model.py

Trains an MLP classifier on the features produced by
scripts/extract_isl_landmarks.py and saves the model + label encoder to
models/sign_language/.

Usage:
    python scripts/extract_isl_landmarks.py   # first, if not already run
    python scripts/train_sign_model.py
"""
import os
import json
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

FEATURES_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "sign_language", "isl_features.npz")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "sign_language")


def main():
    data = np.load(FEATURES_PATH, allow_pickle=True)
    X, y = data["X"], data["y"]
    method = str(data["method"])
    print(f"Loaded {X.shape[0]} samples, {X.shape[1]} features (extraction method: {method})")

    encoder = LabelEncoder()
    y_enc = encoder.fit_transform(y)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=0.2, random_state=42, stratify=y_enc
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    # Architecture roughly mirrors the guide's "Input -> Dense128+ReLU ->
    # Dropout -> Dense64+ReLU -> Dense N + Softmax" using sklearn's MLP
    # (alpha acts as L2 regularization in lieu of explicit dropout).
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
    report = classification_report(
        y_test, y_pred, target_names=encoder.classes_, zero_division=0
    )
    print(report)

    cm = confusion_matrix(y_test, y_pred)

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(clf, os.path.join(MODEL_DIR, "sign_model.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, "scaler.pkl"))
    joblib.dump(encoder, os.path.join(MODEL_DIR, "label_encoder.pkl"))

    with open(os.path.join(MODEL_DIR, "training_report.json"), "w") as f:
        json.dump({
            "extraction_method": method,
            "n_samples": int(X.shape[0]),
            "n_features": int(X.shape[1]),
            "n_classes": len(encoder.classes_),
            "classes": encoder.classes_.tolist(),
            "test_accuracy": float(acc),
            "confusion_matrix": cm.tolist(),
        }, f, indent=2)

    print(f"Saved model, scaler, encoder and training_report.json to {MODEL_DIR}")
    print(
        "\nNOTE: this split is random, not split-by-signer. The project "
        "guide calls out unseen-signer testing as the more realistic "
        "evaluation -- do that once you collect multiple volunteers "
        "for your own ISL recordings (see README, Phase 1 dataset plan)."
    )


if __name__ == "__main__":
    main()
