"""Diagnostic-only: sweep the fire decision threshold and measure the recall/precision tradeoff.

The training run's reported fire recall (0.9221) used plain argmax: an image
is "predicted fire" only if fire has the single HIGHEST probability among the
3 classes -- equivalent to a 0.50-ish decision rule in a one-vs-rest sense.
inspect_misclassified.py showed several of the 17 fire->neutral misses were
close calls (fire probability 0.45-0.49, barely losing to neutral). This
script asks: if we called something "fire" whenever P(fire) >= some LOWER
threshold, regardless of whether fire was the argmax winner, how much recall
do we recover -- and what does it cost in false alarms?

This is diagnostic only. It does NOT edit config.yaml and does NOT retrain --
it reports the tradeoff curve so the developer can pick the actual value.
"""

import argparse
from pathlib import Path

import numpy as np

from val_inference import CHECKPOINT_PATH, load_model, run_inference

CANDIDATE_THRESHOLDS = [0.30, 0.35, 0.40, 0.45, 0.50]
RECALL_BLOCK_BAR = 0.95   # info.md 4.1
PRECISION_BLOCK_BAR = 0.80  # info.md 4.1


def metrics_at_threshold(fire_probs: np.ndarray, is_fire: np.ndarray, threshold: float) -> dict[str, float]:
    """Recall/precision/false-alarm count if 'predicted fire' means P(fire) >= threshold.

    This is deliberately NOT argmax -- an image can have fire as its
    highest-probability class and still fail a HIGH threshold, or have fire
    as its second-highest class and still pass a LOW threshold. That's the
    whole point of the sweep: decoupling "is fire the model's best guess"
    from "is fire probability high enough to raise an alarm".
    """
    predicted_fire = fire_probs >= threshold

    tp = int((predicted_fire & is_fire).sum())          # real fire, alarmed
    fp = int((predicted_fire & ~is_fire).sum())          # not fire, alarmed anyway (false alarm)
    fn = int((~predicted_fire & is_fire).sum())          # real fire, missed

    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    return {"recall": recall, "precision": precision, "tp": tp, "fp": fp, "fn": fn}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT_PATH)
    args = parser.parse_args()

    model, class_to_idx = load_model(args.checkpoint)
    probs, labels, _paths = run_inference(model, class_to_idx)

    fire_idx = class_to_idx["fire"]
    is_fire = labels == fire_idx
    fire_probs = probs[:, fire_idx]
    n_fire = int(is_fire.sum())
    print(f"Val set: {len(labels)} images, {n_fire} true fire, {len(labels) - n_fire} true non-fire")

    baseline = metrics_at_threshold(fire_probs, is_fire, 0.50)
    baseline_fp = baseline["fp"]

    print(f"\n{'Threshold':>9} | {'Fire recall':>11} | {'Fire precision':>14} | {'New false alarms vs 0.50':>25}")
    print("-" * 68)

    results = []
    for t in CANDIDATE_THRESHOLDS:
        m = metrics_at_threshold(fire_probs, is_fire, t)
        new_fp = m["fp"] - baseline_fp  # cost of lowering the threshold below 0.50
        results.append((t, m))
        print(f"{t:>9.2f} | {m['recall']:>11.4f} | {m['precision']:>14.4f} | {new_fp:>25d}")

    # 0.50 is the training run's effective argmax behavior -- included as the
    # reference point the "new false alarms" column is measured against, not
    # as a candidate to lower TO.
    print(f"\n(0.50 = training run's argmax-equivalent baseline: "
          f"recall {baseline['recall']:.4f}, precision {baseline['precision']:.4f})")

    # Lowest threshold (i.e. loosest/most alarm-prone) that clears BOTH block
    # bars simultaneously. Sweeping from the lowest candidate up would find
    # the highest such threshold instead -- we want the lowest, since a lower
    # threshold is the "just barely enough" choice that minimises the
    # false-alarm cost while still clearing recall.
    passing = [(t, m) for t, m in results
               if m["recall"] >= RECALL_BLOCK_BAR and m["precision"] >= PRECISION_BLOCK_BAR]

    print(f"\ninfo.md 4.1 block bars: fire recall >= {RECALL_BLOCK_BAR}, fire precision >= {PRECISION_BLOCK_BAR}")
    if passing:
        best_t, best_m = min(passing, key=lambda pair: pair[0])
        print(f"LOWEST threshold meeting both bars: {best_t:.2f} "
              f"(recall {best_m['recall']:.4f}, precision {best_m['precision']:.4f})")
    else:
        print("NO threshold in the tested range "
              f"({', '.join(f'{t:.2f}' for t in CANDIDATE_THRESHOLDS)}) "
              "achieves both bars simultaneously.")
        print("Threshold lowering alone is not sufficient -- per info.md 4.1, "
              "consider adding training data or rebalancing classes as well.")


if __name__ == "__main__":
    main()
