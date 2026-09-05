"""Fire/smoke classification: single-frame inference + temporal smoothing.

No camera or fusion logic belongs here (info.md 3.4). VisionModel does
single-frame inference; TemporalVoter (Day 4) smooths its output over a
rolling window before anything downstream treats it as an alarm.
"""

from collections import deque
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


class TemporalVoter:
    """N-of-M temporal vote over per-frame fire probabilities (plan.md 6.1).

    Implements:  alarm  <=>  count(last M frames where p_fire > tau) >= N

    Why this exists at all: a single frame's prediction is not fully
    trustworthy on its own. A sunset glint, a reflection, or a momentary
    lighting change can spike p_fire for one frame even on a well-trained
    model — that is normal, expected classifier behavior, not a bug (Phase
    3's live test showed exactly this: frame-to-frame swings from 0.99 down
    to 0.52 and back during genuinely sustained fire). What separates a real
    fire from a glint is *persistence*: fire keeps looking like fire across
    consecutive frames, a glint does not. So the alarm decision is made over
    a window of recent frames, not any single one.

    Threshold note — tau here is DELIBERATELY different from
    fire_decision_threshold (0.30) used by VisionModel.predict(), and the
    two run independently (decision logged in logs.md Phase 4). 0.30 is a
    lenient, recall-optimized bar tuned in Phase 2 so a single frame's
    'fire' flag clears info.md 4.1's 0.95 fire-recall block bar. Tau (0.70,
    plan.md 6.1's original spec) is a stricter bar for the higher-stakes
    question this class answers: not "does this frame look fire-like?" but
    "should we actually alarm?" — a frame must be confidently fire-like to
    count as a vote toward alarming. Collapsing the two would silently drop
    a plan.md-specified value; keeping both means two different "is this
    frame fire" answers exist in the codebase by design, not by accident.
    """

    def __init__(self, frame_threshold: float, window: int, votes_needed: int) -> None:
        """Values come from config.yaml via the caller (info.md 3.1) —
        this class takes plain numbers so it stays a pure, independently
        testable mechanism with no file I/O of its own.
        """
        self.frame_threshold = frame_threshold
        self.votes_needed = votes_needed
        # deque(maxlen=window) is the whole rolling-window mechanism:
        # appending the (window+1)th vote automatically drops the oldest
        # one from the other end. No manual list slicing/trimming, no
        # off-by-one risk, O(1) appends — this "forget the oldest as the
        # newest arrives" behavior is exactly what a rolling window is.
        self.votes: deque[bool] = deque(maxlen=window)

    def cast(self, vote: bool) -> dict[str, bool | int]:
        """Feed one frame's already-decided vote; get the current N-of-M verdict.

        This is the whole rolling-window mechanism, separated from the
        per-frame decision that produces the vote so the SAME window logic
        serves two different per-frame rules: fire's `p_fire > tau` (see
        update()) and smoke's argmax-AND-threshold flag from
        VisionModel.predict() (2026-09-04). Smoke's rule is not a plain
        probability cut, so it cannot be expressed as a frame_threshold —
        hence the vote arrives pre-decided rather than as a probability.

        Why N=5 of M=8 (N/M ~= 0.6) is a sensible default, per plan.md 6.1:
        at N=1 you are trusting a single frame — maximum jitter, exactly the
        glint problem this class exists to solve. At N=M you need unanimous
        agreement — very few false alarms, but you add a full window of
        latency and ONE occluded/blurry frame breaks the chain and resets
        your progress toward alarming. ~0.6 tolerates a few bad frames in
        both directions while still demanding sustained evidence. Tune on
        the Day 5 adversarial videos, not by intuition.
        """
        self.votes.append(vote)
        votes = sum(self.votes)
        return {
            "vote": vote,
            "votes": votes,
            "alarm": votes >= self.votes_needed,
        }

    def update(self, p_fire: float) -> dict[str, bool | int]:
        """Fire's entry point: threshold one frame's p_fire, then cast().

        Strict '>' matches plan.md 6.1's rule verbatim (p_fire > tau) —
        deliberately not normalized to '>=' to mirror predict()'s other,
        unrelated threshold comparison.
        """
        return self.cast(p_fire > self.frame_threshold)


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
        self.smoke_decision_threshold: float = config["smoke_decision_threshold"]

        # Owned voter for predict_smoothed(). Stateful across frames by
        # nature (it *is* the memory of recent frames), while predict()
        # itself stays pure — see predict_smoothed()'s docstring.
        self.voter = TemporalVoter(
            frame_threshold=config["frame_threshold"],
            window=config["window"],
            votes_needed=config["votes_needed"],
        )
        # Second instance of the SAME mechanism for smoke (2026-09-04): live
        # testing showed WATCH firing on isolated, unsustained frames against
        # a patterned background even after the 0.45 argmax-AND gate. Its
        # votes are predict()'s smoke flag fed via cast(), so frame_threshold
        # is never consulted here — passed only because the class requires
        # one; the real per-frame gate is smoke_decision_threshold above.
        # Same window as fire; only N is independently tunable.
        self.smoke_voter = TemporalVoter(
            frame_threshold=self.smoke_decision_threshold,
            window=config["window"],
            votes_needed=config["smoke_votes_needed"],
        )

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

        'smoke' is argmax AND P(smoke) >= smoke_decision_threshold (0.45,
        swept 2026-09-04 in eval/smoke_threshold_sweep.py against v3). Plain
        argmax was the rule until then, and live testing showed it let smoke
        "win" three-way splits at P(smoke) 0.28-0.44 on a neutral scene --
        spurious WATCH states from lighting noise. The rule is deliberately
        a tightening of argmax rather than fire's pure-probability shape: a
        frame where neutral wins is reported as neutral, never smoke, and a
        frame where smoke wins without clearing the threshold falls back to
        not-smoke as well. On the val set this costs one smoke image in 880
        versus argmax and removes zero val false positives -- the val FPs
        are confident (median 0.69), so the live low-confidence band is what
        this gate targets, and val cannot measure that directly.
        'fire' and 'smoke' can still both be true (fire prob >= 0.30 while
        smoke is the confident argmax) -- callers should treat 'fire' as
        authoritative per info.md 4.1's priority ordering, not treat the two
        flags as mutually exclusive.
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
            "smoke": argmax_class == CLASS_TO_IDX["smoke"] and p_smoke >= self.smoke_decision_threshold,
            "p_fire": p_fire,
            "p_smoke": p_smoke,
        }

    def predict_smoothed(self, frame_bgr: np.ndarray) -> dict[str, bool | float | int]:
        """predict() plus the temporal voter, in one call.

        Returns everything predict() returns, merged with the voter's
        output ('vote', 'votes', 'alarm') — the caller gets BOTH the raw
        single-frame result and the smoothed decision, because for
        logging/debugging you need to see what each frame said, not just
        the final verdict ("why didn't it alarm?" is unanswerable from a
        bare boolean).

        Deliberately a separate method rather than folded into predict():
        predict() stays pure and stateless, so Phase 3's single-frame
        behavior is untouched for any future caller that wants the lenient
        fire_decision_threshold signal on its own (per logs.md Phase 4
        decision). This method is stateful — each call advances the voter's
        rolling window — so it must be fed consecutive frames from ONE
        stream; interleaving frames from multiple cameras through one
        VisionModel would corrupt the window's meaning.

        Note the two flags answer different questions at different bars:
        'fire' (single frame, >= 0.30) can be True for many frames while
        'alarm' (N of M frames > 0.70) stays False — that gap is the
        temporal filter doing its job, not a contradiction.

        Smoke mirrors that shape: 'smoke' is the raw per-frame flag,
        'smoke_sustained' is the N-of-M verdict over it ('smoke_votes' is
        the running count). Fusion must consume 'smoke_sustained', never
        'smoke' — a single frame of a patterned wall reading as smoke is
        exactly the noise the voter exists to absorb.
        """
        result = self.predict(frame_bgr)
        smoothed = self.voter.update(result["p_fire"])
        smoke_smoothed = self.smoke_voter.cast(result["smoke"])
        return {
            **result,
            **smoothed,
            "smoke_votes": smoke_smoothed["votes"],
            "smoke_sustained": smoke_smoothed["alarm"],
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
