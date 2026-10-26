"""Score the deployed model on a HELD-OUT test folder, per sub-category.

Why this exists: the validation set (data/val) chose the checkpoint and the
threshold, so its numbers are optimistic (see docs/wiki). This script scores
a folder that no training or selection step has touched, and reports recall
broken down by sub-category (e.g. matchstick_flame, lighter_flame), so a
category such as small matchstick flames can be judged on its own.

Expected layout (create it from images that were never used for training
or threshold choice; the README explains the protocol):

    data/test/fire/<category>/*.jpg
    data/test/neutral/<category>/*.jpg     (use 'root' as category if flat)
    data/test/smoke/<category>/*.jpg

Usage (run from the repo root):

    python eval/test_set_eval.py --model-path models/fire_mnv3.onnx

Decisions are per frame, the same rules as edge/vision.py predict():
fire = p_fire >= fire_decision_threshold; smoke = argmax-AND rule. No
temporal voting here, because a folder of still images has no sequence.
The live voter (3 of 8 frames) makes the real system stricter than this
per-frame number, so this is a floor on the deployed behaviour, not a copy.

Writes eval/test_set_results.csv with one row per image.
"""

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "eval"))
sys.path.insert(0, str(REPO_ROOT / "edge"))

from run_eval import build_model  # noqa: E402  reuses the eval config override

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
TEST_DIR = REPO_ROOT / "data" / "test"
RESULTS_CSV = REPO_ROOT / "eval" / "test_set_results.csv"
FIELDNAMES = ["path", "true_class", "category", "p_fire", "p_smoke", "pred_fire", "pred_smoke"]


def collect(test_dir: Path) -> list[tuple[Path, str, str]]:
    """(path, true_class, category) for every image under test_dir/<class>/<category>/."""
    items = []
    for class_dir in sorted(test_dir.iterdir()):
        if not class_dir.is_dir() or class_dir.name not in ("fire", "neutral", "smoke"):
            continue
        for path in sorted(class_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            rel = path.relative_to(class_dir).parts
            category = rel[0] if len(rel) > 1 else "root"
            items.append((path, class_dir.name, category))
    return items


def rate(hits: int, total: int) -> str:
    return f"{hits}/{total} = {hits / total:.4f}" if total else "no images"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-path", required=True, help="ONNX file to evaluate")
    parser.add_argument("--config", default=str(REPO_ROOT / "config.yaml"))
    parser.add_argument("--test-dir", type=Path, default=TEST_DIR)
    args = parser.parse_args()

    items = collect(args.test_dir)
    if not items:
        print(f"[ERROR] no images under {args.test_dir}/<fire|neutral|smoke>/", file=sys.stderr)
        sys.exit(1)

    model = build_model(args.config, args.model_path)
    fire_thr = model.fire_decision_threshold
    smoke_thr = model.smoke_decision_threshold

    rows = []
    for path, true_class, category in items:
        frame = cv2.imread(str(path))
        if frame is None:
            print(f"[skip] unreadable: {path}")
            continue
        # predict() is stateless, so no voter state leaks between images.
        result = model.predict(frame)
        rows.append({
            "path": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
            "true_class": true_class,
            "category": category,
            "p_fire": round(result["p_fire"], 6),
            "p_smoke": round(result["p_smoke"], 6),
            "pred_fire": bool(result["fire"]),
            "pred_smoke": bool(result["smoke"]),
        })

    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    fire_rows = [r for r in rows if r["true_class"] == "fire"]
    neg_rows = [r for r in rows if r["true_class"] != "fire"]
    fire_hit = sum(r["pred_fire"] for r in fire_rows)
    fp = sum(r["pred_fire"] for r in neg_rows)

    print(f"Model: {args.model_path}   fire threshold {fire_thr}   smoke threshold {smoke_thr}")
    print(f"Images scored: {len(rows)}   (CSV: {RESULTS_CSV.relative_to(REPO_ROOT)})\n")
    print(f"FIRE RECALL, all fire images:      {rate(fire_hit, len(fire_rows))}   (bar 0.95)")
    print(f"FIRE false alarms on non-fire:     {rate(fp, len(neg_rows))}")
    prec_den = fire_hit + fp
    print(f"FIRE PRECISION:                    {rate(fire_hit, prec_den)}   (bar 0.80)\n")

    print("FIRE RECALL by sub-category (the matchstick question is the matchstick row):")
    categories = sorted({r["category"] for r in fire_rows})
    for cat in categories:
        cat_rows = [r for r in fire_rows if r["category"] == cat]
        cat_hit = sum(r["pred_fire"] for r in cat_rows)
        print(f"  {cat:<28} {rate(cat_hit, len(cat_rows))}")

    smoke_rows = [r for r in rows if r["true_class"] == "smoke"]
    smoke_hit = sum(r["pred_smoke"] for r in smoke_rows)
    print(f"\nSMOKE RECALL (argmax-AND rule): {rate(smoke_hit, len(smoke_rows))}   (bar 0.85)")


if __name__ == "__main__":
    main()
