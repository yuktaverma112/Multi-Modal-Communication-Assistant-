"""
scripts/explore_wlasl.py

WLASL_v0.3.json (as distributed) contains METADATA ONLY: for each of the
2000 English sign glosses, a list of instances with a source video URL,
bounding box, signer id, frame range, and train/val/test split -- it does
NOT contain the video files themselves.

NOTE: this script has already been run once -- its outputs
(wlasl100_glosses.json, wlasl100_download_list.csv) are committed in
datasets/sign_language/WLASL100/. The 12MB raw WLASL_v0.3.json this
script reads was deleted afterwards to keep the repo lean (it was a
one-time input, not something the running app needs). To regenerate
or change the top-100 list, re-download it from
https://github.com/dxli94/WLASL (see their `start_kit/`) into
datasets/sign_language/WLASL100/WLASL_v0.3.json and re-run this script.

This script:
  1. Loads the metadata.
  2. Picks the top-100 glosses by number of available instances (a
     reasonable "WLASL100" subset, matching the benchmark naming used
     in sign-language-recognition literature).
  3. Writes datasets/sign_language/WLASL100/wlasl100_glosses.json (the
     class list) and wlasl100_download_list.csv (video_id, gloss, url,
     split) so you can fetch the actual clips on a machine with full
     internet access.

Usage:
    python scripts/explore_wlasl.py
"""
import os
import json
import csv

WLASL_JSON = os.path.join(
    os.path.dirname(__file__), "..", "datasets", "sign_language", "WLASL100", "WLASL_v0.3.json"
)
OUT_DIR = os.path.dirname(WLASL_JSON)


def main():
    with open(WLASL_JSON) as f:
        data = json.load(f)

    print(f"Total glosses in WLASL_v0.3.json: {len(data)}")

    # Rank glosses by instance count, take top 100
    ranked = sorted(data, key=lambda g: len(g["instances"]), reverse=True)
    top100 = ranked[:100]

    glosses = [g["gloss"] for g in top100]
    with open(os.path.join(OUT_DIR, "wlasl100_glosses.json"), "w") as f:
        json.dump(glosses, f, indent=2)
    print(f"Wrote {len(glosses)} class names to wlasl100_glosses.json")

    rows = []
    for g in top100:
        for inst in g["instances"]:
            rows.append({
                "gloss": g["gloss"],
                "video_id": inst["video_id"],
                "signer_id": inst["signer_id"],
                "split": inst["split"],
                "url": inst["url"],
                "frame_start": inst["frame_start"],
                "frame_end": inst["frame_end"],
                "bbox": inst["bbox"],
            })

    csv_path = os.path.join(OUT_DIR, "wlasl100_download_list.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} instance rows (video URLs) to wlasl100_download_list.csv")
    print(
        "\nReminder: WLASL is American Sign Language (ASL), not Indian "
        "Sign Language (ISL). Use it only for initial benchmarking / "
        "demonstrating the pipeline on a well-known dataset -- the "
        "custom_ISL dataset is this project's real India-focused "
        "contribution. State this limitation explicitly in your report "
        "(see the project guide, section 5)."
    )
    print(
        "\nTo actually download clips (needs internet + a machine that "
        "isn't network-restricted), see scripts/download_wlasl_clips.py."
    )


if __name__ == "__main__":
    main()
