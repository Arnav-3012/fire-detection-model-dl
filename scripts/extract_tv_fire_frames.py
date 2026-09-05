"""One-time data collection utility: extracts evenly-spaced frames from a
developer-recorded video (phone filming a laptop screen playing fireplace
footage) for the FireWatch vision dataset's 7th and final hard-negative
category, "TV or laptop screen showing fire footage" (plan.md §6.4).

Not part of edge/train/agent application code — same category as
scripts/test_camera.py and scripts/fetch_hard_negatives.py. Exempt from
config.yaml-for-tunables per info.md §3.1: this is a one-off dataset-building
input, not a runtime tunable.

Unlike the other 6 hard-negative categories (scripts/fetch_hard_negatives.py,
DuckDuckGo image search), this category is not a natural photography or
stock-search subject — a screen actually showing fire footage playing — so it
was manually filmed by the developer and is processed here instead of scraped.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

TARGET_FRAME_COUNT = 30
# Defaults are the original tv_laptop_fire category. --output-dir/--prefix
# (added 2026-09-04) let the SAME extraction logic serve later self-filmed
# hard-negative categories (first: bright_light_textured_wall) instead of
# copy-pasting this file per category -- the frame-selection behaviour must
# stay identical across categories for the dataset to be consistent.
OUTPUT_DIR = Path("data/hard_negatives/tv_laptop_fire")
FILENAME_PREFIX = "tv_fire"
MIN_MEAN_BRIGHTNESS = 15.0  # 0-255 scale; below this a frame is treated as dark/blank/corrupt
ADJACENT_SEARCH_RADIUS = 10  # frames to search forward/backward for a usable replacement


def is_frame_valid(frame: np.ndarray) -> bool:
    """Basic sanity check: reject extremely dark, blank, or corrupt frames.

    A phone recording a screen can catch a black frame during a scene cut,
    or occasionally drop a corrupt frame on decode. Mean pixel brightness is
    a cheap, sufficient proxy for "this frame contains a visible image" —
    the actual content need not be analyzed further at this stage.
    """
    if frame is None or frame.size == 0:
        return False
    return float(np.mean(frame)) >= MIN_MEAN_BRIGHTNESS


def find_valid_adjacent_frame(
    cap: cv2.VideoCapture, target_index: int, total_frames: int
) -> tuple[np.ndarray, int] | None:
    """Search outward from target_index for a usable frame.

    Alternates checking one step further out on each side so the replacement
    stays as close as possible to the original evenly-spaced target.
    """
    for offset in range(1, ADJACENT_SEARCH_RADIUS + 1):
        for candidate in (target_index - offset, target_index + offset):
            if candidate < 0 or candidate >= total_frames:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, candidate)
            ok, frame = cap.read()
            if ok and is_frame_valid(frame):
                return frame, candidate
    return None


def extract_frames(video_path: Path, output_dir: Path = OUTPUT_DIR,
                   prefix: str = FILENAME_PREFIX) -> None:
    """Extract TARGET_FRAME_COUNT evenly-spaced frames from video_path into output_dir."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(
            f"[ERROR] Could not open video: {video_path}\n"
            "Likely causes: wrong path, unsupported codec, or a corrupt file."
        )
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_s = total_frames / fps if fps else 0.0

    if fps <= 0 or total_frames <= 0:
        print(f"[ERROR] Video reports invalid fps={fps} or frame_count={total_frames}.")
        cap.release()
        sys.exit(1)

    print(f"Video: {video_path}")
    print(f"Duration: {duration_s:.1f}s  |  FPS: {fps:.2f}  |  Total frames: {total_frames}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Evenly spaced target indices across the full duration, computed from the
    # actual frame count rather than an assumed length.
    target_indices = np.linspace(0, total_frames - 1, TARGET_FRAME_COUNT, dtype=int)

    saved = 0
    skipped_replaced = 0
    skipped_unrecoverable = 0

    for output_num, target_index in enumerate(target_indices, start=1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(target_index))
        ok, frame = cap.read()

        used_index = int(target_index)
        if not ok or not is_frame_valid(frame):
            print(
                f"[SKIP] frame {target_index} (dark/blank/corrupt) — "
                "searching adjacent frames"
            )
            replacement = find_valid_adjacent_frame(cap, int(target_index), total_frames)
            if replacement is None:
                print(f"[SKIP] no valid replacement found near frame {target_index}")
                skipped_unrecoverable += 1
                continue
            frame, used_index = replacement
            skipped_replaced += 1
            print(f"[REPLACED] using frame {used_index} instead")

        dest = output_dir / f"{prefix}_{output_num:03d}.jpg"
        cv2.imwrite(str(dest), frame)
        saved += 1

    cap.release()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Video duration:        {duration_s:.1f}s")
    print(f"Total frames read:     {total_frames}")
    print(f"Frames extracted:      {saved}/{TARGET_FRAME_COUNT}")
    print(f"Skipped and replaced:  {skipped_replaced}")
    print(f"Skipped unrecoverable: {skipped_unrecoverable}")
    print(f"Output directory:      {output_dir}/")
    print("=" * 60)

    if saved < TARGET_FRAME_COUNT:
        print(
            f"\n[WARNING] Only {saved}/{TARGET_FRAME_COUNT} frames saved. "
            "Some target positions had no valid frame within the search radius."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract evenly-spaced frames from a recorded video for the "
            "tv_laptop_fire hard-negative category (plan.md §6.4)."
        )
    )
    parser.add_argument(
        "--video-path",
        type=Path,
        required=True,
        help="Path to the recorded video file.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=OUTPUT_DIR,
        help="Hard-negative category folder to write into (default: tv_laptop_fire).",
    )
    parser.add_argument(
        "--prefix", default=FILENAME_PREFIX,
        help="Output filename prefix, <prefix>_NNN.jpg (default: tv_fire).",
    )
    args = parser.parse_args()

    if not args.video_path.exists():
        print(f"[ERROR] Video file not found: {args.video_path}")
        sys.exit(1)

    extract_frames(args.video_path, args.output_dir, args.prefix)


if __name__ == "__main__":
    main()
