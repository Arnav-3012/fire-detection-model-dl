"""Train/val leakage regression guard for data/train and data/val.

Why this exists: on 2026-08-27 (logs.md Phase 2 addendum) 3,806 images were
found in BOTH data/train and data/val at once, because prepare_data.py only
ever appended into those folders across sessions. Every retrain since has
relied on a manual "rm -rf then rebuild" plus an eyeballed count check.
This script makes the check explicit and repeatable, and it is stricter
than the original filename check in two ways:

1. It compares CONTENT (md5 of the bytes), not just filenames. prepare_data.py
   disambiguates name collisions with a hash suffix, so the same image could
   sit in train and val under two different names and pass a name check.
   D-Fire's pooled train/val/test folders make byte-identical repeats a
   realistic possibility, not a theoretical one.
2. It also reports duplicates WITHIN a split, which inflate the effective
   weight of an image without being leakage.

Cross-class overlap (the same bytes filed as two classes) is reported too --
that is a labelling contradiction, not leakage, but it is worth knowing.

Runs standalone (`python train/check_leakage.py`) and is called by
prepare_data.py at the end of every rebuild. Exit code 1 on any cross-split
overlap so a wrapper script cannot silently proceed to training.
"""

import argparse
import sys
from collections import defaultdict
from hashlib import md5
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def index_split(split_dir: Path) -> dict[str, list[Path]]:
    """Map content-md5 -> every file in split_dir with those bytes."""
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(split_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            by_hash[md5(path.read_bytes()).hexdigest()].append(path)
    return by_hash


def check(data_dir: Path) -> bool:
    """Print the leakage report for data_dir/train vs data_dir/val; True if clean."""
    train = index_split(data_dir / "train")
    val = index_split(data_dir / "val")
    train_names = {p.name for paths in train.values() for p in paths}
    val_names = {p.name for paths in val.values() for p in paths}

    n_train = sum(len(p) for p in train.values())
    n_val = sum(len(p) for p in val.values())
    print(f"train: {n_train} files ({len(train)} unique by content)")
    print(f"val:   {n_val} files ({len(val)} unique by content)")

    shared_names = train_names & val_names
    shared_content = set(train) & set(val)
    print(f"\ncross-split overlap by FILENAME: {len(shared_names)}")
    print(f"cross-split overlap by CONTENT:  {len(shared_content)}")
    for digest in sorted(shared_content)[:10]:
        print(f"  {digest[:8]}  train={[p.relative_to(data_dir).as_posix() for p in train[digest]]}"
              f"  val={[p.relative_to(data_dir).as_posix() for p in val[digest]]}")
    if len(shared_content) > 10:
        print(f"  ... {len(shared_content) - 10} more")

    for split_name, index in (("train", train), ("val", val)):
        dupes = {d: p for d, p in index.items() if len(p) > 1}
        cross_class = {d: p for d, p in dupes.items() if len({q.parent.name for q in p}) > 1}
        print(f"\nwithin-{split_name} content duplicates: {len(dupes)} groups "
              f"({sum(len(p) - 1 for p in dupes.values())} redundant files), "
              f"of which {len(cross_class)} span two classes")
        for digest, paths in sorted(cross_class.items())[:5]:
            print(f"  {digest[:8]}  {[q.relative_to(data_dir).as_posix() for q in paths]}")

    clean = not shared_names and not shared_content
    print("\nLEAKAGE CHECK:", "PASS -- zero cross-split overlap by name or content" if clean
          else "FAIL -- train and val share images; do NOT train on this split")
    return clean


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    sys.exit(0 if check(args.data_dir) else 1)


if __name__ == "__main__":
    main()
