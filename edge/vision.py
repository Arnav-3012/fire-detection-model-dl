"""Single-frame fire/smoke classification via the exported ONNX model.

Model inference only — no camera, temporal smoothing, or fusion logic
belongs here (info.md 3.4). Temporal smoothing (TemporalVoter) is Day 4.
"""

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import yaml

# Fixed by the training run itself (train/export_onnx.py's printed
# checkpoint['class_to_idx'], logs.md Phase 3 addendum) -- NOT alphabetical
# by coincidence for fire/neutral, but genuinely alphabetical for all three.
# Hardcoded here (not config.yaml) because it is a property of the trained
# model file, not a tunable -- changing it would require retraining, not
# editing a config value.
CLASS_TO_IDX = {"fire": 0, "neutral": 1, "smoke": 2}

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class VisionModel:
    """Loads the exported ONNX classifier and runs single-frame inference.

    Preprocessing must exactly match training (train/train_classifier.py) and
    export verification (train/export_onnx.py): BGR->RGB, resize to
    input_size, scale to [0,1], normalize with ImageNet mean/std, then
    NCHW. Any mismatch here is the classic silent bug where the model loads
    fine and produces plausible-looking but wrong probabilities.
    """

    def __init__(self, config_path: str = "config.yaml") -> None:
        with open(config_path) as f:
            config = yaml.safe_load(f)["vision"]

        self.input_size: int = config["input_size"]
        self.fire_decision_threshold: float = config["fire_decision_threshold"]

        model_path = Path(config["model_path"])
        self.session = ort.InferenceSession(str(model_path))
        self.input_name = self.session.get_inputs()[0].name

    def _preprocess(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Convert a raw BGR camera frame to the model's expected input tensor.

        OpenCV reads and returns frames in BGR; the model was trained on
        torchvision ImageFolder images, which decode to RGB -- skipping this
        swap silently swaps the red and blue channels feeding the network,
        which is exactly the kind of preprocessing bug that produces a
        plausible-but-wrong probability distribution rather than a crash.
        """
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (self.input_size, self.input_size))
        normalized = (resized.astype(np.float32) / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
        chw = normalized.transpose(2, 0, 1)  # HWC -> CHW
        return np.expand_dims(chw, axis=0)  # add batch dim -> NCHW

    def predict(self, frame_bgr: np.ndarray) -> dict[str, bool | float]:
        """Run inference on one frame and return fire/smoke decisions.

        'fire' uses fire_decision_threshold from config.yaml (0.30, tuned in
        Phase 2 to clear info.md 4.1's recall/precision block bars) -- a
        threshold decision, not argmax, because Phase 2 found argmax alone
        (implicit 0.50 threshold) failed the fire recall block bar.

        'smoke' uses argmax (highest-probability class) instead, because
        config.yaml has no smoke-equivalent threshold -- Phase 2 only tuned
        and set the fire threshold. Inventing a smoke threshold without a
        tuning pass (per info.md 3.1/2.4) would be a fabricated number, so
        this is deliberately left as argmax until a real decision is made.
        This means 'fire' and 'smoke' can theoretically both be true (fire
        prob >= 0.30 while smoke happens to also be the single highest
        class) -- callers should treat 'fire' as authoritative per info.md
        4.1's priority ordering, not treat the two flags as mutually
        exclusive.
        """
        tensor = self._preprocess(frame_bgr)
        logits = self.session.run(None, {self.input_name: tensor})[0][0]

        # softmax for interpretable probabilities; raw logits are not
        # comparable across frames or to the tuned threshold, which was
        # swept and set against probabilities (eval/threshold_sweep.py).
        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()

        p_fire = float(probs[CLASS_TO_IDX["fire"]])
        p_smoke = float(probs[CLASS_TO_IDX["smoke"]])
        argmax_class = int(probs.argmax())

        return {
            "fire": p_fire >= self.fire_decision_threshold,
            "smoke": argmax_class == CLASS_TO_IDX["smoke"],
            "p_fire": p_fire,
            "p_smoke": p_smoke,
        }


if __name__ == "__main__":
    # Throwaway smoke test -- confirms preprocessing produces a sensible
    # probability distribution on a real frame before main.py depends on it.
    from camera import Camera

    cam = Camera()
    frame = cam.read()
    cam.release()

    model = VisionModel()
    result = model.predict(frame)
    print(result)
