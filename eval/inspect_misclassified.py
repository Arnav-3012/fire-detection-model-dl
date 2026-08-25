"""Diagnostic-only: inspect real fire images the trained model misclassified.

Phase 2 training measured fire recall 0.9221, below info.md 4.1's 0.95 block
bar. The confusion matrix says WHICH cells are wrong (17 fire->neutral, 51
fire->smoke) but not WHY -- this script pulls up the actual images and the
model's full probability distribution on each one, so a human can look at
them and judge whether the miss is a genuinely ambiguous image (fire hidden
in a busy neutral scene, faint early-stage smoke) or a case the model should
clearly have gotten right.

This script does NOT retrain, does NOT touch config.yaml or
train_classifier.py -- diagnostic only, per this session's explicit scope.
"""

import shutil
from pathlib import Path

import numpy as np

from val_inference import load_model, run_inference

# "Close call" vs "confident miss" split point, applied to the model's fire
# probability on images it got wrong. A close call (fire prob well above
# chance, ~0.33 for 3 classes) means the model saw SOME fire signal but
# another class edged it out -- likely a genuinely ambiguous image. A
# confident miss (fire prob near zero) means the model saw essentially no
# fire signal at all -- a more concerning gap in what it learned to
# recognise. 0.20 is chosen as roughly 60% of the 3-class chance baseline
# (0.333): comfortably below "no real signal", while a fire probability
# ABOVE it means the model was clearly registering something fire-like even
# though it lost the argmax.
CLOSE_CALL_THRESHOLD = 0.20


def report_misclassifications(probs, labels, paths, class_to_idx, true_class, pred_class, out_dir, detailed):
    """Find every image where true=true_class, predicted=pred_class; report and copy it out."""
    idx_to_class = {i: c for c, i in class_to_idx.items()}
    true_idx = class_to_idx[true_class]
    pred_idx = class_to_idx[pred_class]

    predicted = probs.argmax(axis=1)
    mask = (labels == true_idx) & (predicted == pred_idx)
    matches = np.where(mask)[0]

    print(f"\n=== {true_class} misclassified as {pred_class}: {len(matches)} images ===")

    out_dir.mkdir(parents=True, exist_ok=True)
    close_calls, confident_misses = [], []
    fire_idx = class_to_idx["fire"]

    for i in matches:
        path = paths[i]
        p = probs[i]
        # Order printed as fire/neutral/smoke regardless of internal index
        # order, for human readability -- the alphabetical ImageFolder index
        # order (fire=0, neutral=1, smoke=2) is an implementation detail, not
        # how a person thinks about the three classes.
        prob_str = ", ".join(f"{c}: {p[class_to_idx[c]]:.2f}" for c in ("fire", "neutral", "smoke"))
        if detailed:
            print(f"  {path.name} -- {prob_str}")

        fire_prob = p[fire_idx]
        if fire_prob >= CLOSE_CALL_THRESHOLD:
            close_calls.append(path.name)
        else:
            confident_misses.append(path.name)

        shutil.copy2(path, out_dir / path.name)

    if detailed:
        print(f"\nSplit (fire probability >= {CLOSE_CALL_THRESHOLD} = close call, else confident miss):")
        print(f"  Close call:      {len(close_calls)} -- {close_calls}")
        print(f"  Confident miss:  {len(confident_misses)} -- {confident_misses}")
    else:
        print(f"  Close call: {len(close_calls)}, Confident miss: {len(confident_misses)}")

    print(f"  Copied {len(matches)} images to {out_dir}/")
    return len(close_calls), len(confident_misses)


def main() -> None:
    model, class_to_idx = load_model()
    probs, labels, paths = run_inference(model, class_to_idx)

    # Sanity check against the training run's confusion matrix numbers before
    # anything else -- if these don't match, something about the val set or
    # checkpoint has changed since training and the rest of this analysis
    # would be diagnosing the wrong run.
    predicted = probs.argmax(axis=1)
    fire_idx = class_to_idx["fire"]
    neutral_idx = class_to_idx["neutral"]
    smoke_idx = class_to_idx["smoke"]
    n_fire_as_neutral = int(((labels == fire_idx) & (predicted == neutral_idx)).sum())
    n_fire_as_smoke = int(((labels == fire_idx) & (predicted == smoke_idx)).sum())
    print(f"\nSanity check against training run's confusion matrix: "
          f"fire->neutral={n_fire_as_neutral} (expected 17), "
          f"fire->smoke={n_fire_as_smoke} (expected 51)")

    print(f"\nClose-call vs confident-miss threshold: fire probability >= {CLOSE_CALL_THRESHOLD}")

    fn_close, fn_confident = report_misclassifications(
        probs, labels, paths, class_to_idx, "fire", "neutral",
        Path("eval/misclassified_fire_as_neutral"), detailed=True)

    fs_close, fs_confident = report_misclassifications(
        probs, labels, paths, class_to_idx, "fire", "smoke",
        Path("eval/misclassified_fire_as_smoke"), detailed=False)

    print("\n=== Summary ===")
    print(f"fire->neutral (dangerous: real fire, model says nothing happening): "
          f"{fn_close} close call, {fn_confident} confident miss")
    print(f"fire->smoke (less dangerous: model still flags a hazard, wrong subtype): "
          f"{fs_close} close call, {fs_confident} confident miss")


if __name__ == "__main__":
    main()
