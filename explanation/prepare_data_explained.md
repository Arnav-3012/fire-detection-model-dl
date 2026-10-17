# `prepare_data.py` Explained — Line by Line, Function by Function

This is FireWatch's actual dataset-building script — the real code behind what the "Data In, Predictions Out" document described in prose. This file walks through every function, in the order the script actually executes them, explaining not just *what* each line does but *why* it's written that way — including several real bugs the comments reveal were caught and fixed.

---

## 0. The Module Docstring — a Real, Documented Design Decision

```python
"""Build the 3-class (neutral/smoke/fire) train/val split for FireWatch.

Split strategy (decided 2026-08-18, see logs.md Phase 1): plan.md's Day 1
prompt assumes a single undifferentiated D-Fire pool, but the Kaggle mirror
actually in use ships three pre-split folders (train/val/test). plan.md does
not specify a held-out test set beyond the Day 5 adversarial eval and Day 11
trial evaluation, so all three D-Fire splits are pooled together and
re-split 85/15 here rather than respecting D-Fire's original boundaries.
"""
```

Before any code runs, this docstring records a real deviation from the original plan. `plan.md` assumed D-Fire would arrive as one undifferentiated pool of images; the actual dataset mirror in use ships pre-split into `train/`, `val/`, and `test/` folders instead. Rather than silently working around this mismatch, the script's author explains the reasoning: since the project already has its own held-out evaluation stages (adversarial testing, trial evaluation) elsewhere, D-Fire's own train/val/test boundaries aren't needed — so all three are pooled together and given one fresh 85/15 split, matching what this project actually needs rather than what D-Fire happened to ship with.

---

## 1. Imports and Constants

```python
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
```

- `argparse` — lets the script be run from the command line with configurable options (paths, flags), rather than hardcoding folder locations.
- `filecmp` — used later to compare two files byte-for-byte (not just by name), for a genuinely important duplicate-detection step.
- `random` — Python's built-in random number generator, used for shuffling before the train/val split.
- `shutil` — file operations: copying files, deleting whole directory trees.
- `Counter`, `defaultdict` — two specialized dictionary types from `collections`. `Counter` auto-initializes missing keys to 0 (perfect for tallying "how many images per class"); `defaultdict(list)` auto-initializes missing keys to an empty list (perfect for grouping images by class before you know which classes exist yet).
- `md5` — a hashing function, used here not for security but to generate a short, stable, reproducible string from a file path, for disambiguating duplicate filenames.
- `Path` — modern, object-oriented file path handling (from `pathlib`), used throughout instead of raw strings.
- `PIL.Image`, `UnidentifiedImageError` — Python's imaging library, used to actually open and verify each image is real, readable image data — not just trust that a `.jpg` extension means it's a valid JPEG.
- `check_leakage` — imported from a separate file, `check_leakage.py`; this script calls it at the very end to verify the split it just built doesn't have train/val duplicates (Data doc, Section 2.4's leakage story).
- `print_balance_table`, `save_balance_chart` — imported from `data_report.py`, used at the end to summarize and visualize how many images ended up in each class.

**The three constants:**
- `RANDOM_SEED = 42` — a fixed seed, so re-running this script produces the *exact same* train/val split every time, rather than a different random split on each run. The comment points to `info.md 3.3`, meaning this isn't an arbitrary choice — it's a documented project-wide rule.
- `VAL_FRACTION = 0.15` — 15% of each class goes to validation, 85% to training (Data doc, Section 2.3's stratified split).
- `IMAGE_EXTENSIONS` — the set of file extensions treated as images; anything else encountered while walking a folder gets silently skipped.

---

## 2. `label_from_yolo_file()` — Turning Box Labels Into One Image-Level Label

```python
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
```

This is the exact function described conceptually in the Data doc's Section 2.1. D-Fire ships as an **object-detection** dataset: each image's label file lists one line per detected box, formatted as `class_id x y width height` (YOLO format) — `class_id` is `0` for smoke or `1` for fire. But FireWatch trains a **classifier**, which needs exactly one label per whole image, not a list of boxes. This function does that collapse.

- `if not label_path.exists(): return "neutral"` — if D-Fire didn't even generate a label file for this image, it means nothing was detected in it at all, so it's neutral by default.
- `class_ids: set[int] = set()` — a *set* (not a list) is used deliberately, since duplicate class IDs across multiple boxes in the same image don't matter here — we only care *which* classes are present, not how many boxes of each.
- The `for line in f:` loop reads the label file line by line, skips blank lines (`if not line: continue`), and pulls the first number off each line (`line.split()[0]`, since YOLO format always puts the class ID first) and adds it to the set.
- `if not class_ids: return "neutral"` — the label file existed but was empty (no boxes at all) — still neutral.
- `if 1 in class_ids: return "fire"` — checked **before** the smoke check. This is the fire-priority rule the docstring explains: if an image has both a fire box and a smoke box, it gets labeled `fire`, never `smoke`, because the project's strictest requirement is never missing a real fire (`info.md 4.1`'s fire-recall bar) — filing a fire-containing image as merely "smoke" would be the wrong direction of error for a safety system.
- `if 0 in class_ids: return "smoke"` — only reached if there was no fire box, but there was a smoke box.
- Final `return "neutral"` — a defensive fallback that should be unreachable in practice (if `class_ids` isn't empty, it must contain 0 and/or 1, given how D-Fire's format works), but is there in case an unexpected class ID ever showed up.

