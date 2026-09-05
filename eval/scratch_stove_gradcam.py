"""ONE-OFF diagnostic for the Day 5 gas-stove-flame (candle substitute) zero-
alarm finding (logs.md Phase 5). NOT a phase deliverable, NOT wired into any
pipeline -- reuses eval/inspect_model.py's Grad-CAM implementation exactly
(generate_gradcam, save_gradcam_overlay) and edge/vision.py's exact
preprocessing (via VisionModel) to find which frames to look at, rather than
reimplementing either.

Two-step process:
  1. Run v2's ONNX model (models/fire_mnv3_v2.onnx) over every frame of
     fire_candle.mov via VisionModel.predict() -- identical code path to the
     Day 5 eval -- to find each frame's p_fire.
  2. Pick 4 frames spanning the observed p_fire range, then run Grad-CAM on
     each using v2's .pt checkpoint (fire_mnv3_v2.pt) so gradients are
     available (ONNX has none) -- same generate_gradcam() function
     eval/inspect_model.py already uses for the val-set images.

Outputs: eval/model_understanding/gradcam_stove_flame_frame_N.png
"""

import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
from torchvision import models

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "edge"))
from vision import VisionModel  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_model import generate_gradcam, save_gradcam_overlay, IMAGENET_MEAN, IMAGENET_STD  # noqa: E402

VIDEO_PATH = Path("eval/adversarial/fire_candle.mov")
V2_ONNX_PATH = "models/fire_mnv3_v2.onnx"
V2_PT_PATH = Path("models/fire_mnv3_v2.pt")
OUT_DIR = Path("eval/model_understanding")


def scan_p_fire_per_frame(video_path: Path) -> list[float]:
    """Run v2 (ONNX, same path as the Day 5 eval) over every frame, no
    temporal voter involved -- we want the raw per-frame p_fire curve.
    """
    import yaml
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    config["vision"]["model_path"] = V2_ONNX_PATH
    tmp_path = Path("eval/_gradcam_scan_tmp.yaml")
    with open(tmp_path, "w") as f:
        yaml.safe_dump(config, f)
    model = VisionModel(config_path=str(tmp_path))
    tmp_path.unlink()

    cap = cv2.VideoCapture(str(video_path))
    p_fire_values = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        result = model.predict(frame)
        p_fire_values.append(result["p_fire"])
    cap.release()
    return p_fire_values


def pick_representative_frames(p_fire_values: list[float], n: int = 4) -> list[int]:
    """Pick frame indices spanning the observed p_fire range, per this
    session's task: one near the max (0.656-0.748 range noted in logs.md),
    one or two at lower-but-still-elevated points, and one from the bulk of
    the clip -- so the comparison is "high confidence vs modestly elevated
    vs low", not "high vs near-zero", which would tell us little about why
    confidence tops out below tau.
    """
    arr = np.array(p_fire_values)
    order = np.argsort(arr)[::-1]  # descending by p_fire
    n_frames = len(arr)

    picks = [int(order[0])]  # global max
    # Next: a frame roughly in the top 5% (still meaningfully elevated).
    picks.append(int(order[max(1, n_frames // 20)]))
    # Next: a frame roughly at the top-25% mark (moderate signal).
    picks.append(int(order[max(2, n_frames // 4)]))
    # Last: median frame (typical/background frame, for contrast).
    median_idx = int(np.argsort(arr)[n_frames // 2])
    picks.append(median_idx)

    # De-duplicate while preserving order, in case of small-clip collisions.
    seen = set()
    unique_picks = []
    for p in picks:
        if p not in seen:
            seen.add(p)
            unique_picks.append(p)
    return unique_picks[:n]


def load_pt_model(checkpoint_path: Path) -> tuple[nn.Module, dict[str, int]]:
    """Identical to inspect_model.py's load_model() -- duplicated in this
    scratch script only because that function prints val-set-specific
    checkpoint info we don't need here; the actual reconstruction logic
    (architecture + state_dict load) is copied verbatim, not reimplemented
    differently.
    """
    model = models.mobilenet_v3_small(weights=None)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, 3)
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model, checkpoint["class_to_idx"]


def frame_to_tensor_and_display(frame_bgr: np.ndarray, input_size: int = 224):
    """Same preprocessing as edge/vision.py's VisionModel._preprocess (BGR->
    RGB, resize, ImageNet normalize) but returning a torch tensor with
    requires_grad-friendly float32, plus a 0-1 display array -- mirrors
    inspect_model.py's load_and_preprocess_image() but from an in-memory
    video frame instead of a file on disk.
    """
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (input_size, input_size))
    display_img = resized.astype(np.float32) / 255.0

    normalized = (display_img - IMAGENET_MEAN) / IMAGENET_STD
    chw = normalized.transpose(2, 0, 1).astype(np.float32)
    tensor = torch.from_numpy(chw).unsqueeze(0)
    return tensor, display_img


def extract_frame(video_path: Path, frame_index: int) -> np.ndarray:
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"Could not read frame {frame_index} from {video_path}")
    return frame


def main() -> None:
    print(f"Scanning {VIDEO_PATH} with v2 ({V2_ONNX_PATH}) for per-frame p_fire...")
    p_fire_values = scan_p_fire_per_frame(VIDEO_PATH)
    print(f"  {len(p_fire_values)} frames scanned. "
          f"max={max(p_fire_values):.4f} min={min(p_fire_values):.4f}")

    frame_indices = pick_representative_frames(p_fire_values, n=4)
    print(f"Selected frame indices: {frame_indices}")
    for idx in frame_indices:
        print(f"  frame {idx}: p_fire={p_fire_values[idx]:.4f}")

    model, class_to_idx = load_pt_model(V2_PT_PATH)
    idx_to_class = {i: c for c, i in class_to_idx.items()}
    fire_idx = class_to_idx["fire"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for n, frame_idx in enumerate(frame_indices, start=1):
        p_fire = p_fire_values[frame_idx]
        raw_frame = extract_frame(VIDEO_PATH, frame_idx)
        tensor, display_img = frame_to_tensor_and_display(raw_frame)

        with torch.no_grad():
            logits = model(tensor)
            pred_idx = int(logits.argmax(dim=1))
        predicted_class = idx_to_class[pred_idx]

        # Grad-CAM w.r.t. the FIRE class specifically (not argmax) -- these
        # frames are the gas-stove-flame video, genuinely fire-class content
        # per plan.md 6.4, regardless of what the model's argmax says. We
        # want to see what evidence the model found FOR fire, even on frames
        # it did not ultimately call fire.
        cam = generate_gradcam(model, tensor, fire_idx)

        out_path = OUT_DIR / f"gradcam_stove_flame_frame_{n}.png"
        label = f"stove_flame_frame{n} (p_fire={p_fire:.3f})"
        save_gradcam_overlay(display_img, cam, label, predicted_class, out_path)
        print(f"  saved {out_path}  (frame_idx={frame_idx}, p_fire={p_fire:.4f}, "
              f"model predicted={predicted_class})")


if __name__ == "__main__":
    main()
