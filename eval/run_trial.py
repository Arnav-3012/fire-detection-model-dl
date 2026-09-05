"""Day 11 evaluation trial logger (info.md 4.4): wraps ONE run of
edge/main.py and logs the outcome to eval/results.csv.

Companion script only — does NOT import or reimplement any detection/
fusion logic (info.md 3.4, and the developer's explicit instruction for
this script). edge/main.py already prints its fused level every frame
(`format_status()`'s trailing "{level.name}: {reason}") and on every
alarm transition ("*** LOCAL ALARM ON/OFF ..."). This script launches
main.py as a real subprocess with its stdout piped back here, and reads
the level off that existing text — the exact same verdict a developer
watching the console would see, just also timestamped and logged.

Usage (see also --help):

    python eval/run_trial.py --label candle_no_gas --expected WARNING

Run it from the repo root, same as `python edge/main.py` — main.py opens
config.yaml with a relative path. Ctrl+C ends the trial (best-effort
SIGINT is also sent to main.py so the buzzer is silenced via its own
`finally` block, unchanged).
"""

from __future__ import annotations

import argparse
import csv
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_CSV = REPO_ROOT / "eval" / "results.csv"

FIELDNAMES = [
    "trial_id",
    "timestamp",
    "trial_label",
    "expected_outcome",
    "actual_outcome",
    "detection_latency_seconds",
    "pass",
]

LEVELS = ("SAFE", "WATCH", "WARNING", "CRITICAL")

# Matches the trailing "{level.name}: {reason}" that format_status() in
# edge/main.py prints on every frame — deliberately the SAME line a
# developer reads live, not a separate machine-readable format.
LEVEL_LINE_RE = re.compile(r"\b(SAFE|WATCH|WARNING|CRITICAL):")

# known adversarial cases where a stricter-than-expected outcome is still
# a documented pass (info.md 4.2's TV/laptop-fire limitation). Keyed by a
# substring of --label; extend as new documented bounds are agreed.
ACCEPTABLE_BOUNDS: dict[str, tuple[str, ...]] = {
    "tv_fire": ("WARNING", "CRITICAL"),
    "tv_fire_adversarial": ("WARNING",),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run one FireWatch evaluation trial: launches edge/main.py, "
        "watches its stdout for fusion level changes, and logs the outcome to "
        "eval/results.csv (info.md 4.4)."
    )
    p.add_argument(
        "--label",
        required=True,
        help='Free-text trial label, e.g. "candle_no_gas" or "tv_fire_adversarial".',
    )
    p.add_argument(
        "--expected",
        required=True,
        choices=LEVELS,
        help="Expected outcome level for this trial.",
    )
    p.add_argument(
        "--target-level",
        choices=LEVELS,
        default=None,
        help="Optional: level to watch for when recording detection_latency_seconds. "
        "Defaults to the first level reached that differs from the initial reading "
        "(usually SAFE).",
    )
    return p.parse_args()


def resolve_pass(expected: str, actual: str, label: str) -> bool:
    """actual matches expected, or matches a documented acceptable bound
    for known adversarial cases (info.md 4.2), e.g. TV-fire: WARNING
    acceptable, CRITICAL would fail."""
    if actual == expected:
        return True
    for key, bounds in ACCEPTABLE_BOUNDS.items():
        if key in label.lower():
            return actual in bounds
    return False


def run_trial(label: str, expected: str, target_level: str | None) -> None:
    print(f"Starting trial: label={label!r} expected={expected}")
    print("Launching edge/main.py — Ctrl+C to end the trial once the outcome is clear.\n")

    proc = subprocess.Popen(
        [sys.executable, "-u", "edge/main.py"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    start = time.monotonic()
    initial_level: str | None = None
    detection_latency: float | None = None
    highest_level = "SAFE"
    highest_rank = 0

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            match = LEVEL_LINE_RE.search(line)
            if not match:
                continue
            level = match.group(1)
            rank = LEVELS.index(level)

            if initial_level is None:
                initial_level = level

            if rank > highest_rank:
                highest_rank = rank
                highest_level = level

            if detection_latency is None:
                reached_target = (
                    level == target_level if target_level else level != initial_level
                )
                if reached_target:
                    detection_latency = time.monotonic() - start
                    print(
                        f"\n*** trial helper: detection latency = "
                        f"{detection_latency:.2f}s (reached {level}) ***\n"
                    )
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.terminate()

    actual_outcome = highest_level
    passed = resolve_pass(expected, actual_outcome, label)
    log_result(label, expected, actual_outcome, detection_latency, passed)
    print_summary(label, expected, actual_outcome, detection_latency, passed)


def log_result(
    label: str,
    expected: str,
    actual: str,
    latency: float | None,
    passed: bool,
) -> None:
    """Append one row. Creates the file with headers on first run;
    append-only after that (info.md 6's never-overwrite-history rule)."""
    file_exists = RESULTS_CSV.exists()
    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "trial_id": str(uuid.uuid4()),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "trial_label": label,
                "expected_outcome": expected,
                "actual_outcome": actual,
                "detection_latency_seconds": (
                    f"{latency:.3f}" if latency is not None else ""
                ),
                "pass": passed,
            }
        )


def print_summary(
    label: str,
    expected: str,
    actual: str,
    latency: float | None,
    passed: bool,
) -> None:
    banner = "PASS" if passed else "FAIL"
    latency_str = f"{latency:.2f}s" if latency is not None else "not reached"
    print("\n" + "=" * 50)
    print(f"TRIAL RESULT: {banner}")
    print(f"  label:              {label}")
    print(f"  expected:           {expected}")
    print(f"  actual (highest):   {actual}")
    print(f"  detection latency:  {latency_str}")
    print(f"  logged to:          {RESULTS_CSV.relative_to(REPO_ROOT)}")
    print("=" * 50)


def main() -> None:
    args = parse_args()
    run_trial(args.label, args.expected, args.target_level)


if __name__ == "__main__":
    main()
