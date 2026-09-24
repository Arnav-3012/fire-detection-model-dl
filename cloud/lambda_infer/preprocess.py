"""Frame -> model tensor. THE contract shared by local inference and Lambda.

WHY THIS FILE EXISTS AT ALL. edge/vision.py's VisionModel._preprocess()
already did this, and Stage 6's Lambda needs the identical operation. The
obvious move -- retype those four lines in the Lambda handler -- is the
one thing phase12.md step 7 explicitly flags as the project's classic
silent bug: preprocessing that diverges does not crash, it just produces
plausible-looking wrong probabilities. So the steps live here once, and
both callers import them.

MEASURED, NOT ASSUMED (2026-09-23). Before writing this, the cheaper
option was tested: drop the ~130MB OpenCV dependency from the Lambda zip
and resize with Pillow instead. Over 400 val frames, cv2 vs PIL bilinear
resize of the SAME image through the SAME model gave:

    mean |delta p_fire| = 0.035,  p95 = 0.193,  max = 0.556
    decision flips across the 0.30 threshold: 8 / 400  (2%)

Two percent of frames would get a different verdict from the resize
library alone. That is fatal for this specific feature, not merely
untidy: additiontoplan.md Item A's entire premise is that a local/cloud
DISAGREEMENT carries information ("local's downscale hid something"). A
2% manufactured disagreement rate would drown that signal in library
noise and make the agree/disagree display actively misleading. OpenCV
stays in the zip; the size is the price of the feature meaning anything.

INTERPOLATION IS PART OF THE CONTRACT. cv2.resize()'s default is
INTER_LINEAR and it is passed explicitly below -- this value is load-
bearing per the numbers above, and a future default change upstream must
not silently alter it.
"""

import cv2
import numpy as np

# Duplicated from edge/vision.py deliberately: Lambda ships this file
# WITHOUT edge/ on its path, so importing them from there would make the
# zip depend on the whole edge package. They are properties of the
# trained model (ImageNet-pretrained backbone), fixed for the life of
# models/fire_mnv3.onnx -- not tunables that could drift apart.
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

INPUT_SIZE = 224  # locked by the ONNX export; see crops.py's header


def preprocess_rgb(rgb: np.ndarray, input_size: int = INPUT_SIZE) -> np.ndarray:
    """One RGB image -> (3, input_size, input_size) float32 CHW, no batch dim.

    Takes RGB, not BGR: the BGR->RGB swap belongs to whoever decoded the
    frame (OpenCV hands back BGR, a JPEG decoder may not), so doing it
    here would double-swap for callers that already have RGB.
    """
    resized = cv2.resize(rgb, (input_size, input_size), interpolation=cv2.INTER_LINEAR)
    normalized = (resized.astype(np.float32) / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
    return normalized.transpose(2, 0, 1)  # HWC -> CHW


def preprocess_bgr(bgr: np.ndarray, input_size: int = INPUT_SIZE) -> np.ndarray:
    """BGR (what cv2.imread/VideoCapture return) -> CHW tensor, no batch dim.

    This is exactly edge/vision.py's _preprocess() minus the batch axis:
    BGR->RGB, resize, /255, ImageNet normalize, HWC->CHW.
    """
    return preprocess_rgb(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), input_size)


def softmax(logits: np.ndarray) -> np.ndarray:
    """Row-wise softmax, max-subtracted for numerical stability.

    Handles both a single (C,) logit vector and a batched (N, C) one --
    the Lambda path always batches, the local path does not.

    The model outputs raw logits; every threshold in this project
    (fire_decision_threshold, TemporalVoter's tau) was swept against
    PROBABILITIES, so logits are never comparable to them directly.
    """
    x = np.atleast_2d(logits)
    e = np.exp(x - x.max(axis=1, keepdims=True))
    probs = e / e.sum(axis=1, keepdims=True)
    return probs[0] if logits.ndim == 1 else probs
