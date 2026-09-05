"""Reporting helpers for train/prepare_data.py: balance table and bar chart.

Split out of prepare_data.py to keep that file under the ~200 line guideline
in info.md 3.3.
"""

from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CLASSES = ("neutral", "smoke", "fire")


def print_balance_table(
    train_counts: Counter,
    val_counts: Counter,
    hn_per_category: Counter,
    extra_fire_per_category: Counter | None = None,
) -> None:
    """Print the class balance table plus the hard-negative per-category breakdown."""
    print("\n=== Class balance ===")
    print(f"{'Class':<10}{'Train':>10}{'Val':>10}{'Total':>10}")
    for class_name in CLASSES:
        train_n = train_counts.get(class_name, 0)
        val_n = val_counts.get(class_name, 0)
        print(f"{class_name:<10}{train_n:>10}{val_n:>10}{train_n + val_n:>10}")
    total_train = sum(train_counts.values())
    total_val = sum(val_counts.values())
    print(f"{'TOTAL':<10}{total_train:>10}{total_val:>10}{total_train + total_val:>10}")

    print("\n=== Hard-negative contribution by category (all -> neutral) ===")
    if hn_per_category:
        for category, count in sorted(hn_per_category.items()):
            print(f"  {category:<20}{count:>6}")
        print(f"  {'TOTAL':<20}{sum(hn_per_category.values()):>6}")
    else:
        print("  (none found)")
    print(
        "\nNOTE: hard negatives are reviewed stock/scraped images (kept after "
        "manual review, see logs.md Phase 1), a documented deviation from "
        "plan.md section 6.4's original 'shoot personally' instruction."
    )
    print(
        "NOTE: tv_laptop_fire (2026-08-26) and bright_light_textured_wall "
        "(2026-09-04) are the exceptions: self-filmed by the developer, frames "
        "extracted by scripts/extract_tv_fire_frames.py."
    )

    print("\n=== Extra fire-positive contribution by category (all -> fire, in addition to D-Fire) ===")
    if extra_fire_per_category:
        for category, count in sorted(extra_fire_per_category.items()):
            print(f"  {category:<20}{count:>6}")
        print(f"  {'TOTAL':<20}{sum(extra_fire_per_category.values()):>6}")
        print(
            "\nNOTE: these are reviewed small/localized-flame images (kept after "
            "manual review, see logs.md Phase 5 addenda) folded in to address the "
            "Day 5 Grad-CAM finding that vision under-weights small/localized "
            "flames -- distinct from D-Fire's own fire-class images above."
        )
    else:
        print("  (none found)")


def save_balance_chart(train_counts: Counter, val_counts: Counter, output_path: Path) -> None:
    """Save a grouped bar chart of train/val counts per class to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    x = range(len(CLASSES))
    train_values = [train_counts.get(c, 0) for c in CLASSES]
    val_values = [val_counts.get(c, 0) for c in CLASSES]
    width = 0.35

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar([i - width / 2 for i in x], train_values, width, label="train")
    ax.bar([i + width / 2 for i in x], val_values, width, label="val")
    ax.set_xticks(list(x))
    ax.set_xticklabels(CLASSES)
    ax.set_ylabel("Image count")
    ax.set_title("FireWatch class balance (train/val)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
