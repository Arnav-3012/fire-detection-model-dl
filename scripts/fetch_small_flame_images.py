"""One-time data collection utility: downloads small/localized-flame images
via DuckDuckGo image search (`ddgs` package) for the FireWatch vision
dataset's FIRE class.

Same tool and pattern as scripts/fetch_hard_negatives.py (no API key, PIL
validation before saving, rate-limit-aware, `next_free_index` protection
against overwriting already-downloaded files on a re-run, `--category` flag
for retrying one category) — reused deliberately rather than writing a
second, slightly-different downloader. Not part of edge/train/agent
application code, same category as scripts/test_camera.py and
scripts/fetch_hard_negatives.py. Exempt from config.yaml-for-tunables per
info.md §3.1: the category dict below is a one-off dataset-building input,
not a runtime tunable.

UNLIKE fetch_hard_negatives.py, this is FIRE-CLASS training data, not hard
negatives. It exists to address the Day 5 Grad-CAM finding (logs.md, Phase 5
addendum): the model correctly attends to real flame regions but
under-weights small, contained, gas-burner-style flames, likely because
D-Fire's training distribution skews toward larger, more open fires. These
four categories deliberately target variety in small/contained flame
appearance (size, color temperature, containment, distance) rather than one
narrow flame type.

This script only downloads and saves images to
data/additional_fire_training/scraped/<category>/. It does NOT fold this
data into data/train/fire/, does NOT touch prepare_data.py, and does NOT
retrain anything — per this session's explicit scope, folding this into
training and manual quality review (following fetch_hard_negatives.py's own
precedent — see logs.md Phase 1, the steam-category review finding) are
separate, later steps.
"""

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from ddgs import DDGS
from PIL import Image

# category_name -> (search_query, target_count)
CATEGORIES: dict[str, tuple[str, int]] = {
    "gas_stove_flame": ("gas stove burner flame close up", 40),
    "lighter_flame": ("cigarette lighter flame close up", 30),
    "small_candle_flame": ("small candle flame close up macro", 30),
    "matchstick_flame": ("matchstick flame burning close up", 20),
}

# Second attempt, deliberately different phrasing (no "close up"/"macro") to
# test the hypothesis that phrasing pulled staged/color-graded stock photos
# rather than naturalistic captured flames in the first attempt — see
# logs.md small-flame-data entry for the 61% reject rate that prompted this.
CATEGORIES_V2: dict[str, tuple[str, int]] = {
    "gas_stove_flame_v2": ("gas stove burning kitchen photo", 40),
    "lighter_flame_v2": ("lighter flame photo hand", 30),
    "small_candle_flame_v2": ("small candle flame burning photo", 30),
    "matchstick_flame_v2": ("match burning flame photo", 20),
}

OUTPUT_ROOT = Path("data/additional_fire_training/scraped")
OUTPUT_ROOT_V2 = Path("data/additional_fire_training/scraped_v2")
REQUEST_TIMEOUT_S = 5
DELAY_BETWEEN_REQUESTS_S = 0.5
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# Same value fetch_hard_negatives.py settled on after its first run left
# categories short even before manual review — download failures (mostly
# 403s from hotlink-protected stock sites) eat a large fraction of
# candidates regardless of category subject matter.
CANDIDATE_MULTIPLIER = 8


def next_free_index(out_dir: Path, category: str) -> int:
    """Find the first filename index not already used in out_dir.

    Identical purpose to fetch_hard_negatives.py's function of the same
    name: re-running a category (e.g. to top up after a manual quality
    review) must never reuse an existing index and silently overwrite a
    file already on disk.
    """
    existing = list(out_dir.glob(f"{category}_*.*"))
    if not existing:
        return 0
    used_indices = []
    for path in existing:
        stem = path.stem
        suffix = stem.rsplit("_", 1)[-1]
        if suffix.isdigit():
            used_indices.append(int(suffix))
    return max(used_indices, default=-1) + 1


