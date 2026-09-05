"""Day 7 fusion test scaffold: printed pass/fail per case, no framework.

Matches this project's existing testing style (standalone runnable
script, like run_eval.py / votes_needed_sweep.py) rather than pytest —
plan.md specifies no test framework, and a viva panel can read printed
expectations directly.

Run from the repo root:  python eval/test_fusion.py
Exit code 0 = all pass, 1 = at least one failure.

Note on rule 2: because plan.md's fuse() signature takes temp_spiking as
a parameter, the rule IS reachable here by forcing True at the call site
(case proving the rule is structurally intact). Production can never
reach it, because the only sanctioned source of that parameter is the
temp_spiking() stub, which always returns False — tested directly below.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "edge"))
from fusion import Level, compute_gas_high, fuse, load_gas_thresholds, temp_spiking  # noqa: E402

CONFIG_PATH = str(Path(__file__).resolve().parent.parent / "config.yaml")


def main() -> int:
    thresholds = load_gas_thresholds(CONFIG_PATH)
    failures = 0

    # (name, fuse args (vision_fire, vision_smoke, gas_high, temp_spiking),
    #  expected level, expected reason)
    fuse_cases: list[tuple[str, tuple[bool, bool, bool, bool], Level, str]] = [
        (
            "rule 1: fire + gas_high -> CRITICAL",
            (True, False, True, False),
            Level.CRITICAL,
            "visual hazard confirmed by gas sensor",
        ),
        (
            "rule 1: smoke + gas_high -> CRITICAL",
            (False, True, True, False),
            Level.CRITICAL,
            "visual hazard confirmed by gas sensor",
        ),
        (
            # THE TV/laptop-fire mitigation, confirmed explicitly (Phase 5
            # decision): vision-only fire, no gas agreement, must cap at
            # WARNING and never reach CRITICAL.
            "rule 4: fire alone, gas normal -> WARNING (TV/laptop-fire cap, NOT CRITICAL)",
            (True, False, False, False),
            Level.WARNING,
            "visual flame, unconfirmed by sensors",
        ),
        (
            "rule 3: gas_high alone, no fire/smoke -> WARNING",
            (False, False, True, False),
            Level.WARNING,
            "gas concentration high, no visible flame",
        ),
        (
            "rule 5: smoke alone -> WATCH",
            (False, True, False, False),
            Level.WATCH,
            "possible smoke, monitoring",
        ),
        (
            "rule 6: neutral, gas normal -> SAFE",
            (False, False, False, False),
            Level.SAFE,
            "nominal",
        ),
        (
            # Rule 2 structural check: forcing temp_spiking=True at the
            # call site (something production code cannot do — its only
            # source is the always-False stub) proves the rule was kept
            # in the table, not deleted.
            "rule 2 (structural): fire + forced temp_spiking=True -> CRITICAL",
            (True, False, False, True),
            Level.CRITICAL,
            "flame detected with rapid temperature rise",
        ),
        (
            "rule ordering: rule 1 outranks rule 2 when both match",
            (True, False, True, True),
            Level.CRITICAL,
            "visual hazard confirmed by gas sensor",
        ),
    ]

    for name, args, want_level, want_reason in fuse_cases:
        got_level, got_reason = fuse(*args)
        ok = got_level is want_level and got_reason == want_reason
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            print(f"       expected ({want_level.name}, {want_reason!r})")
            print(f"       got      ({got_level.name}, {got_reason!r})")

    # temp_spiking() stub: must return False until real temperature
    # hardware exists — this is what keeps rule 2 disabled in production.
    ok = temp_spiking() is False
    failures += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] temp_spiking() stub returns False (rule 2 disabled in production)")

    # gas_high derivation against the REAL calibrated config.yaml values
    # (mq2_warn=115.57, mq135_warn=98.77 as of 2026-08-31), definition:
    # either sensor at or above its warn threshold.
    gas_cases: list[tuple[str, float, float, bool]] = [
        ("gas_high: both at calm baseline -> False", 57.0, 51.0, False),
        ("gas_high: mq2 exactly at warn threshold -> True", thresholds["mq2_warn"], 51.0, True),
        ("gas_high: mq135 alone above warn -> True", 57.0, thresholds["mq135_warn"] + 1, True),
        ("gas_high: both just below warn -> False", thresholds["mq2_warn"] - 0.01, thresholds["mq135_warn"] - 0.01, False),
    ]
    for name, mq2, mq135, want in gas_cases:
        got = compute_gas_high(mq2, mq135, thresholds)
        ok = got is want
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            print(f"       expected {want}, got {got} (mq2={mq2}, mq135={mq135})")

    total = len(fuse_cases) + 1 + len(gas_cases)
    print(f"\n{total - failures}/{total} cases passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
