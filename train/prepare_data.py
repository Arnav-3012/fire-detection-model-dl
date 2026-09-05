"""Build the 3-class (neutral/smoke/fire) train/val split for FireWatch.

Split strategy (decided 2026-08-18, see logs.md Phase 1): plan.md's Day 1
prompt assumes a single undifferentiated D-Fire pool, but the Kaggle mirror
actually in use ships three pre-split folders (train/val/test). plan.md does
not specify a held-out test set beyond the Day 5 adversarial eval and Day 11
trial evaluation, so all three D-Fire splits are pooled together and
re-split 85/15 here rather than respecting D-Fire's original boundaries.
"""

import argparse
import filecmp
import random
import shutil
from collections import Counter, defaultdict
from hashlib import md5
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from check_leakage import check as check_leakage
from data_report import print_balance_table, save_balance_chart

RANDOM_SEED = 42  # reproducibility, info.md 3.3
VAL_FRACTION = 0.15
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def label_from_yolo_file(label_path: Path) -> str:
    """Derive a single image-level class from a YOLO label file.

    D-Fire labels are per-box (class_id x y w h), but this project trains an
    image classifier, not a detector, so many boxes collapse to one label.
    Fire takes priority over smoke when both appear in the same image
    because info.md 4.1's strictest quality bar is fire recall -- an image
    with any fire content should never be filed as merely "smoke".
    """
    if not label_path.exists():
        return "neutral"

    class_ids: set[int] = set()
    with label_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            class_ids.add(int(line.split()[0]))

    if not class_ids:
        return "neutral"
    if 1 in class_ids:
        return "fire"
    if 0 in class_ids:
        return "smoke"
    return "neutral"


def collect_dfire_images(dfire_dir: Path) -> tuple[list[tuple[Path, str]], list[str]]:
    """Pool every image across D-Fire's train/val/test splits with its derived label.

    Pooling ignores D-Fire's original split boundaries by design -- see the
    module docstring for why this session chose to re-split rather than
    respect them.
    """
    items: list[tuple[Path, str]] = []
    skipped: list[str] = []

    for split in ("train", "val", "test"):
        images_dir = dfire_dir / split / "images"
        labels_dir = dfire_dir / split / "labels"
        if not images_dir.is_dir():
            skipped.append(f"{images_dir}: split directory missing, skipped entirely")
            continue

        for image_path in sorted(images_dir.iterdir()):
            if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            label_path = labels_dir / f"{image_path.stem}.txt"
            try:
                label = label_from_yolo_file(label_path)
            except (ValueError, OSError) as exc:
                skipped.append(f"{label_path}: malformed label file ({exc})")
                continue
            items.append((image_path, label))

    return items, skipped


def collect_hard_negatives(extra_negatives_dir: Path) -> tuple[list[Path], Counter]:
    """Recursively walk the reviewed hard-negatives tree; every image is `neutral`.

    Walked recursively (not top-level-only) because the directory holds
    per-category subfolders (car_lights_night/, red_orange_objects/, etc.),
    per logs.md Phase 1 addendum 2. These are reviewed stock/scraped images
    kept after manual review -- a documented deviation from plan.md 6.4's
    original "shoot personally" instruction, not self-recorded photos.
    """
    images: list[Path] = []
    per_category: Counter = Counter()

    if not extra_negatives_dir.is_dir():
        return images, per_category

    for image_path in sorted(extra_negatives_dir.rglob("*")):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        category = image_path.relative_to(extra_negatives_dir).parts[0]
        images.append(image_path)
        per_category[category] += 1

    return images, per_category


