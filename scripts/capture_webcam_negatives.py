"""One-time data collection utility: capture hard-negative frames from the
edge device's OWN webcam, for a scene the live loop misclassifies.

Why this exists (2026-09-04): the bright-lit textured wall / ceiling grid
produced a sustained smoke WATCH on the live MacBook webcam (p_smoke
0.50-0.66, 8-of-8 votes), yet the phone-filmed clip of the same wall never
crossed the 0.45 gate offline (max p_smoke 0.357). The failing input is
what THIS camera produces -- its sensor, exposure, white balance and field
of view -- so the hard negatives must come from it. Same category as
scripts/extract_tv_fire_frames.py: one-off dataset input, exempt from
config.yaml-for-tunables (info.md 3.1).

Reuses edge/camera.py and edge/vision.py verbatim (info.md 3.4): frames are
saved exactly as the edge loop sees them, and each saved frame's p_smoke is
printed so the capture doubles as the "before" measurement for the retrain.

Optionally records every captured frame to a video (--record-video) so
eval/run_eval.py --extra-video can score a checkpoint on a held-out webcam
clip offline. Record the held-out clip in a SEPARATE run from the training
capture (shift the laptop slightly), never from the same frames.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "edge"))
from camera import Camera  # noqa: E402
from vision import VisionModel  # noqa: E402

MIN_MEAN_BRIGHTNESS = 15.0  # same dark/blank floor as extract_tv_fire_frames.py


def next_free_index(output_dir: Path, prefix: str) -> int:
    """Resume numbering after existing <prefix>_NNN files (same fix as fetch_hard_negatives.py)."""
    existing = [int(p.stem.rsplit("_", 1)[1]) for p in output_dir.glob(f"{prefix}_*.jpg")
                if p.stem.rsplit("_", 1)[1].isdigit()]
    return max(existing, default=0) + 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("data/hard_negatives/bright_light_textured_wall_webcam"))
    parser.add_argument("--prefix", default="bright_wall_cam")
    parser.add_argument("--seconds", type=float, default=30.0, help="capture duration")
    parser.add_argument("--count", type=int, default=30, help="frames to save, evenly spaced in time")
    parser.add_argument("--record-video", type=Path, default=None,
                        help="also write EVERY frame to this .avi (MJPG) for offline eval")
    parser.add_argument("--no-save", action="store_true",
                        help="measure only (print p_smoke stats), save no frames")
    parser.add_argument("--preview", action="store_true",
                        help="grab ONE frame, write data/capture_preview.jpg and open it, then exit -- "
                             "check the framing (scene only, no people) before a real capture")
    args = parser.parse_args()

    cam = Camera()
    first = cam.read()
    if args.preview:
        # Two takes on 2026-09-04 captured the developer and colleagues because a
        # lid-mounted camera cannot be aimed by eye; look before recording.
        cam.release()
        preview = Path("data/capture_preview.jpg")
        cv2.imwrite(str(preview), first)
        print(f"Preview written to {preview} -- opening it. Re-aim until it shows ONLY the scene.")
        subprocess.run(["open", str(preview)], check=False)
        return
    model = VisionModel()  # production model from config.yaml -- the "before"
    writer = None
    if args.record_video:
        args.record_video.parent.mkdir(parents=True, exist_ok=True)
        h, w = first.shape[:2]
        writer = cv2.VideoWriter(str(args.record_video), cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (w, h))

    if not args.no_save:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    index = next_free_index(args.output_dir, args.prefix) if not args.no_save else 0
    save_times = np.linspace(0.0, args.seconds, args.count, endpoint=False) if args.count else []
    next_save = 0

    print(f"Capturing {args.seconds:.0f}s from the webcam; saving {0 if args.no_save else args.count} "
          f"frames to {args.output_dir}/ | frame the SCENE ONLY, stay out of shot.")
    t0 = time.monotonic()
    p_smokes: list[float] = []
    smoke_flags = 0
    saved = 0
    while (elapsed := time.monotonic() - t0) < args.seconds:
        frame = cam.read()
        if writer is not None:
            writer.write(frame)
        result = model.predict(frame)
        p_smokes.append(result["p_smoke"])
        smoke_flags += int(result["smoke"])

        if next_save < len(save_times) and elapsed >= save_times[next_save]:
            next_save += 1
            if float(np.mean(frame)) < MIN_MEAN_BRIGHTNESS:
                print(f"[SKIP] t={elapsed:5.1f}s dark/blank frame")
                continue
            if not args.no_save:
                dest = args.output_dir / f"{args.prefix}_{index:03d}.jpg"
                cv2.imwrite(str(dest), frame)
                index += 1
                saved += 1
                print(f"[SAVED] {dest.name}  t={elapsed:5.1f}s  p_smoke={result['p_smoke']:.2f}  "
                      f"p_fire={result['p_fire']:.2f}  smoke_flag={result['smoke']}")

    cam.release()
    if writer is not None:
        writer.release()

    p = np.array(p_smokes)
    print("\n" + "=" * 60 + "\nSUMMARY (production model, this capture)\n" + "=" * 60)
    print(f"Frames seen:            {len(p)}")
    print(f"Frames saved:           {saved}")
    print(f"p_smoke mean/median/max {p.mean():.3f} / {np.median(p):.3f} / {p.max():.3f}")
    print(f"Frames passing smoke gate ({model.smoke_decision_threshold}, argmax-AND): "
          f"{smoke_flags}/{len(p)} = {100 * smoke_flags / max(len(p), 1):.1f}%")
    if writer is not None:
        print(f"Video written:          {args.record_video}")
    print("=" * 60)


if __name__ == "__main__":
    main()
