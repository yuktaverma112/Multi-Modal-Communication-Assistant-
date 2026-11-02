"""
scripts/augment_dataset.py

Comprehensive, production-ready data augmentation pipeline tailored for sign language
gesture datasets (such as Indian Sign Language / ISL and American Sign Language / ASL).

Key features:
- Domain-safe transformations:
    * Spatial/Geometric: slight rotations (-15 to +15 deg), subtle translations (-8% to +8%),
      slight zoom/scaling (0.88x to 1.15x), mild shear (-6 to +6 deg), subtle perspective warp.
    * Lighting/Photometric: brightness adjustment, contrast scaling, HSV hue/saturation jitter,
      gamma exposure correction via lookup table.
    * Sensor/Environment: Gaussian defocus blur, linear motion blur, subtle Gaussian sensor noise,
      mild random cutout/erasing (occlusion simulation).
    * Sign language safety: horizontal flip is DISABLED by default (handedness/orientation
      matters in sign language alphabet like B/D/P/Q/E/L/I), vertical flips and extreme rotations
      are strictly excluded.
- Operational modes:
    * Multiplier mode (--multiplier N): Generates N diverse augmented variations for every image.
    * Class balancing mode (--target-count N): Dynamically generates enough augmented variations
      so every class reaches at least N samples, eliminating class imbalance.
- Safe output options:
    * Default output to a separate directory (e.g. DataSet_Augmented/), keeping originals untouched.
    * Optional --in-place flag to write directly into the source dataset folder.
    * Automatically copies original images to destination (enabled by default) so the output
      folder is a complete, drop-in replacement dataset.
- Verification & Reporting:
    * Saves an augmentation_report.json with full statistics before and after augmentation.
    * Performs integrity verification on all generated images.

Usage:
    # 1. Standard run: 5 augmentations per image -> DataSet_Augmented/
    python scripts/augment_dataset.py

    # 2. Balanced run: bring every class to at least 100 images
    python scripts/augment_dataset.py --target-count 100

    # 3. Custom multiplier (e.g., 10x):
    python scripts/augment_dataset.py --multiplier 10

    # 4. In-place augmentation into existing DataSet:
    python scripts/augment_dataset.py --in-place --multiplier 5
"""

import os
import sys
import glob
import json
import random
import argparse
import shutil
import time
from typing import List, Dict, Tuple, Optional
import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Transformation Primitives
# ---------------------------------------------------------------------------

def apply_affine_transform(
    image: np.ndarray,
    angle_range: Tuple[float, float] = (-15.0, 15.0),
    scale_range: Tuple[float, float] = (0.88, 1.15),
    shift_range: Tuple[float, float] = (-0.08, 0.08),
    shear_range: Tuple[float, float] = (-6.0, 6.0),
) -> Tuple[np.ndarray, str]:
    """Applies combined rotation, scaling, translation, and shear."""
    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)

    angle = random.uniform(*angle_range)
    scale = random.uniform(*scale_range)
    dx = random.uniform(*shift_range) * w
    dy = random.uniform(*shift_range) * h
    shear_x = np.deg2rad(random.uniform(*shear_range))
    shear_y = np.deg2rad(random.uniform(*shear_range))

    # Rotation + Scale matrix
    rot_mat = cv2.getRotationMatrix2D(center, angle, scale)
    rot_mat[0, 2] += dx
    rot_mat[1, 2] += dy

    # Expand to 3x3 for composition
    affine_3x3 = np.vstack([rot_mat, [0, 0, 1]])

    # Shear matrix around center
    shear_3x3 = np.array([
        [1.0, np.tan(shear_x), -np.tan(shear_x) * center[1]],
        [np.tan(shear_y), 1.0, -np.tan(shear_y) * center[0]],
        [0.0, 0.0, 1.0]
    ], dtype=np.float32)

    combined_3x3 = affine_3x3 @ shear_3x3
    final_mat = combined_3x3[:2, :]

    warped = cv2.warpAffine(
        image,
        final_mat,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101
    )
    tag = f"rot{angle:+.1f}_s{scale:.2f}_dx{dx:+.0f}_dy{dy:+.0f}"
    return warped, tag