def collect_extra_fire_positives(extra_fire_dirs: list[Path]) -> tuple[list[Path], Counter]:
    """Recursively walk one or more reviewed fire-class trees; every image is `fire`.

    Same recursive-walk pattern as collect_hard_negatives(), applied to
    fire-class data instead of neutral -- this is how the Day 5 Grad-CAM
    finding (logs.md Phase 5 addendum: vision attends to the right region
    but under-weights small/localized flames) gets more small-flame FIRE
    training examples without touching the D-Fire pooling logic. Each
    directory is expected to already contain only manually-reviewed KEPT
    images (rejects were moved to a separate sibling `*_rejected/` tree by
    scripts/review_hard_negatives.py, so a plain recursive walk here already
    excludes them).
    """
    images: list[Path] = []
    per_category: Counter = Counter()

    for extra_fire_dir in extra_fire_dirs:
        if not extra_fire_dir.is_dir():
            continue
        for image_path in sorted(extra_fire_dir.rglob("*")):
            if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            category = image_path.relative_to(extra_fire_dir).parts[0] if image_path.parent != extra_fire_dir else extra_fire_dir.name
            images.append(image_path)
            per_category[category] += 1

    return images, per_category


def verify_image(image_path: Path) -> bool:
    """Open and verify an image is readable, without trusting the file extension."""
    try:
        with Image.open(image_path) as img:
            img.verify()
        return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False


def stratified_split(
    items: list[tuple[Path, str]], val_fraction: float, seed: int
) -> tuple[list[tuple[Path, str]], list[tuple[Path, str]]]:
    """Split items into train/val, preserving per-class proportions.

    A plain random split can under- or over-represent the smallest class
    (fire) in validation purely by chance; stratifying per class keeps the
    val set representative regardless of class imbalance.
    """
    by_class: dict[str, list[tuple[Path, str]]] = defaultdict(list)
    for item in items:
        by_class[item[1]].append(item)

    rng = random.Random(seed)
    train_items: list[tuple[Path, str]] = []
    val_items: list[tuple[Path, str]] = []

    for class_name, class_items in by_class.items():
        shuffled = class_items[:]
        rng.shuffle(shuffled)
        n_val = round(len(shuffled) * val_fraction)
        val_items.extend(shuffled[:n_val])
        train_items.extend(shuffled[n_val:])

    return train_items, val_items