def download_category(
    category: str, query: str, target_count: int, output_root: Path = OUTPUT_ROOT
) -> tuple[int, int]:
    """Download up to target_count valid images for one category.

    Returns (downloaded, failed) counts. Stops once target_count VALID
    saved images are reached, pulling extra candidate URLs as needed since
    some will fail (dead link, timeout, corrupt/non-image response).
    """
    out_dir = output_root / category
    out_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    failed = 0
    next_index = next_free_index(out_dir, category)
    seen_urls: set[str] = set()
    fetch_count = target_count * CANDIDATE_MULTIPLIER

    print(f"\n[{category}] searching: \"{query}\" (target {target_count})")

    try:
        results = DDGS().images(query, max_results=fetch_count)
    except Exception as exc:
        print(f"[{category}] SEARCH FAILED: {exc}")
        return downloaded, failed

    headers = {"User-Agent": USER_AGENT}

    for result in results:
        if downloaded >= target_count:
            break

        url = result.get("image")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_S)
            resp.raise_for_status()

            from io import BytesIO

            img = Image.open(BytesIO(resp.content))
            img.verify()

            ext = Path(urlparse(url).path).suffix.lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                ext = ".jpg"
            dest = out_dir / f"{category}_{next_index:03d}{ext}"
            dest.write_bytes(resp.content)

            downloaded += 1
            next_index += 1
            print(f"[{category}] {downloaded}/{target_count} saved: {dest.name}")

        except Exception as exc:
            failed += 1
            print(f"[{category}] skip (failed): {url} — {exc}")

        time.sleep(DELAY_BETWEEN_REQUESTS_S)

    return downloaded, failed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download small/localized-flame FIRE-class images for FireWatch via DuckDuckGo image search."
    )
    all_categories = {**CATEGORIES, **CATEGORIES_V2}
    parser.add_argument(
        "--category",
        choices=sorted(all_categories.keys()),
        default=None,
        help="Run a single category only (for retrying a failed one).",
    )
    parser.add_argument(
        "--v2",
        action="store_true",
        help=(
            "Run the v2 category set (naturalistic phrasing retry) instead of "
            f"the original set, saving into {OUTPUT_ROOT_V2}/ instead of "
            f"{OUTPUT_ROOT}/. Kept as a separate output tree so the two "
            "phrasing approaches can be compared."
        ),
    )
    args = parser.parse_args()

    active_set = CATEGORIES_V2 if args.v2 else CATEGORIES
    output_root = OUTPUT_ROOT_V2 if args.v2 else OUTPUT_ROOT

    categories = (
        {args.category: all_categories[args.category]} if args.category else active_set
    )

    summary: list[tuple[str, int, int, int]] = []
    for category, (query, target_count) in categories.items():
        downloaded, failed = download_category(category, query, target_count, output_root)
        summary.append((category, target_count, downloaded, failed))

    print("\n" + "=" * 60)
    print(f"{'Category':<22}{'Requested':>10}{'Downloaded':>12}{'Failed':>10}")
    print("-" * 60)
    total_requested = total_downloaded = total_failed = 0
    for category, requested, downloaded, failed in summary:
        print(f"{category:<22}{requested:>10}{downloaded:>12}{failed:>10}")
        total_requested += requested
        total_downloaded += downloaded
        total_failed += failed
    print("-" * 60)
    print(f"{'TOTAL':<22}{total_requested:>10}{total_downloaded:>12}{total_failed:>10}")
    print("=" * 60)

    print(
        "\nREMINDERS:\n"
        "  1. This is FIRE-CLASS training data, not hard negatives — target "
        f"is data/train/fire/ eventually, via a full retrain, NOT immediate.\n"
        "  2. These are stock/scraped images, not self-shot photos. This is a "
        "documented limitation — record it in logs.md, same as "
        "fetch_hard_negatives.py's hard negatives.\n"
        "  3. NOT yet reviewed for quality (keyword-matched search results can "
        "mismatch visual content — see logs.md Phase 1's steam-category "
        "finding, an 83% reject rate on a similarly keyword-scraped category). "
        "A manual review pass, or at minimum a visual spot-check, should happen "
        "before this data is folded into training.\n"
        "  4. Output is organized in per-category subfolders under "
        f"{OUTPUT_ROOT}/<category>/. Whatever eventually folds this into "
        "data/train/fire/ will need to walk this recursively, same pattern "
        "prepare_data.py already uses for data/hard_negatives/. Not resolved "
        "here — prepare_data.py was not touched this session.\n"
        "  5. data/additional_fire_training/personal_stove/ (developer-provided "
        "personal photos) is a separate input to the eventual retrain, not "
        "produced by this script."
    )


if __name__ == "__main__":
    sys.exit(main())