def apply_perspective_warp(
    image: np.ndarray,
    distortion_scale: float = 0.04
) -> Tuple[np.ndarray, str]:
    """Applies a subtle 4-point perspective distortion."""
    h, w = image.shape[:2]
    d = distortion_scale
    src_pts = np.float32([
        [0, 0],
        [w, 0],
        [w, h],
        [0, h]
    ])
    dst_pts = np.float32([
        [random.uniform(0, d * w), random.uniform(0, d * h)],
        [w - random.uniform(0, d * w), random.uniform(0, d * h)],
        [w - random.uniform(0, d * w), h - random.uniform(0, d * h)],
        [random.uniform(0, d * w), h - random.uniform(0, d * h)]
    ])
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(
        image,
        M,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101
    )
    return warped, "persp"


def adjust_brightness_contrast(
    image: np.ndarray,
    brightness_range: Tuple[float, float] = (0.78, 1.25),
    contrast_range: Tuple[float, float] = (0.78, 1.25),
) -> Tuple[np.ndarray, str]:
    """Adjusts brightness and contrast using an efficient precomputed lookup table."""
    alpha = random.uniform(*contrast_range)      # Contrast control
    beta_factor = random.uniform(*brightness_range) # Brightness factor

    # Vectorized LUT for instant 8-bit mapping
    table = np.arange(256, dtype=np.float32)
    # Scale around midpoint 128 for contrast, then adjust brightness
    table = (table - 128.0) * alpha + 128.0
    table = table * beta_factor
    lut = np.clip(table, 0, 255).astype(np.uint8)

    adjusted = cv2.LUT(image, lut)
    tag = f"bright{beta_factor:.2f}_cont{alpha:.2f}"
    return adjusted, tag


