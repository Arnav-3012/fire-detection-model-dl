"""Lambda entry point: the cloud SECOND OPINION on one frame (Stage 6).

CONTRACT WITH THE DETECTOR -- read this before changing anything here.
Nothing this function returns may ever reach edge/fusion.py's fuse().
edge/fusion.py:12-13 states detection is "No model, no LLM, no network",
and plan.md 2's offline claim rests on it: a WAN outage, a throttled
Lambda, a bad deploy or an expired key must be incapable of downgrading
the local detector. This endpoint is ADVISORY ONLY -- it is displayed
next to the local verdict and never gates the buzzer. Delete this whole
directory and local detection is byte-for-byte identical. That property
is the feature, not a limitation of it.

WHY THE VERDICT IS FULL-FRAME, AND THE CROPS ARE ONLY DIAGNOSTICS.
additiontoplan.md A.1 proposed taking MAX p_fire over five 224x224 crops
of the native frame as the cloud's verdict, on the theory that the
full-frame downscale hides small/distant flame. That was measured on the
val set (2026-09-23, 150 frames/class) before it was built, and it does
not hold:

    rule                    fire-recall   neutral-FP   smoke-FP
    full-frame   @0.30         0.980        0.000       0.047
    5-crop MAX   @0.30         0.993        0.180       0.227
    5-crop MAX   @0.70         0.687        0.033       0.033
    5-crop MEAN  @0.30         0.920        0.033       0.033

There is NO threshold at which 5-crop max beats the full-frame baseline.
The reason is statistical, not a bug: the max of five draws shifts the
distribution upward for EVERY frame, not only fire ones, so any scene
with a warm-coloured corner clears the bar. On clean neutral frames that
is 0 false positives -> 23 of 120. It bought +1.3% recall for +18% FP.

So the crops stayed and the DECISION RULE went. The verdict below is
full-frame -- identical arithmetic to local inference -- and the five
crop scores ride along as detail. They are genuinely informative as
detail; the spread between max and mean separates the classes cleanly:

    fire max 0.78 / mean 0.45 -> spread 0.33     (localised hot region)
    neutral                   -> spread 0.10
    smoke                     -> spread 0.16

That is the shape distinction worth showing a human: a high max with a
LOW mean is one hot corner (what a real distant flame looks like), while
high max with a HIGH mean is fire-like everywhere -- a wall of flame, or
a screen showing one (edge/fusion.py rule 4's known TV limitation).

WHY THE OPINION IS NOT AN ECHO. Running the same model on the same frame
would agree with local by construction and carry no information.
Disagreement here is real because the two see different things: local
votes over a TEMPORAL window (TemporalVoter, N-of-M, phase12.md:164-170)
on a live stream, while this scores ONE frame with no history. Local
saying WARNING while this says 0.11 means the alarm rests on frames
other than this one -- which is exactly what a human checking the
snapshot needs to know.
"""

import base64
import json
import os
import time

import cv2
import numpy as np
import onnxruntime as ort

from crops import CROP_COUNT, build_batch
from preprocess import preprocess_rgb, softmax

# Same mapping as edge/vision.py, and fixed by the training run
# (train/export_onnx.py's class_to_idx) -- a property of the model file,
# not a tunable.
CLASS_TO_IDX = {"fire": 0, "neutral": 1, "smoke": 2}

MODEL_PATH = os.environ.get("MODEL_PATH", os.path.join(os.path.dirname(__file__), "fire_mnv3.onnx"))

# Bound the decode: a malformed or hostile payload must not turn into an
# unbounded allocation inside a billed invocation.
MAX_JPEG_BYTES = 4 * 1024 * 1024

# Built once at module import, reused by every invocation on a warm
# container. Rebuilding per call would add ~100ms of session setup to
# each one for no benefit -- ORT sessions are read-only at inference.
_SESSION: ort.InferenceSession | None = None
_INPUT_NAME: str | None = None


