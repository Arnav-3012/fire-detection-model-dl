"""Five-crop decomposition of a native-resolution frame (additiontoplan.md A.1).

THE PROBLEM THIS SOLVES. The camera captures 640x480. Local inference
squashes that whole frame to 224x224 and the detail is simply gone -- a
small or distant flame occupying 40x40 native pixels lands on ~14x14
after the downscale, which is not much for the network to work with.
That is not a bug in edge/vision.py; it is what single-shot full-frame
classification costs, and it is the same tradeoff at 30 FPS on a laptop.

Lambda has no 30 FPS budget -- it runs once per gas EVENT -- so it can
afford to look closer. It scores five 224x224 windows of the NATIVE
frame and reports the strongest.

WHY MAX IS THE OPERATIVE NUMBER. The question this answers is "does ANY
region of the frame look like fire at full detail?", which is precisely
what the full-frame downscale cannot answer. Mean is reported alongside
because max alone is not interpretable: max 0.9 with mean 0.85 is a
frame that is fire-like everywhere (a wall of flame -- or a TV showing
one), while max 0.9 with mean 0.2 is one hot corner, which is what a
real distant flame looks like. The pair is the signal; either number
alone is not. edge/fusion.py rule 4's known TV-fire limitation is
exactly a case where those two shapes differ.

WHY 224 IS NOT A TUNABLE. Verified against models/fire_mnv3.onnx on
2026-09-23:

    INPUT   input   ['batch', 3, 224, 224]   OUTPUT  logits  ['batch', 3]

Batch is dynamic (a 5-stack runs in ONE session.run call -- confirmed,
returns (5,3)); spatial dims are LOCKED. Feeding 320x320 is rejected
outright with INVALID_ARGUMENT. Higher-resolution inference would need a
re-export from the training checkpoint -- a new artifact requiring its
own eval/ validation, which the no-retraining constraint rules out. So
every idea here lives inside 224x224, by measurement rather than choice.
"""

import numpy as np

from preprocess import INPUT_SIZE, preprocess_rgb

# Centre + four corners. Five is a deliberate ceiling, not an arbitrary
# number: it is the standard 5-crop scheme, it covers the frame's
# extremes plus its middle, and it keeps ONE session.run() comfortably
# inside a short Lambda timeout. More crops would mean finer coverage and
# a longer invocation for a feature that is advisory only.
CROP_COUNT = 5


def five_crop_boxes(width: int, height: int, size: int = INPUT_SIZE) -> list[tuple[int, int, int, int]]:
    """Five (x0, y0, x1, y1) boxes: centre, then TL, TR, BL, BR.

    Boxes are clamped to the frame and are `size` px where the frame
    allows it. On a frame SMALLER than `size` in either axis the boxes
    collapse toward the full frame and the five views stop being
    distinct -- preprocess_rgb() still resizes each to 224, so the result
    is correct, just redundant. scored_crops() notices this case and says
    so rather than reporting five "independent" views that are not.
    """
    w = min(size, width)
    h = min(size, height)
    cx = max(0, (width - w) // 2)
    cy = max(0, (height - h) // 2)
    right = max(0, width - w)
    bottom = max(0, height - h)
    origins = [(cx, cy), (0, 0), (right, 0), (0, bottom), (right, bottom)]
    return [(x, y, x + w, y + h) for x, y in origins]


def build_batch(rgb: np.ndarray, size: int = INPUT_SIZE) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
    """Frame -> ((5, 3, size, size) float32 batch, the boxes that produced it).

    ONE array for ONE session.run(). Running five separate inference
    calls would pay the per-call overhead five times for identical
    arithmetic; the model's batch axis is dynamic precisely so this works
    (verified above).

    Crops at native scale are already `size` px and preprocess_rgb()'s
    resize is then a no-op -- that is the point of cropping the native
    frame rather than the downscaled one. It is NOT skipped, because a
    frame narrower than `size` yields a smaller box that genuinely needs
    the resize, and branching on that would be two code paths where one
    suffices.
    """
    height, width = rgb.shape[:2]
    boxes = five_crop_boxes(width, height, size)
    tensors = [preprocess_rgb(rgb[y0:y1, x0:x1], size) for x0, y0, x1, y1 in boxes]
    return np.stack(tensors).astype(np.float32), boxes