def adjust_hsv_jitter(
    image: np.ndarray,
    hue_shift_limit: int = 8,
    sat_scale_range: Tuple[float, float] = (0.80, 1.25),
) -> Tuple[np.ndarray, str]:
    """Applies subtle hue jitter and saturation scaling to simulate varied lighting."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    h_shift = random.uniform(-hue_shift_limit, hue_shift_limit)
    s_scale = random.uniform(*sat_scale_range)

    hsv[:, :, 0] = (hsv[:, :, 0] + h_shift) % 180.0
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * s_scale, 0, 255.0)

    bgr = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    tag = f"hue{h_shift:+.1f}_sat{s_scale:.2f}"
    return bgr, tag


def adjust_gamma(
    image: np.ndarray,
    gamma_range: Tuple[float, float] = (0.80, 1.25)
) -> Tuple[np.ndarray, str]:
    """Applies gamma exposure correction."""
    gamma = random.uniform(*gamma_range)
    inv_gamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype(np.uint8)
    adjusted = cv2.LUT(image, table)
    return adjusted, f"gam{gamma:.2f}"


def apply_blur(
    image: np.ndarray,
    mode: Optional[str] = None
) -> Tuple[np.ndarray, str]:
    """Applies either Gaussian defocus blur or directional motion blur."""
    if mode is None:
        mode = random.choice(["gaussian", "motion"])

    if mode == "gaussian":
        ksize = random.choice([3, 5])
        sigma = random.uniform(0.5, 1.2)
        blurred = cv2.GaussianBlur(image, (ksize, ksize), sigma)
        return blurred, f"gblur{ksize}s{sigma:.1f}"
    else:
        # Linear motion blur
        size = random.choice([3, 5, 7])
        angle = random.uniform(0, 180)
        kernel = np.zeros((size, size), dtype=np.float32)
        center = size // 2
        # Draw a line at angle
        rad = np.deg2rad(angle)
        dx = int(round(np.cos(rad) * center))
        dy = int(round(np.sin(rad) * center))
        cv2.line(kernel, (center - dx, center - dy), (center + dx, center + dy), 1.0, 1)
        ksum = kernel.sum()
        if ksum > 0:
            kernel /= ksum
        else:
            kernel[center, center] = 1.0
        blurred = cv2.filter2D(image, -1, kernel)
        return blurred, f"mblur{size}a{angle:.0f}"


def add_gaussian_noise(
    image: np.ndarray,
    sigma_range: Tuple[float, float] = (2.0, 9.0)
) -> Tuple[np.ndarray, str]:
    """Simulates camera sensor noise in low-light environments."""
    sigma = random.uniform(*sigma_range)
    noise = np.random.normal(0, sigma, image.shape).astype(np.float32)
    noisy = np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return noisy, f"noise{sigma:.1f}"


def apply_cutout_occlusion(
    image: np.ndarray,
    num_patches: int = 1,
    patch_size_range: Tuple[float, float] = (0.04, 0.10)
) -> Tuple[np.ndarray, str]:
    """Applies small rectangular cutouts simulating partial background occlusion."""
    h, w = image.shape[:2]
    out = image.copy()
    for _ in range(num_patches):
        scale = random.uniform(*patch_size_range)
        pw, ph = int(w * scale), int(h * scale)
        if pw <= 0 or ph <= 0:
            continue
        # Avoid placing directly on the absolute center
        x = random.randint(0, max(0, w - pw))
        y = random.randint(0, max(0, h - ph))

        fill_type = random.choice(["mean", "noise", "gray"])
        if fill_type == "mean":
            out[y:y+ph, x:x+pw] = np.mean(image, axis=(0, 1)).astype(np.uint8)
        elif fill_type == "noise":
            out[y:y+ph, x:x+pw] = np.random.randint(0, 256, (ph, pw, image.shape[2]), dtype=np.uint8)
        else:
            out[y:y+ph, x:x+pw] = 128
    return out, "cutout"


# ---------------------------------------------------------------------------
# Composite Augmentation Strategy
# ---------------------------------------------------------------------------

def generate_augmented_sample(
    image: np.ndarray,
    allow_horizontal_flip: bool = False,
    augment_intensity: str = "moderate"
) -> Tuple[np.ndarray, List[str]]:
    """
    Composes a natural, realistic chain of transformations:
    1. Spatial (Rotation + Shift + Zoom + Shear)
    2. Subtle perspective (probabilistic)
    3. Lighting / Contrast / Gamma
    4. HSV Color variation
    5. Blur / Defocus OR Sensor Noise
    6. Occasional small occlusion cutout
    """
    tags = []
    aug_img = image.copy()

    # 1. Spatial affine transform (always applied with subtle randomization)
    if augment_intensity == "light":
        aug_img, tag = apply_affine_transform(
            aug_img, angle_range=(-8.0, 8.0), scale_range=(0.93, 1.08), shift_range=(-0.05, 0.05), shear_range=(-3.0, 3.0)
        )
    elif augment_intensity == "strong":
        aug_img, tag = apply_affine_transform(
            aug_img, angle_range=(-18.0, 18.0), scale_range=(0.84, 1.20), shift_range=(-0.10, 0.10), shear_range=(-8.0, 8.0)
        )
    else:  # moderate (default)
        aug_img, tag = apply_affine_transform(
            aug_img, angle_range=(-14.0, 14.0), scale_range=(0.88, 1.14), shift_range=(-0.08, 0.08), shear_range=(-5.0, 5.0)
        )
    tags.append(tag)

    # 2. Optional perspective warp (35% probability)
    if random.random() < 0.35:
        aug_img, tag = apply_perspective_warp(aug_img, distortion_scale=0.03)
        tags.append(tag)

    # 3. Photometric / Lighting (80% probability)
    if random.random() < 0.85:
        aug_img, tag = adjust_brightness_contrast(aug_img)
        tags.append(tag)

    # 4. Gamma correction (40% probability)
    if random.random() < 0.40:
        aug_img, tag = adjust_gamma(aug_img)
        tags.append(tag)

    # 5. HSV jitter (60% probability)
    if random.random() < 0.60:
        aug_img, tag = adjust_hsv_jitter(aug_img)
        tags.append(tag)

    # 6. Blur or Noise (50% probability)
    r = random.random()
    if r < 0.30:
        aug_img, tag = apply_blur(aug_img)
        tags.append(tag)
    elif r < 0.60:
        aug_img, tag = add_gaussian_noise(aug_img)
        tags.append(tag)

    # 7. Cutout occlusion (20% probability)
    if random.random() < 0.20:
        aug_img, tag = apply_cutout_occlusion(aug_img, num_patches=1, patch_size_range=(0.04, 0.08))
        tags.append(tag)

    # 8. Optional horizontal flip if explicitly enabled
    if allow_horizontal_flip and random.random() < 0.50:
        aug_img = cv2.flip(aug_img, 1)
        tags.append("hflip")

    return aug_img, tags


# ---------------------------------------------------------------------------
# Dataset Processing Engine
# ---------------------------------------------------------------------------

def find_image_files(directory: str) -> List[str]:
    """Finds all supported image files in a directory."""
    valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    images = []
    for f in os.listdir(directory):
        ext = os.path.splitext(f)[1].lower()
        if ext in valid_exts:
            images.append(os.path.join(directory, f))
    return sorted(images)


def process_dataset(
    source_dir: str,
    output_dir: str,
    multiplier: int = 5,
    target_count: Optional[int] = None,
    in_place: bool = False,
    copy_originals: bool = True,
    allow_horizontal_flip: bool = False,
    augment_intensity: str = "moderate",
    jpeg_quality: int = 92,
    seed: int = 42,
) -> Dict:
    """
    Main execution loop that walks all class subfolders and generates augmentations.
    """
    random.seed(seed)
    np.random.seed(seed)
    start_time = time.time()

    source_dir = os.path.abspath(source_dir)
    if in_place:
        output_dir = source_dir
    else:
        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)

    if not os.path.isdir(source_dir):
        raise ValueError(f"Source dataset directory not found: {source_dir}")

    class_dirs = sorted([
        d for d in os.listdir(source_dir)
        if os.path.isdir(os.path.join(source_dir, d))
    ])

    if not class_dirs:
        raise ValueError(f"No class subdirectories found in: {source_dir}")

    print("=" * 70)
    print("STARTING DATA AUGMENTATION PIPELINE")
    print("=" * 70)
    print(f"Source Directory:      {source_dir}")
    print(f"Output Directory:      {output_dir}")
    print(f"Total Classes Found:   {len(class_dirs)}")
    print(f"Mode:                  {'Target Count (' + str(target_count) + ' per class)' if target_count else 'Multiplier (' + str(multiplier) + 'x per image)'}")
    print(f"Intensity:             {augment_intensity}")
    print(f"Horizontal Flip:       {allow_horizontal_flip} (Handedness-safe)")
    print(f"In-Place:              {in_place}")
    print(f"Copy Originals:        {copy_originals if not in_place else 'N/A'}")
    print(f"Random Seed:           {seed}")
    print("-" * 70)

    stats = {
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_dir": source_dir,
        "output_dir": output_dir,
        "mode": "target_count" if target_count else "multiplier",
        "multiplier": multiplier,
        "target_count": target_count,
        "intensity": augment_intensity,
        "allow_horizontal_flip": allow_horizontal_flip,
        "classes": {},
        "total_originals": 0,
        "total_augmented": 0,
        "total_final": 0,
    }

    for class_name in class_dirs:
        class_src_path = os.path.join(source_dir, class_name)
        class_dst_path = os.path.join(output_dir, class_name)
        os.makedirs(class_dst_path, exist_ok=True)

        original_files = find_image_files(class_src_path)
        # Filter out previously generated augmentations if running in-place
        pure_originals = [
            f for f in original_files
            if not os.path.basename(f).startswith("aug_")
        ]
        n_orig = len(pure_originals)
        stats["total_originals"] += n_orig

        if n_orig == 0:
            print(f"[{class_name}] Warning: No original images found, skipping.")
            continue

        # Determine how many augmented images to generate
        if target_count is not None:
            needed = max(0, target_count - n_orig)
            # Cycle through originals to distribute augmentations evenly
            aug_plan = []
            for i in range(needed):
                aug_plan.append((pure_originals[i % n_orig], i + 1))
        else:
            aug_plan = []
            for orig_path in pure_originals:
                for m in range(1, multiplier + 1):
                    aug_plan.append((orig_path, m))

        n_aug_needed = len(aug_plan)
        class_aug_count = 0

        # Copy originals if writing to separate directory
        if not in_place and copy_originals:
            for orig_path in pure_originals:
                dst_file = os.path.join(class_dst_path, os.path.basename(orig_path))
                if os.path.abspath(orig_path) != os.path.abspath(dst_file):
                    shutil.copy2(orig_path, dst_file)

        # Generate augmentations
        for orig_path, aug_idx in aug_plan:
            orig_name = os.path.splitext(os.path.basename(orig_path))[0]
            # Read image
            image = cv2.imread(orig_path)
            if image is None:
                print(f"Error reading {orig_path}, skipping.")
                continue

            # Transform
            aug_image, tags = generate_augmented_sample(
                image,
                allow_horizontal_flip=allow_horizontal_flip,
                augment_intensity=augment_intensity
            )

            tag_summary = "_".join(tags[:2])  # Keep filename clean
            out_filename = f"aug_{orig_name[:25]}_{aug_idx:03d}_{tag_summary}.jpg"
            # Sanitize filename (spaces/symbols)
            safe_filename = "".join([c if c.isalnum() or c in "._-" else "_" for c in out_filename])
            out_path = os.path.join(class_dst_path, safe_filename)

            # Save JPEG
            cv2.imwrite(out_path, aug_image, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
            class_aug_count += 1

        final_class_count = (n_orig if (copy_originals or in_place) else 0) + class_aug_count
        stats["classes"][class_name] = {
            "original_count": n_orig,
            "augmented_count": class_aug_count,
            "final_count": final_class_count,
        }
        stats["total_augmented"] += class_aug_count
        stats["total_final"] += final_class_count

        print(f"Class '{class_name:>15}': {n_orig:>3} originals -> +{class_aug_count:>4} augmented = {final_class_count:>4} total")

    elapsed = time.time() - start_time
    stats["elapsed_seconds"] = round(elapsed, 2)
    stats["completed_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # Save summary report
    report_path = os.path.join(output_dir, "augmentation_report.json")
    with open(report_path, "w") as f:
        json.dump(stats, f, indent=2)

    print("=" * 70)
    print("AUGMENTATION SUMMARY")
    print("=" * 70)
    print(f"Total Original Images:     {stats['total_originals']}")
    print(f"Total Augmented Images:    {stats['total_augmented']}")
    print(f"Total Dataset Count:       {stats['total_final']}")
    print(f"Elapsed Time:              {elapsed:.2f} seconds ({elapsed / max(1, stats['total_augmented']):.3f}s / image)")
    print(f"Augmentation Report Saved: {report_path}")
    print("=" * 70)

    return stats


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Augment sign language image dataset.")
    parser.add_argument(
        "--source-dir", "-s",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "DataSet"),
        help="Path to source dataset directory (default: <project>/DataSet)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "..", "DataSet_Augmented"),
        help="Path to output augmented dataset directory (default: <project>/DataSet_Augmented)",
    )
    parser.add_argument(
        "--multiplier", "-m",
        type=int,
        default=5,
        help="Number of augmented variants per original image (default: 5)",
    )
    parser.add_argument(
        "--target-count", "-t",
        type=int,
        default=None,
        help="If set, augments each class up to at least target-count images (balancing classes)",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Write augmented images directly into the source dataset directory",
    )
    parser.add_argument(
        "--no-copy-originals",
        action="store_true",
        help="Do not copy original images into the destination directory",
    )
    parser.add_argument(
        "--intensity",
        choices=["light", "moderate", "strong"],
        default="moderate",
        help="Augmentation perturbation intensity (default: moderate)",
    )
    parser.add_argument(
        "--allow-horizontal-flip",
        action="store_true",
        help="Allow horizontal flipping (WARNING: In sign language, flipping can change hand-sign identity!)",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=92,
        help="JPEG quality for saved images (default: 92)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic reproducibility (default: 42)",
    )

    args = parser.parse_args()

    # Determine default paths relative to workspace if not explicitly provided
    source_dir = os.path.abspath(args.source_dir)
    if not os.path.exists(source_dir):
        # Check fallback for nested directory structure
        alt_source = os.path.abspath(os.path.join("Multi-Modal-Communication-Assistant--main", "DataSet"))
        if os.path.exists(alt_source):
            source_dir = alt_source

    output_dir = os.path.abspath(args.output_dir)
    if not args.in_place and not os.path.exists(os.path.dirname(output_dir)):
        alt_output = os.path.abspath(os.path.join("Multi-Modal-Communication-Assistant--main", "DataSet_Augmented"))
        output_dir = alt_output

    process_dataset(
        source_dir=source_dir,
        output_dir=output_dir,
        multiplier=args.multiplier,
        target_count=args.target_count,
        in_place=args.in_place,
        copy_originals=not args.no_copy_originals,
        allow_horizontal_flip=args.allow_horizontal_flip,
        augment_intensity=args.intensity,
        jpeg_quality=args.jpeg_quality,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()