def _session() -> tuple[ort.InferenceSession, str]:
    """Lazily build (and then reuse) the ORT session.

    Deliberately lazy rather than at import: an unreadable model file
    then surfaces as a clean error response from the handler instead of
    an import-time crash, which Lambda reports far less legibly.
    """
    global _SESSION, _INPUT_NAME
    if _SESSION is None:
        opts = ort.SessionOptions()
        # Lambda gives one vCPU at typical memory settings; letting ORT
        # spin up its default thread pool costs contention, not speed.
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        _SESSION = ort.InferenceSession(MODEL_PATH, opts, providers=["CPUExecutionProvider"])
        _INPUT_NAME = _SESSION.get_inputs()[0].name
    return _SESSION, _INPUT_NAME


def _decode(event: dict) -> np.ndarray:
    """Event -> RGB frame. Raises ValueError with a caller-useful message.

    Accepts the API Gateway shape (a JSON string body, optionally base64
    encoded by the gateway itself) and a direct dict event, so the same
    function is testable locally without constructing a gateway envelope.
    """
    body = event.get("body", event)
    if isinstance(body, str):
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body)
            body = body.decode("utf-8") if body[:1] in (b"{", b" ") else body
        if isinstance(body, str):
            body = json.loads(body)
    if not isinstance(body, dict) or "jpeg_b64" not in body:
        raise ValueError("expected JSON body with a 'jpeg_b64' field")

    raw = base64.b64decode(body["jpeg_b64"])
    if len(raw) > MAX_JPEG_BYTES:
        raise ValueError(f"jpeg too large: {len(raw)} bytes > {MAX_JPEG_BYTES}")

    bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("jpeg could not be decoded")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def score(rgb: np.ndarray) -> dict:
    """The actual inference. Separated from the Lambda envelope so the
    identical code path is exercised by local tests and by AWS.

    ONE session.run() for all six views: the full frame plus the five
    crops are stacked into a single (6, 3, 224, 224) batch. The model's
    batch axis is dynamic (verified), so this costs one call rather than
    six, and the full frame is index 0 by construction.
    """
    started = time.perf_counter()
    crop_batch, boxes = build_batch(rgb)
    full = preprocess_rgb(rgb)[None]
    batch = np.concatenate([full, crop_batch]).astype(np.float32)

    session, input_name = _session()
    probs = softmax(session.run(None, {input_name: batch})[0])

    fire_idx, smoke_idx = CLASS_TO_IDX["fire"], CLASS_TO_IDX["smoke"]
    full_probs = probs[0]
    crop_fire = probs[1:, fire_idx]

    # argmax of the FULL frame, so "hottest crop" below is always
    # interpretable relative to the verdict rather than to itself.
    hottest = int(np.argmax(crop_fire))
    names = ["centre", "top-left", "top-right", "bottom-left", "bottom-right"]

    return {
        # --- the verdict: full-frame, same arithmetic as local ---------
        "p_fire": float(full_probs[fire_idx]),
        "p_smoke": float(full_probs[smoke_idx]),
        # --- diagnostics: NOT a decision, see the module docstring -----
        "crops": {
            "count": CROP_COUNT,
            "max_p_fire": float(crop_fire.max()),
            "mean_p_fire": float(crop_fire.mean()),
            # max - mean. High spread = one localised hot region; low
            # spread = uniformly fire-like (a wall of flame, or a screen).
            "spread": float(crop_fire.max() - crop_fire.mean()),
            "hottest_region": names[hottest],
            "hottest_box": list(boxes[hottest]),
            "per_crop_p_fire": [float(v) for v in crop_fire],
        },
        "frame": {"width": int(rgb.shape[1]), "height": int(rgb.shape[0])},
        "inference_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def lambda_handler(event, context):  # noqa: ANN001 (AWS-defined signature)
    """API Gateway entry point. Always returns a well-formed HTTP response.

    Never raises: an exception here becomes a 502 with a stack trace the
    caller cannot act on, and the caller (cloud/second_opinion.py) treats
    any failure as "no opinion" anyway. A clean JSON error is strictly
    more useful and costs the same.
    """
    try:
        result = score(_decode(event))
        return {"statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"ok": True, **result})}
    except ValueError as exc:
        return {"statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"ok": False, "error": str(exc)})}
    except Exception as exc:  # noqa: BLE001 -- see docstring: never raise
        return {"statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"ok": False, "error": f"{exc.__class__.__name__}: {exc}"})}