---

## 3. `collect_dfire_images()` — Walking All Three D-Fire Splits Into One Pool

```python
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
```

This function implements exactly the "pool all three splits" decision from the module docstring.

- `items` accumulates `(image_path, label)` pairs — the running list of everything found so far.
- `skipped` accumulates human-readable strings describing anything that had to be skipped and why — this is a real, deliberate transparency choice: rather than silently dropping bad data, the script tracks every skip reason so it can be reported to the person running it at the end (see `main()`, near the bottom).
- The outer loop walks D-Fire's three sub-folders one at a time (`"train", "val", "test"`), each of which is expected to contain `images/` and `labels/` subfolders — the standard YOLO dataset layout.
- `if not images_dir.is_dir(): skipped.append(...); continue` — if one of the three expected split folders is missing entirely (maybe the download was incomplete), the script doesn't crash — it logs the gap and moves to the next split.
- `sorted(images_dir.iterdir())` — `sorted()` matters here: without it, folder iteration order can vary between operating systems and even between runs, which would break the reproducibility that `RANDOM_SEED = 42` is trying to guarantee. Sorting first means the same seed always shuffles the same, consistently-ordered list.
- `if image_path.suffix.lower() not in IMAGE_EXTENSIONS: continue` — skips any non-image files sitting in the folder (e.g. a stray `.txt` or `.DS_Store`).
- `label_path = labels_dir / f"{image_path.stem}.txt"` — YOLO's convention: an image named `photo123.jpg` has its label at `labels/photo123.txt` — same filename stem, different folder and extension.
- The `try/except` around `label_from_yolo_file(label_path)` catches two realistic failure modes: `ValueError` (e.g., a label line that doesn't parse as an integer — a corrupted or malformed label file) and `OSError` (a filesystem-level read failure). Either way, the image is skipped and logged rather than crashing the entire script over one bad file.

---

## 4. `collect_hard_negatives()` — Folding In the Hand-Reviewed Neutral Images

```python
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
```

This is the hard-negative collection function described in the Data doc's Section 1.3 (sunset_window, red_orange_objects, steam, etc.). Two things worth noticing beyond what the Data doc already covered:

- **A second, honest documented deviation.** The docstring reveals `plan.md 6.4` originally called for personally-shot photos, but the actual images are reviewed stock/scraped photos instead — logged plainly, not hidden.
- **`extra_negatives_dir.rglob("*")`** — `rglob` (recursive glob) walks *every* subfolder, not just the top level, which is required since these images live in per-category subfolders (`hard_negatives/steam/`, `hard_negatives/car_lights_night/`, etc.) rather than one flat folder.
- **`category = image_path.relative_to(extra_negatives_dir).parts[0]`** — this line extracts just the category name from the full path. If `image_path` is `data/hard_negatives/steam/photo1.jpg`, then `relative_to(extra_negatives_dir)` gives `steam/photo1.jpg`, and `.parts[0]` takes the first path component, `"steam"` — used purely for the `per_category` tally (so the final report can show "steam: 23 images" the way the Data doc's Figure 1.1 does), not for the actual training label, since every image here is unconditionally `neutral` regardless of which category folder it came from.

---

## 5. `collect_extra_fire_positives()` — a Later, Grad-CAM-Motivated Addition

```python
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
```

This function is new information — it's not covered in any of the earlier documents. The docstring explains its origin precisely: a Grad-CAM investigation (exactly the technique explained in the "Seeing Inside the Model" document) found the model's attention was landing on the *correct* region of an image, but was systematically **under-weighting small, localized flames** — meaning the model was less confident about small fires than it should have been. Rather than changing the architecture or the decision thresholds, the fix chosen was to add more training examples specifically containing small flames to the `fire` class — a direct, practical example of "fix it in the data, not the code," the same philosophy behind the hard-negative collection strategy.

Two structural details worth understanding:

- **It accepts a *list* of directories** (`extra_fire_dirs: list[Path]`), not just one — unlike `collect_hard_negatives()`, which takes a single folder. This lets the fire-positive data come from multiple separate review batches (e.g., one batch from an initial small-flame collection effort, another from a later follow-up), each added independently over time as `main()`'s `--extra-fire-positive` argument accepts multiple paths (`nargs="+"`, seen further down).
- **The category-naming line is slightly more complex than `collect_hard_negatives()`'s equivalent:** `category = image_path.relative_to(extra_fire_dir).parts[0] if image_path.parent != extra_fire_dir else extra_fire_dir.name`. This handles two possible folder shapes: if images sit directly inside `extra_fire_dir` with no subfolder (`image_path.parent == extra_fire_dir`), the category name falls back to the directory's own name; otherwise, it behaves like the hard-negatives function and takes the first subfolder name. This flexibility exists because, unlike the hard-negatives tree (which always has category subfolders), a small, one-off fire-positive review batch might not bother organizing into subcategories at all.
- **The docstring also documents a related script, `scripts/review_hard_negatives.py`,** which physically separates manually-rejected images into a sibling `*_rejected/` folder — meaning this function's plain recursive walk automatically only picks up *kept*, reviewed images, without needing any extra filtering logic here.

---

## 6. `verify_image()` — Never Trust a File Extension

```python
def verify_image(image_path: Path) -> bool:
    """Open and verify an image is readable, without trusting the file extension."""
    try:
        with Image.open(image_path) as img:
            img.verify()
        return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False
```

A short but important function: a file named `photo.jpg` is not guaranteed to actually *be* a valid JPEG — it could be a corrupted download, a truncated file, or even an HTML error page saved with the wrong extension (a realistic failure mode for scraped hard-negative images, Data doc Section 1.3). This function actually opens the file with PIL and calls `.verify()`, which checks the file's internal structure is a genuine, parseable image — catching `UnidentifiedImageError` (not an image PIL recognizes at all), `OSError` (a read/corruption failure), and `ValueError` (malformed internal image data) as all meaning "this file is unusable," returning `False` rather than letting a bad file crash training later.

---

## 7. `stratified_split()` — the Actual 85/15 Split, Per Class

```python
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
```

This is the code behind the Data doc's Section 2.3 (stratified 85/15 split). The mechanics:

- `by_class = defaultdict(list)` then the loop `for item in items: by_class[item[1]].append(item)` — groups every `(path, label)` pair into separate lists keyed by class name. `item[1]` is the label (the second element of the tuple), so this sorts every image into its own class's bucket first — this is what "stratified" means in practice: the split happens *within* each class separately, not across the whole pool at once.
- `rng = random.Random(seed)` — creates a private random number generator seeded with the fixed value (42), rather than using Python's global `random` module directly. This is a subtle but important correctness detail: using a dedicated `Random` instance means this function's shuffling is fully reproducible and isolated, unaffected by any other code elsewhere in the program that might also call `random` functions and inadvertently change the global random state.
- `shuffled = class_items[:]` — makes a *copy* of the list (`[:]` is Python's slice-everything idiom for copying) before shuffling, so the original `by_class[class_name]` list isn't mutated in place — a defensive habit that avoids subtle bugs if this data were ever reused elsewhere.
- `rng.shuffle(shuffled)` — randomly reorders this one class's images, using the seeded generator.
- `n_val = round(len(shuffled) * val_fraction)` — computes how many of this class's images go to validation (15%, rounded to the nearest whole number).
- `val_items.extend(shuffled[:n_val])` and `train_items.extend(shuffled[n_val:])` — since the list is already shuffled, simply slicing the first `n_val` items for validation and the rest for training is equivalent to a random selection, without needing any more complex sampling logic.

This loop runs once per class (fire, neutral, smoke), so each class independently gets its own 85/15 split before all the pieces are combined back into two master lists — exactly the guarantee the Data doc's Section 2.3 described: no class can be accidentally over- or under-represented in validation just by chance.

---

## 8. `write_split()` — Physically Copying Files, With a Real Documented Bug Fix

```python
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
```

This function physically builds the final `data/train/<class>/` and `data/val/<class>/` folder structure the model actually trains from. Line by line:

- `for image_path, class_name in items:` — unpacks each `(path, label)` tuple directly in the loop header.
- `if not verify_image(image_path): skipped.append(...); continue` — runs the corruption check from Section 6 above at copy time, not earlier — meaning even a file that made it through label-collection can still be dropped here if it turns out to be unreadable.
- `dest_dir = output_dir / split_name / class_name` then `dest_dir.mkdir(parents=True, exist_ok=True)` — builds (or reuses, if it already exists) the destination folder, e.g. `data/train/fire/`. `parents=True` creates any missing parent folders too; `exist_ok=True` means it won't raise an error if the folder is already there.
- **The duplicate-filename block is the most interesting part of this whole script**, and its comment documents a real bug that was caught and fixed. Two different images pooled from different sources (say, a D-Fire image and a hard-negative image) could coincidentally share the exact same filename. The naive fix — just append a random or hash-based suffix whenever a name collision occurs — has a hidden trap: if you simply **re-run** this script over its own previous output (say, to add more data), *every single file* would appear to "collide" with the file it wrote last time, and the naive fix would duplicate the entire dataset. The comment says exactly this happened once (`logs.md Phase 2`).
- **The actual fix:** `if filecmp.cmp(image_path, dest_path, shallow=False):` — before assuming a name collision means "two different images with the same name," the script checks whether the two files are **byte-for-byte identical** (`shallow=False` forces a full content comparison, not just a quick timestamp/size check). If they're identical, this is just a harmless re-run over old output — the function counts it and moves on (`continue`) without copying anything again. Only if the two files have the same name but **different content** does it fall through to the disambiguation step.
- `digest = md5(str(image_path).encode()).hexdigest()[:8]` — generates an 8-character hash from the source file's *path* (not its content), used to build a unique suffix. The comment explains why `md5` was chosen over Python's built-in `hash()`: `hash()` on a string is randomized differently every time you start a new Python process (a security feature in modern Python), so it would produce a different suffix every re-run — breaking reproducibility. `md5` always produces the same digest for the same input, every time, on every machine.
- `shutil.copyfile(image_path, dest_path)` — the actual file copy, only reached once everything above has confirmed this file needs to be copied.
- `counts[class_name] += 1` — tallies how many images actually ended up in this class, for the final balance report.

---

## 9. `main()` — Tying Every Function Together

```python
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
```

`argparse` sets up the command-line interface. Each `add_argument` call defines one option:
- `--dfire-dir` — where the raw D-Fire download lives (defaults to `data/dfire_raw/data`).
- `--output-dir` — where to write the final `train/` and `val/` folders (defaults to `data/`).
- `--extra-negatives` — where the hard-negative tree lives.
- `--extra-fire-positive` — accepts **one or more** paths (`nargs="+"`), matching `collect_extra_fire_positives()`'s list-based signature from Section 5. `default=None` means this is optional — if omitted, no extra fire images are folded in, and D-Fire's own fire images are all there is.
- `--clean` — a boolean flag (`action="store_true"`, meaning its mere presence on the command line sets it `True`, no value needed). Its help text documents **another real, dated incident**: on 2026-08-27, running this script twice without wiping old output first caused an actual train/val leakage bug (this is very likely the same duplicate-stock-photo leakage story referenced in the Data doc's Section 2.4) — so the script was changed to *refuse to run at all* against non-empty output folders unless this flag is explicitly passed.

```python
    existing = [d for d in (args.output_dir / "train", args.output_dir / "val") if d.exists()]
    if existing and not args.clean:
        print(f"[ERROR] {', '.join(map(str, existing))} already exist. Re-run with --clean "
              "to wipe and rebuild them; never append into an existing split.")
        raise SystemExit(1)
    for d in existing:
        print(f"--clean: removing {d}")
        shutil.rmtree(d)
```

This is the actual enforcement of the `--clean` safety rule just described. It checks whether `train/` and/or `val/` already exist; if either does and `--clean` wasn't passed, the script prints an error and exits immediately (`raise SystemExit(1)`, `1` signaling failure to any calling script or CI system) rather than silently appending into old data. If `--clean` *was* passed, it deletes (`shutil.rmtree`, recursive folder delete) any existing split folders before continuing — guaranteeing every run starts from a truly empty output, which is what makes `write_split()`'s duplicate-detection logic (Section 8) trustworthy: a "duplicate" it finds is always a real cross-source collision, never leftover debris from a half-finished previous run.

```python
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
```

This block calls the three collection functions from Sections 3–5, in order, printing progress as it goes and accumulating every skip reason into one master `all_skipped` list. The `if args.extra_negatives:` and `if args.extra_fire_positive:` guards mean these two sources are optional — the script still works if you only want D-Fire alone. The fire-positive block additionally computes and prints `dfire_fire_count` alongside the extra count, so the console output makes clear exactly how much the small-flame Grad-CAM fix (Section 5) actually contributed relative to D-Fire's own fire images.

```python
    all_items = (
        dfire_items
        + [(p, "neutral") for p in hn_images]
        + [(p, "fire") for p in extra_fire_images]
    )
```

Here every source gets combined into one flat list of `(path, label)` tuples, ready for splitting. Notice the hard-negative and extra-fire-positive lists (which came back as plain lists of paths, not path-label pairs) get their fixed label attached right here, via list comprehensions — `"neutral"` for every hard negative, `"fire"` for every extra fire-positive image, exactly matching each function's documented behavior from Sections 4 and 5.

```python
    print(f"\nSplitting {len(all_items)} total images {int((1 - VAL_FRACTION) * 100)}/{int(VAL_FRACTION * 100)} (stratified by class, seed={RANDOM_SEED})...")
    train_items, val_items = stratified_split(all_items, VAL_FRACTION, RANDOM_SEED)

    print(f"Writing train split ({len(train_items)} images) to {args.output_dir / 'train'}...")
    train_counts, train_skipped = write_split(train_items, args.output_dir, "train")
    all_skipped.extend(train_skipped)

    print(f"Writing val split ({len(val_items)} images) to {args.output_dir / 'val'}...")
    val_counts, val_skipped = write_split(val_items, args.output_dir, "val")
    all_skipped.extend(val_skipped)
```

The actual split (Section 7) runs once on the combined pool, then `write_split()` (Section 8) is called twice — once for the training items, once for the validation items — physically copying files into `data/train/<class>/` and `data/val/<class>/` respectively.

```python
    if all_skipped:
        print(f"\n=== Skipped {len(all_skipped)} files ===")
        for entry in all_skipped:
            print(f"  {entry}")

    print_balance_table(train_counts, val_counts, hn_per_category, extra_fire_per_category)

    chart_path = Path("eval/class_balance.png")
    save_balance_chart(train_counts, val_counts, chart_path)
    print(f"\nClass balance chart saved to {chart_path}")
```

Every skip reason collected throughout the entire run — from D-Fire label parsing failures, to corrupt images caught in `write_split()` — gets printed in one final, honest summary rather than being silently swallowed anywhere. Then `print_balance_table()` and `save_balance_chart()` (imported from `data_report.py`, a separate module not shown here) produce the human-readable class-count summary and the chart — this is almost certainly what generates the exact figures the Data doc's Section 1 and Figure 1.1 are built from.

```python
    print("\n=== Train/val leakage check (train/check_leakage.py) ===")
    if not check_leakage(args.output_dir):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

The very last step calls `check_leakage()` (imported from `check_leakage.py`, a separate file) on the freshly-written output — this is the exact leakage-check step described in the Data doc's Section 2.4. The comment right above this call in the original source (visible just above `main()`'s leakage guard block) makes the philosophy explicit: *"a rebuild is not 'clean' because we wiped first, it is clean because we checked"* — meaning wiping old data before rebuilding (the `--clean` flag) is necessary but not sufficient; the script doesn't consider its own output trustworthy until an independent verification pass has actually confirmed there's no leakage, and it exits with a failure code (`raise SystemExit(1)`) if that check fails, rather than reporting success regardless.

`if __name__ == "__main__": main()` is the standard Python idiom meaning "only run `main()` if this file was executed directly (e.g., `python prepare_data.py`), not if it was imported as a module by some other script."

---

## Summary — the Full Pipeline in One Pass

1. Parse command-line arguments; refuse to run against old output unless `--clean` is passed (a real bug fix, `logs.md Phase 2`).
2. Collect D-Fire's images across all three of its own splits, deriving one fire/smoke/neutral label per image from its YOLO box annotations, with fire taking priority whenever both fire and smoke boxes appear together.
3. Optionally fold in hand-reviewed hard-negative images (all labeled `neutral`) and extra fire-positive images (all labeled `fire`, added later in response to a Grad-CAM finding about under-weighted small flames).
4. Stratify-split everything into train/val, 85/15, independently per class, with a fixed random seed for reproducibility.
5. Physically copy every file into its final `train/<class>/` or `val/<class>/` folder, verifying each image is genuinely readable first, and safely handling filename collisions by checking file content before ever assuming two same-named files are actually different (a second real bug fix, also `logs.md Phase 2`).
6. Report every skipped file, print and chart the final class balance, and run an independent leakage check before considering the whole rebuild trustworthy.
