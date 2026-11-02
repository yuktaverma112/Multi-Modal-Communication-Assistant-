"""
scripts/train_sign_model.py

Trains an MLP classifier on the sign language feature vectors produced by
scripts/extract_isl_landmarks.py and saves the model + scaler + label encoder
to models/sign_language/.

Usage:
    python scripts/extract_isl_landmarks.py   # extract features first
    python scripts/train_sign_model.py        # train with optimal MLP architecture
"""
import os
import sys
import json
import argparse
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score


def main():
    parser = argparse.ArgumentParser(description="Train sign language recognition classifier.")
    parser.add_argument(
        "--features-path", "-f",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "models", "sign_language", "isl_features.npz"),
        help="Path to .npz feature file",
    )
    parser.add_argument(
        "--model-dir", "-m",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "models", "sign_language"),
        help="Directory to save trained model artifacts",
    )
    parser.add_argument(
        "--hidden-layers",
        type=str,
        default="256,128,64",
        help="Comma-separated hidden layer sizes (default: 256,128,64)",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=1e-3,
        help="L2 regularization penalty (default: 0.001)",
    )
    parser.add_argument(
        "--max-iter",
        type=int,
        default=1000,
        help="Maximum training epochs (default: 1000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    args = parser.parse_args()

    features_path = os.path.abspath(args.features_path)
    model_dir = os.path.abspath(args.model_dir)
    hidden_layer_sizes = tuple(int(x.strip()) for x in args.hidden_layers.split(","))

    if not os.path.exists(features_path):
        print(f"Error: features file not found: {features_path}")
        print("Please run scripts/extract_isl_landmarks.py first.")
        sys.exit(1)

    print("=" * 70)
    print("TRAINING SIGN LANGUAGE CLASSIFIER")
    print("=" * 70)
    print(f"Features Path:       {features_path}")
    print(f"Model Directory:     {model_dir}")
    print(f"Hidden Layers:       {hidden_layer_sizes}")
    print(f"L2 Regularization:   {args.alpha}")
    print(f"Max Epochs:          {args.max_iter}")
    print("-" * 70)

    data = np.load(features_path, allow_pickle=True)
    X, y = data["X"], data["y"]
    method = str(data["method"])
    print(f"Loaded {X.shape[0]} total samples with {X.shape[1]} features each (Extraction method: {method})")

    encoder = LabelEncoder()
    y_enc = encoder.fit_transform(y)
    n_classes = len(encoder.classes_)
    print(f"Vocabulary: {n_classes} distinct classes: {list(encoder.classes_)}")

    # 80/20 Stratified Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=0.20, random_state=args.seed, stratify=y_enc
    )
    print(f"Split: {len(X_train)} training samples, {len(X_test)} validation/test samples")

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    # Multi-Layer Perceptron (Input -> Dense256+ReLU -> Dense128+ReLU -> Dense64+ReLU -> Softmax)
    clf = MLPClassifier(
        hidden_layer_sizes=hidden_layer_sizes,
        activation="relu",
        alpha=args.alpha,
        max_iter=args.max_iter,
        early_stopping=True,
        n_iter_no_change=15,
        random_state=args.seed,
    )
    clf.fit(X_train_s, y_train)

    train_acc = accuracy_score(y_train, clf.predict(X_train_s))
    y_pred = clf.predict(X_test_s)
    test_acc = accuracy_score(y_test, y_pred)

    print("=" * 70)
    print(f"TRAINING COMPLETE (Converged in {clf.n_iter_} iterations)")
    print(f"Training Accuracy:   {train_acc * 100:.2f}%")
    print(f"Validation Accuracy: {test_acc * 100:.2f}%")
    print("=" * 70)
    print("\nClassification Report:\n")
    report = classification_report(
        y_test, y_pred, target_names=encoder.classes_, zero_division=0, digits=3
    )
    print(report)

    cm = confusion_matrix(y_test, y_pred)

    os.makedirs(model_dir, exist_ok=True)
    model_file = os.path.join(model_dir, "sign_model.pkl")
    scaler_file = os.path.join(model_dir, "scaler.pkl")
    encoder_file = os.path.join(model_dir, "label_encoder.pkl")
    report_file = os.path.join(model_dir, "training_report.json")

    joblib.dump(clf, model_file)
    joblib.dump(scaler, scaler_file)
    joblib.dump(encoder, encoder_file)

    report_data = {
        "extraction_method": method,
        "n_samples": int(X.shape[0]),
        "n_features": int(X.shape[1]),
        "n_classes": n_classes,
        "classes": encoder.classes_.tolist(),
        "hidden_layer_sizes": list(hidden_layer_sizes),
        "iterations_converged": int(clf.n_iter_),
        "train_accuracy": float(train_acc),
        "test_accuracy": float(test_acc),
        "confusion_matrix": cm.tolist(),
    }
    with open(report_file, "w") as f:
        json.dump(report_data, f, indent=2)

    print(f"Model saved:   {model_file}")
    print(f"Scaler saved:  {scaler_file}")
    print(f"Encoder saved: {encoder_file}")
    print(f"Report saved:  {report_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
