"""One-time manual review utility for the hard-negative images pulled by
scripts/fetch_hard_negatives.py — not part of edge/agent/train application
code, same category as scripts/test_camera.py. Exempt from
config.yaml-for-tunables per info.md §3.1.

Purpose: the DuckDuckGo/ddgs scrape matches on keywords, not visual content,
so some results are wrong (e.g. a commercial steam-kettle product photo
landing in the "steam" category with no visible vapor). This app lets the
developer look at each image and approve or reject it before
train/prepare_data.py treats these counts as clean.

How to run:
    streamlit run scripts/review_hard_negatives.py

Reject moves the file to data/hard_negatives_rejected/<category>/ (never
deletes). Decisions persist across restarts in
data/hard_negatives_review_state.json (gitignored, since data/ is already
covered by .gitignore).
"""

import json
from pathlib import Path

import streamlit as st

HARD_NEGATIVES_DIR = Path("data/hard_negatives")
REJECTED_DIR = Path("data/hard_negatives_rejected")
STATE_FILE = Path("data/hard_negatives_review_state.json")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def load_state() -> dict[str, str]:
    """Load filename -> 'kept' | 'rejected' decisions made in prior sessions."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict[str, str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def list_categories() -> list[str]:
    if not HARD_NEGATIVES_DIR.exists():
        return []
    return sorted(p.name for p in HARD_NEGATIVES_DIR.iterdir() if p.is_dir())


def list_images(category: str) -> list[Path]:
    category_dir = HARD_NEGATIVES_DIR / category
    return sorted(
        p for p in category_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS
    )


def state_key(category: str, filename: str) -> str:
    return f"{category}/{filename}"


def reject_image(image_path: Path, category: str) -> None:
    """Move a rejected image out of the review pool, preserving the file."""
    dest_dir = REJECTED_DIR / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    image_path.rename(dest_dir / image_path.name)


def main() -> None:
    st.set_page_config(page_title="Hard negatives review", layout="centered")

    if "review_state" not in st.session_state:
        st.session_state.review_state = load_state()

    categories = list_categories()
    if not categories:
        st.error(f"No categories found under {HARD_NEGATIVES_DIR}/")
        return

    st.sidebar.title("Categories")
    selected_category = st.sidebar.radio("Jump to category", categories)

    images = list_images(selected_category)
    if not images:
        st.warning(f"No images left in '{selected_category}' — all reviewed or rejected.")
        return

    # Find the first not-yet-decided image in this category.
    pending = [
        img for img in images
        if state_key(selected_category, img.name) not in st.session_state.review_state
    ]

    decided_count = len(images) - len(pending)
    kept_count = sum(
        1 for img in images
        if st.session_state.review_state.get(state_key(selected_category, img.name)) == "kept"
    )
    rejected_count = sum(
        1 for img in images
        if st.session_state.review_state.get(state_key(selected_category, img.name)) == "rejected"
    )

    if not pending:
        st.success(
            f"'{selected_category}' fully reviewed — "
            f"kept {kept_count}, rejected {rejected_count} out of {len(images)}."
        )
        return

    current = pending[0]
    position = decided_count + 1

    st.subheader(f"Reviewing {selected_category}: {position} of {len(images)}")
    st.caption(current.name)
    st.image(str(current), width="stretch")

    col_keep, col_reject = st.columns(2)
    with col_keep:
        if st.button("Keep", type="primary", width="stretch"):
            st.session_state.review_state[state_key(selected_category, current.name)] = "kept"
            save_state(st.session_state.review_state)
            st.rerun()
    with col_reject:
        if st.button("Reject", width="stretch"):
            reject_image(current, selected_category)
            st.session_state.review_state[state_key(selected_category, current.name)] = "rejected"
            save_state(st.session_state.review_state)
            st.rerun()

    st.divider()
    st.caption(f"So far in {selected_category}: kept {kept_count}, rejected {rejected_count}")


if __name__ == "__main__":
    main()
