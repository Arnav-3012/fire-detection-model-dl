"""Controlled v2-vs-v3 comparison at the EXACT same fire_candle.mov frames
Grad-CAM analyzed on v2 (logs.md Phase 5, "Grad-CAM investigation" addendum:
p_fire 0.748, 0.188, 0.064, 0.026). Re-running pick_representative_frames()
against v3's own p_fire curve would likely select DIFFERENT frame indices
(v3's curve differs from v2's), which would not be a controlled comparison --
this script recovers v2's exact frame indices deterministically (ONNX
inference and frame decode are both documented as deterministic in
scratch_stove_gradcam.py) and evaluates v3 at those same indices.

Not a phase deliverable -- one-off comparison script, same status as
scratch_stove_gradcam.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "edge"))
from vision import VisionModel  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scratch_stove_gradcam import scan_p_fire_per_frame, pick_representative_frames  # noqa: E402

VIDEO_PATH = Path("eval/adversarial/fire_candle.mov")
V2_ONNX_PATH = "models/fire_mnv3_v2.onnx"
V3_ONNX_PATH = "models/fire_mnv3_v3.onnx"


def scan_with_model_path(video_path: Path, onnx_path: str) -> list[float]:
    import yaml
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    config["vision"]["model_path"] = onnx_path
    tmp_path = Path(f"eval/_compare_tmp_{Path(onnx_path).stem}.yaml")
    with open(tmp_path, "w") as f:
        yaml.safe_dump(config, f)
    model = VisionModel(config_path=str(tmp_path))
    tmp_path.unlink()

    import cv2
    cap = cv2.VideoCapture(str(video_path))
    p_fire_values = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        p_fire_values.append(model.predict(frame)["p_fire"])
    cap.release()
    return p_fire_values


def main() -> None:
    print(f"Re-scanning {VIDEO_PATH} with v2 ({V2_ONNX_PATH}) to recover the exact frame indices...")
    v2_p_fire = scan_with_model_path(VIDEO_PATH, V2_ONNX_PATH)
    frame_indices = pick_representative_frames(v2_p_fire, n=4)
    print(f"v2 max p_fire={max(v2_p_fire):.4f} (expect 0.7484, per logs.md)")
    print(f"Recovered frame indices: {frame_indices}")
    for idx in frame_indices:
        print(f"  frame {idx}: v2 p_fire={v2_p_fire[idx]:.4f}")

    print(f"\nScanning {VIDEO_PATH} with v3 ({V3_ONNX_PATH})...")
    v3_p_fire = scan_with_model_path(VIDEO_PATH, V3_ONNX_PATH)
    print(f"v3 max p_fire={max(v3_p_fire):.4f} min p_fire={min(v3_p_fire):.4f} (full clip)")

    print("\n=== Headline comparison: p_fire at the SAME frames Grad-CAM analyzed ===")
    print(f"{'Frame idx':>10} | {'v2 p_fire':>10} | {'v3 p_fire':>10} | {'Delta':>10} | {'v3 >= tau(0.70)':>16}")
    for idx in frame_indices:
        v2_val = v2_p_fire[idx]
        v3_val = v3_p_fire[idx]
        delta = v3_val - v2_val
        print(f"{idx:>10} | {v2_val:>10.4f} | {v3_val:>10.4f} | {delta:>+10.4f} | {'YES' if v3_val >= 0.70 else 'no':>16}")

    tau_frames_v2 = sum(1 for p in v2_p_fire if p >= 0.70)
    tau_frames_v3 = sum(1 for p in v3_p_fire if p >= 0.70)
    print(f"\nFull-clip frames with p_fire >= tau (0.70): v2={tau_frames_v2}/{len(v2_p_fire)}, v3={tau_frames_v3}/{len(v3_p_fire)}")


if __name__ == "__main__":
    main()