def write_split(
    items: list[tuple[Path, str]], output_dir: Path, split_name: str
) -> tuple[Counter, list[str]]:
    """Physically copy each item into output_dir/split_name/<class>/, skipping bad images."""
    counts: Counter = Counter()
    skipped: list[str] = []

    for image_path, class_name in items:
        if not verify_image(image_path):
            skipped.append(f"{image_path}: unreadable/corrupt image, skipped")
            continue

        dest_dir = output_dir / split_name / class_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / image_path.name

        # Duplicate filenames can occur across D-Fire's pooled splits and the
        # hard-negatives tree; disambiguate rather than silently overwriting.
        # md5 (not the built-in hash()) so the disambiguated name is stable
        # across runs/processes -- hash() is randomized per-process for str.
        # But first check whether the existing file IS this file (byte-equal):
        # that means a re-run over old output, and disambiguating would silently
        # duplicate the whole dataset (this happened once -- see logs.md Phase 2).
        # Skipping keeps re-runs idempotent; only genuinely different content
        # sharing a name gets a suffixed copy.
        if dest_path.exists():
            if filecmp.cmp(image_path, dest_path, shallow=False):
                counts[class_name] += 1
                continue
            digest = md5(str(image_path).encode()).hexdigest()[:8]
            dest_path = dest_dir / f"{image_path.stem}_{digest}{image_path.suffix}"

        shutil.copyfile(image_path, dest_path)
        counts[class_name] += 1

    return counts, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the FireWatch 3-class train/val split.")
    parser.add_argument("--dfire-dir", type=Path, default=Path("data/dfire_raw/data"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/"))
    parser.add_argument("--extra-negatives", type=Path, default=Path("data/hard_negatives"))
    parser.add_argument(
        "--extra-fire-positive", type=Path, nargs="+", default=None,
        help="One or more directories of reviewed fire-class images to fold "
             "into the fire class, in addition to D-Fire's fire images "
             "(recursive walk, same pattern as --extra-negatives).",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Delete <output-dir>/train and <output-dir>/val before writing. "
             "Without it the script refuses to run against non-empty output "
             "folders -- appending across sessions is exactly how the 2026-08-27 "
             "train/val leakage happened (logs.md Phase 2 addendum).",
    )
    args = parser.parse_args()

    # Leakage guard (info.md open item since 2026-08-27): write_split() has no
    # cross-split awareness, so the only safe rebuild is from empty folders.
    existing = [d for d in (args.output_dir / "train", args.output_dir / "val") if d.exists()]
    if existing and not args.clean:
        print(f"[ERROR] {', '.join(map(str, existing))} already exist. Re-run with --clean "
              "to wipe and rebuild them; never append into an existing split.")
        raise SystemExit(1)
    for d in existing:
        print(f"--clean: removing {d}")
        shutil.rmtree(d)

    all_skipped: list[str] = []

    print(f"Collecting D-Fire images from {args.dfire_dir} (pooling train/val/test splits)...")
    dfire_items, dfire_skipped = collect_dfire_images(args.dfire_dir)
    all_skipped.extend(dfire_skipped)
    print(f"  {len(dfire_items)} labelled D-Fire images collected.")

    hn_images: list[Path] = []
    hn_per_category: Counter = Counter()
    if args.extra_negatives:
        print(f"Collecting hard negatives from {args.extra_negatives} (recursive)...")
        hn_images, hn_per_category = collect_hard_negatives(args.extra_negatives)
        print(f"  {len(hn_images)} hard-negative images collected across {len(hn_per_category)} categories.")

    extra_fire_images: list[Path] = []
    extra_fire_per_category: Counter = Counter()
    if args.extra_fire_positive:
        print(f"Collecting extra fire-positive images from {args.extra_fire_positive} (recursive)...")
        extra_fire_images, extra_fire_per_category = collect_extra_fire_positives(args.extra_fire_positive)
        dfire_fire_count = sum(1 for _, label in dfire_items if label == "fire")
        print(f"  {len(extra_fire_images)} additional fire-positive images folded in "
              f"(D-Fire fire images: {dfire_fire_count}, additional: {len(extra_fire_images)}).")

    all_items = (
        dfire_items
        + [(p, "neutral") for p in hn_images]
        + [(p, "fire") for p in extra_fire_images]
    )

    print(f"\nSplitting {len(all_items)} total images {int((1 - VAL_FRACTION) * 100)}/{int(VAL_FRACTION * 100)} (stratified by class, seed={RANDOM_SEED})...")
    train_items, val_items = stratified_split(all_items, VAL_FRACTION, RANDOM_SEED)

    print(f"Writing train split ({len(train_items)} images) to {args.output_dir / 'train'}...")
    train_counts, train_skipped = write_split(train_items, args.output_dir, "train")
    all_skipped.extend(train_skipped)

    print(f"Writing val split ({len(val_items)} images) to {args.output_dir / 'val'}...")
    val_counts, val_skipped = write_split(val_items, args.output_dir, "val")
    all_skipped.extend(val_skipped)

    if all_skipped:
        print(f"\n=== Skipped {len(all_skipped)} files ===")
        for entry in all_skipped:
            print(f"  {entry}")

    print_balance_table(train_counts, val_counts, hn_per_category, extra_fire_per_category)

    chart_path = Path("eval/class_balance.png")
    save_balance_chart(train_counts, val_counts, chart_path)
    print(f"\nClass balance chart saved to {chart_path}")

    # Verify the split we just wrote, by filename AND content -- a rebuild
    # is not "clean" because we wiped first, it is clean because we checked.
    print("\n=== Train/val leakage check (train/check_leakage.py) ===")
    if not check_leakage(args.output_dir):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
