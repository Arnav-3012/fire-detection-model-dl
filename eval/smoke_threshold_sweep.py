"""Diagnostic-only: sweep the smoke decision threshold and measure the recall/precision tradeoff.

Sibling of threshold_sweep.py (fire). edge/vision.py has always called a
frame "smoke" by plain argmax -- smoke wins whenever it is merely the
highest of three probabilities, which on a 3-class softmax can happen at
P(smoke) as low as ~0.34. Live testing (2026-09-04) saw WATCH states fire
at P(smoke) 0.28-0.44 against a neutral scene. This script asks the
mirror-image question of the fire sweep: if we only called a frame "smoke"
when P(smoke) >= some threshold, how much smoke recall do we give up, and
how many false smoke calls on genuinely non-smoke val images do we remove?

Two decision rules are reported because they differ below 0.50:
  - "prob"   : P(smoke) >= t, regardless of argmax (fire's rule shape)
  - "argmax" : smoke is the argmax winner AND P(smoke) >= t (a strict
               tightening of today's behaviour -- can only remove calls)
At t >= 0.50 the two coincide (a class above 0.50 is always the argmax).

Diagnostic only. Does NOT edit config.yaml and does NOT retrain.
"""

import argparse
from pathlib import Path

import numpy as np

from val_inference import CHECKPOINT_PATH, load_model, run_inference

CANDIDATE_THRESHOLDS = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70]
RECALL_BLOCK_BAR = 0.85   # info.md 4.1, smoke row
RECALL_TARGET = 0.92      # info.md 4.1, smoke row


def metrics(predicted: np.ndarray, is_smoke: np.ndarray) -> dict[str, float]:
    """Recall/precision/counts for one boolean 'predicted smoke' vector."""
    tp = int((predicted & is_smoke).sum())
    fp = int((predicted & ~is_smoke).sum())
    fn = int((~predicted & is_smoke).sum())
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    return {"recall": recall, "precision": precision, "tp": tp, "fp": fp, "fn": fn}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT_PATH)
    args = parser.parse_args()

    model, class_to_idx = load_model(args.checkpoint)
    probs, labels, _paths = run_inference(model, class_to_idx)

    smoke_idx = class_to_idx["smoke"]
    neutral_idx = class_to_idx["neutral"]
    is_smoke = labels == smoke_idx
    is_neutral = labels == neutral_idx
    smoke_probs = probs[:, smoke_idx]
    argmax_smoke = probs.argmax(axis=1) == smoke_idx
    n_smoke = int(is_smoke.sum())
    print(f"Val set: {len(labels)} images, {n_smoke} true smoke, {len(labels) - n_smoke} true non-smoke "
          f"({int(is_neutral.sum())} neutral)")

    # Today's production behaviour: argmax with no threshold at all.
    base = metrics(argmax_smoke, is_smoke)
    base_fp_neutral = int((argmax_smoke & is_neutral).sum())
    print(f"\nBASELINE (argmax, no threshold -- current edge/vision.py): "
          f"recall {base['recall']:.4f}, precision {base['precision']:.4f}, "
          f"FP {base['fp']} (of which {base_fp_neutral} are true-neutral images)")
    fp_probs = smoke_probs[argmax_smoke & ~is_smoke]
    if len(fp_probs):
        q = np.percentile(fp_probs, [10, 25, 50, 75, 90])
        print(f"P(smoke) on those {len(fp_probs)} argmax false positives -- "
              f"p10 {q[0]:.3f}  p25 {q[1]:.3f}  median {q[2]:.3f}  p75 {q[3]:.3f}  p90 {q[4]:.3f}")
        print(f"  ...of which {int((fp_probs < 0.50).sum())} have P(smoke) < 0.50 "
              f"(smoke 'won' argmax without even a majority)")

    header = (f"{'t':>5} | {'rule':>6} | {'recall':>7} | {'precision':>9} | {'TP':>4} | {'FN':>4} | "
              f"{'FP':>4} | {'FP neutral':>10} | {'FP removed vs argmax':>20}")
    print(f"\n{header}\n{'-' * len(header)}")
    results = []
    for t in CANDIDATE_THRESHOLDS:
        for rule, predicted in (("prob", smoke_probs >= t), ("argmax", argmax_smoke & (smoke_probs >= t))):
            m = metrics(predicted, is_smoke)
            fp_neutral = int((predicted & is_neutral).sum())
            results.append((t, rule, m))
            print(f"{t:>5.2f} | {rule:>6} | {m['recall']:>7.4f} | {m['precision']:>9.4f} | {m['tp']:>4d} | "
                  f"{m['fn']:>4d} | {m['fp']:>4d} | {fp_neutral:>10d} | {base['fp'] - m['fp']:>20d}")
            if t >= 0.50:
                break  # rules coincide at and above 0.50; print once

    print(f"\ninfo.md 4.1 smoke block bar: recall >= {RECALL_BLOCK_BAR} (target >= {RECALL_TARGET})")
    passing = [(t, rule, m) for t, rule, m in results if m["recall"] >= RECALL_BLOCK_BAR]
    if passing:
        t, rule, m = max(passing, key=lambda r: r[0])
        print(f"HIGHEST threshold still clearing the block bar: {t:.2f} ({rule}) -- "
              f"recall {m['recall']:.4f}, precision {m['precision']:.4f}, FP {m['fp']} "
              f"({base['fp'] - m['fp']} fewer than argmax)")
    else:
        print("NO candidate threshold clears the smoke recall block bar.")


if __name__ == "__main__":
    main()
