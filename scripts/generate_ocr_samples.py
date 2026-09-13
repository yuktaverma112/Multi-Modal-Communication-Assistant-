"""
scripts/generate_ocr_samples.py

The only OCR dataset you uploaded (archive__2/3_.zip -> captcha-data)
is a CAPTCHA dataset: intentionally distorted text, the opposite of
what section 5 of the project guide means by a "custom OCR dataset --
reading signs, documents, labels". It's kept in
datasets/ocr/custom_OCR/data/ as a stress-test, but it will not give a
representative OCR accuracy number.

This script generates a small set of clean, rendered sign/label-style
images (the guide's real target use case) so the OCR service has
something realistic to be evaluated against too. Replace this
directory with real photos of signs/menus/documents for a proper
evaluation set, per the guide's "300-500 image" recommendation.
"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets", "ocr", "custom_OCR", "synthetic")

SAMPLES = [
    "EXIT",
    "PLEASE WASH YOUR HANDS",
    "PLATFORM 4",
    "EMERGENCY STOP",
    "NO ENTRY",
    "HOSPITAL - 200m",
]


def _font(size=48):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    font = _font()
    for i, text in enumerate(SAMPLES):
        img = Image.new("RGB", (700, 140), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 699, 139], outline=(0, 0, 0), width=4)
        draw.text((30, 45), text, fill=(0, 0, 0), font=font)
        path = os.path.join(OUT_DIR, f"sample_{i:02d}.png")
        img.save(path)
        print(f"Wrote {path}  (text: {text!r})")


if __name__ == "__main__":
    main()
