"""One-time data collection utility: downloads hard-negative images via
DuckDuckGo image search (`ddgs` package) for the FireWatch vision dataset.

Not part of edge/train/agent application code — same category as
scripts/test_camera.py. Exempt from config.yaml-for-tunables per info.md
§3.1: the category dict below is a one-off dataset-building input, not a
runtime tunable.

Chosen over the Pixabay API after discovering Pixabay gates hi-res image
downloads behind a 24-hour manual approval, which does not fit this
project's timeline. `ddgs` needs no API key, no signup, no wait.

Covers 6 of the 7 hard-negative categories in plan.md §6.4. The 7th
category — "TV or laptop screen showing fire footage" (30 images) — is
deliberately excluded here. It is not a natural photography subject
(search results return marketing photos of TVs, not screenshots of fire
footage playing on a screen), so it needs manual screenshot collection
instead. See the reminder printed at the end of this script.
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
    "sunset_window": ("sunset through window", 50),
    "red_orange_objects": ("red orange cushion pillow blanket closeup indoor", 40),
    "warm_lights": ("fairy lights room candle table lamp warm", 50),
    "steam": ("boiling kettle steam vapor rising closeup", 50),
    "car_lights_night": ("car headlights night street", 30),
    "stove_cooking": ("gas stove cooking flame kitchen", 50),
}

# 7th category from plan.md §6.4, NOT covered by this script — see docstring.
MANUAL_CATEGORY = "TV or laptop screen showing fire footage"
MANUAL_CATEGORY_COUNT = 30

OUTPUT_ROOT = Path("data/hard_negatives")
REQUEST_TIMEOUT_S = 5
DELAY_BETWEEN_REQUESTS_S = 0.5
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# Pull more candidate URLs than the target, since some downloads will fail.
# Raised from 4 to 8 after the first run left several categories short even
# before manual review (see logs.md Phase 1) — download failures alone
# (mostly 403s from hotlink-protected stock sites) ate a large fraction of
# candidates, and manual review removes more on top of that.
CANDIDATE_MULTIPLIER = 8


def next_free_index(out_dir: Path, category: str) -> int:
    """Find the first filename index not already used in out_dir.

    Re-running a category (e.g. to top up after manual review rejected
    some images) must never reuse an existing index — a previous run, or a
    developer's Keep/Reject decision, may already have a real file there.
    Silently overwriting it destroys that file with no warning.
    """
    existing = list(out_dir.glob(f"{category}_*.*"))
    if not existing:
        return 0
    used_indices = []
    for path in existing:
        stem = path.stem  # e.g. "steam_007"
        suffix = stem.rsplit("_", 1)[-1]
        if suffix.isdigit():
            used_indices.append(int(suffix))
    return max(used_indices, default=-1) + 1


def download_category(category: str, query: str, target_count: int) -> tuple[int, int]:
    """Download up to target_count valid images for one category.

    Returns (downloaded, failed) counts. Stops once target_count VALID
    saved images are reached, pulling extra candidate URLs as needed since
    some will fail (dead link, timeout, corrupt/non-image response).
    """
    out_dir = OUTPUT_ROOT / category
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

            # Verify it is actually a valid image before saving.
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
        description="Download hard-negative images for FireWatch via DuckDuckGo image search."
    )
    parser.add_argument(
        "--category",
        choices=sorted(CATEGORIES.keys()),
        default=None,
        help="Run a single category only (for retrying a failed one).",
    )
    args = parser.parse_args()

    categories = (
        {args.category: CATEGORIES[args.category]} if args.category else CATEGORIES
    )

    summary: list[tuple[str, int, int, int]] = []
    for category, (query, target_count) in categories.items():
        downloaded, failed = download_category(category, query, target_count)
        summary.append((category, target_count, downloaded, failed))

    print("\n" + "=" * 60)
    print(f"{'Category':<22}{'Requested':>10}{'Downloaded':>12}{'Failed':>10}")
    print("-" * 60)
    for category, requested, downloaded, failed in summary:
        print(f"{category:<22}{requested:>10}{downloaded:>12}{failed:>10}")
    print("=" * 60)

    print(
        "\nREMINDERS:\n"
        f"  1. Manual collection still needed: \"{MANUAL_CATEGORY}\" — "
        f"target {MANUAL_CATEGORY_COUNT} images. Not covered by this script "
        "(not a natural photography subject).\n"
        "  2. These are stock/scraped images, not self-shot photos. This is a "
        "documented limitation — record it in logs.md.\n"
        "  3. Output is organized in per-category subfolders under "
        f"{OUTPUT_ROOT}/<category>/. train/prepare_data.py (next session) will "
        "need to walk this recursively, not expect a flat directory. Not "
        "resolved here."
    )


if __name__ == "__main__":
    sys.exit(main())
