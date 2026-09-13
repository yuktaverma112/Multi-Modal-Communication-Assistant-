"""
scripts/download_wlasl_clips.py  (OPTIONAL, run on your own machine)

Downloads the actual video clips listed in
datasets/sign_language/WLASL100/wlasl100_download_list.csv.

This is NOT run as part of the core pipeline (it needs unrestricted
internet access to many different third-party video hosts, some of
which are slow/unreliable/occasionally offline -- this is a known
characteristic of the WLASL dataset). Use it only if you want to
benchmark your pipeline on real ASL video beyond the metadata.

Usage:
    pip install yt-dlp requests
    python scripts/download_wlasl_clips.py --limit 50
"""
import argparse
import csv
import os
import subprocess

CSV_PATH = os.path.join(
    os.path.dirname(__file__), "..", "datasets", "sign_language", "WLASL100", "wlasl100_download_list.csv"
)
OUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "datasets", "sign_language", "WLASL100", "videos"
)


def download_one(url: str, video_id: str, gloss: str) -> bool:
    dest_dir = os.path.join(OUT_DIR, gloss)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"{video_id}.mp4")
    if os.path.exists(dest_path):
        return True
    try:
        # yt-dlp handles YouTube + most direct mp4 links; falls back to
        # curl for plain-http direct video files.
        result = subprocess.run(
            ["yt-dlp", "-o", dest_path, url],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and os.path.exists(dest_path):
            return True
    except Exception:
        pass
    try:
        subprocess.run(["curl", "-L", "-o", dest_path, url], timeout=120, check=True)
        return os.path.exists(dest_path)
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50, help="max clips to download")
    args = parser.parse_args()

    with open(CSV_PATH) as f:
        rows = list(csv.DictReader(f))

    ok, fail = 0, 0
    for row in rows[: args.limit]:
        success = download_one(row["url"], row["video_id"], row["gloss"])
        if success:
            ok += 1
        else:
            fail += 1
        print(f"[{'OK' if success else 'FAIL'}] {row['gloss']} / {row['video_id']}")

    print(f"\nDone. {ok} downloaded, {fail} failed (dead links are common in WLASL).")


if __name__ == "__main__":
    main()
