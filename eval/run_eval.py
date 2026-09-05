"""Day 5 adversarial evaluation: run the vision pipeline against recorded
video clips and count how many times the temporal voter alarms.

Reuses edge/vision.py's VisionModel + TemporalVoter exactly as the live
edge loop does (info.md 3.4 — no reimplementing detection logic here).
Frames come from cv2.VideoCapture(file) instead of the webcam; everything
downstream of "a BGR frame" is identical to edge/main.py's path.
"""

import argparse
import sys
import time
from pathlib import Path

import cv2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "edge"))
from vision import VisionModel  # noqa: E402

ADVERSARIAL_DIR = Path(__file__).resolve().parent / "adversarial"


def build_model(config_path: str, model_path: str) -> VisionModel:
    """VisionModel reads model_path from config.yaml internally, so to
    evaluate a specific checkpoint we load the config, override the one
    key, and write it to a temp file VisionModel then reads -- keeps
    VisionModel's constructor signature untouched (info.md 3.4) rather than
    bolting an override parameter onto application code for an eval-only
    need.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)
    config["vision"]["model_path"] = model_path

    tmp_config_path = ADVERSARIAL_DIR.parent / "_eval_config_tmp.yaml"
    with open(tmp_config_path, "w") as f:
        yaml.safe_dump(config, f)

    model = VisionModel(config_path=str(tmp_config_path))
    tmp_config_path.unlink()
    return model


def run_video(model: VisionModel, video_path: Path) -> dict:
    """Feed every frame of one video through predict_smoothed() and count
    alarm events. An 'alarm event' is a rising edge (False -> True) of the
    voter's alarm flag, not a raw per-frame count -- otherwise one sustained
    alarm spanning 200 frames would be reported as 200 alarms, which answers
    a different question than info.md 4.2's block/target bars ("<=1 alarm",
    "<=2 alarms") are asking.
    """
    # Fresh voters per video -- state must not leak between clips, since
    # VisionModel owns its voter instances for its whole lifetime.
    model.voter.votes.clear()
    model.smoke_voter.votes.clear()

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    frame_index = 0
    alarm_count = 0
    prev_alarm = False
    first_alarm_frame = None
    max_p_fire = 0.0
    # Smoke side (added 2026-09-04): the same rising-edge count over the
    # smoke voter's `smoke_sustained` -- i.e. how many times fusion rule 5
    # would have produced a WATCH from vision alone -- plus how many raw
    # frames cleared the argmax-AND smoke gate, so a "0 WATCH events" result
    # can be told apart from "0 events but 40% of frames voted smoke".
    smoke_event_count = 0
    prev_smoke = False
    smoke_frames = 0
    max_p_smoke = 0.0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        result = model.predict_smoothed(frame)
        max_p_fire = max(max_p_fire, result["p_fire"])
        max_p_smoke = max(max_p_smoke, result["p_smoke"])
        smoke_frames += int(result["smoke"])

        if result["alarm"] and not prev_alarm:
            alarm_count += 1
            if first_alarm_frame is None:
                first_alarm_frame = frame_index
        prev_alarm = result["alarm"]
        if result["smoke_sustained"] and not prev_smoke:
            smoke_event_count += 1
        prev_smoke = result["smoke_sustained"]

        frame_index += 1

    cap.release()

    time_to_first_alarm = (first_alarm_frame / fps) if first_alarm_frame is not None else None

    return {
        "video": video_path.name,
        "frames": frame_index,
        "fps": fps,
        "duration_s": frame_index / fps if fps else None,
        "alarm_count": alarm_count,
        "max_p_fire": max_p_fire,
        "time_to_first_alarm_s": time_to_first_alarm,
        "smoke_event_count": smoke_event_count,
        "smoke_frame_fraction": smoke_frames / frame_index if frame_index else 0.0,
        "max_p_smoke": max_p_smoke,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True, help="ONNX model file to evaluate")
    parser.add_argument("--config", default="config.yaml", help="Base config.yaml path")
    parser.add_argument(
        "--adversarial-dir",
        default=str(ADVERSARIAL_DIR),
        help="Directory of adversarial video clips",
    )
    parser.add_argument(
        "--extra-video", type=Path, nargs="*", default=[],
        help="Additional clip(s) to run after the adversarial set, e.g. the "
             "self-filmed bright-wall footage a hard-negative category came from.",
    )
    args = parser.parse_args()

    video_dir = Path(args.adversarial_dir)
    videos = sorted(video_dir.glob("*.mov")) + sorted(video_dir.glob("*.mp4"))
    if not videos:
        print(f"[ERROR] No video files found in {video_dir}", file=sys.stderr)
        sys.exit(1)
    videos += list(args.extra_video)

    model = build_model(args.config, args.model_path)

    print(f"Model: {args.model_path}")
    print(f"{'Video':<28} {'Frames':>7} {'Dur(s)':>7} {'Alarms':>7} {'MaxP(fire)':>11} {'TimeToAlarm(s)':>15}"
          f" {'SmokeWATCH':>10} {'SmokeFr%':>8} {'MaxP(smk)':>10}")
    results = []
    for video_path in videos:
        t0 = time.perf_counter()
        result = run_video(model, video_path)
        elapsed = time.perf_counter() - t0
        results.append(result)
        tta = f"{result['time_to_first_alarm_s']:.2f}" if result["time_to_first_alarm_s"] is not None else "-"
        print(
            f"{result['video']:<28} {result['frames']:>7} {result['duration_s']:>7.1f} "
            f"{result['alarm_count']:>7} {result['max_p_fire']:>11.4f} {tta:>15}"
            f" {result['smoke_event_count']:>10} {100 * result['smoke_frame_fraction']:>7.1f}% "
            f"{result['max_p_smoke']:>10.4f}"
            f"   (processed in {elapsed:.1f}s)"
        )

    return results


if __name__ == "__main__":
    main()
