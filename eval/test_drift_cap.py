"""Bench validation for BASELINE_DRIFT_CAP_PER_HOUR (arduino/sensor_esp32_node/sensor_esp32_node.ino).

Pure-Python port of the firmware's EMA baseline tracker + drift-cap guard
(no hardware). Validates the constant two ways, without waiting on real
wall-clock hours or a live gas stimulus:

  1. Synthetic slow-ramp: with the cap OFF, a slow gas-like rise should
     never cross WARN (reproduces the "learned away" failure the cap
     exists to prevent). With the cap ON, it should cross WARN within a
     bounded, reportable latency.
  2. Real passive log replay: feeding last night's actual undisturbed
     capture (eval/calibration/drift_*.csv) through the cap-enabled path
     should NEVER engage the clamp -- if it does, the cap is too tight
     for real ordinary baseline wandering and will cause false "trouble"
     chirps.

Constants below must be kept in sync with the .ino by hand -- there is no
shared source of truth. See logs.md 2026-09-23 entry for how the cap
values (MQ2=10, MQ135=5) were derived and why they are not yet final.
"""

import csv
import random
import sys
from pathlib import Path

ALPHA = 0.001  # BASELINE_EMA_ALPHA
ANCHOR_INTERVAL_S = 3600  # re-anchor cadence, matches millis() - lastDriftCapCheckMs >= 3600000UL

WARN_MULT = 0.30  # matches mq*Warn = baseline + 0.30 * delta in the firmware

# ramp_total is set to 1.5x the WARN gap (0.30*delta) so the ramp alone,
# if fully absorbed into the baseline (cap OFF), comfortably would have
# reached WARN -- otherwise "WARN never crossed" is meaningless: it could
# mean the cap is working, or just that the ramp was too small to ever
# reach WARN regardless of the cap. An earlier version of this script
# used a fixed ramp_total=50/25 without checking this and produced a
# "never crossed" result under BOTH cap ON and cap OFF -- not a finding,
# just an undersized ramp (only ~15% of the WARN gap). See logs.md.
SENSORS = {
    "mq2": dict(baseline0=140, delta=1121, cap=10, ramp_total=1.5 * 0.30 * 1121, ramp_hours=2, noise=4),
    "mq135": dict(baseline0=40, delta=572, cap=5, ramp_total=1.5 * 0.30 * 572, ramp_hours=2, noise=2),
}


def step(baseline, anchor, anchor_tick, t, raw, delta, cap, cap_enabled):
    """One simulated tick, in the same order as loop() in the .ino."""
    warn = baseline + WARN_MULT * delta
    exceeded = raw >= warn

    # Guard 1: EMA update only when NOT exceeded.
    if not exceeded:
        baseline = (1 - ALPHA) * baseline + ALPHA * raw

    clamped = False
    if cap_enabled:
        # Guard 2: re-anchor once per rolling hour, then clamp.
        if t - anchor_tick >= ANCHOR_INTERVAL_S:
            anchor = baseline
            anchor_tick = t
        drift = baseline - anchor
        if drift > cap:
            baseline = anchor + cap
            clamped = True
        elif drift < -cap:
            baseline = anchor - cap
            clamped = True

    return baseline, anchor, anchor_tick, warn, exceeded, clamped


def simulate_ramp(cfg, cap_enabled, seed=0):
    rng = random.Random(seed)
    baseline = cfg["baseline0"]
    anchor = baseline
    anchor_tick = 0
    ramp_ticks = cfg["ramp_hours"] * 3600
    warn_cross_tick = None

    for t in range(ramp_ticks):
        ramp = cfg["ramp_total"] * (t / ramp_ticks)
        raw = cfg["baseline0"] + ramp + rng.uniform(-cfg["noise"], cfg["noise"])

        baseline, anchor, anchor_tick, warn, exceeded, _ = step(
            baseline, anchor, anchor_tick, t, raw, cfg["delta"], cfg["cap"], cap_enabled
        )
        if warn_cross_tick is None and exceeded:
            warn_cross_tick = t

    return warn_cross_tick


def simulate_real_log(cfg, csv_path, column):
    baseline = cfg["baseline0"]
    anchor = baseline
    anchor_tick = 0
    clamp_events = 0
    total_ticks = 0

    with open(csv_path) as f:
        for row in csv.DictReader(f):
            if row["state"] != "OK":
                continue
            raw = int(row[column])
            t = total_ticks
            baseline, anchor, anchor_tick, warn, exceeded, clamped = step(
                baseline, anchor, anchor_tick, t, raw, cfg["delta"], cfg["cap"], True
            )
            if clamped:
                clamp_events += 1
            total_ticks += 1

    return clamp_events, total_ticks


def main():
    print("=== Synthetic slow-ramp test ===")
    for name, cfg in SENSORS.items():
        for cap_enabled in (False, True):
            t = simulate_ramp(cfg, cap_enabled)
            label = "cap ON " if cap_enabled else "cap OFF"
            if t is None:
                print(f"{name:6s} [{label}]: WARN never crossed in {cfg['ramp_hours']}h ramp")
            else:
                print(f"{name:6s} [{label}]: WARN crossed at {t/60:.1f} min")

    print("\n=== Real passive-log replay (cap ON) ===")
    calib_dir = Path(__file__).resolve().parent / "calibration"
    drift_logs = sorted(calib_dir.glob("drift_*.csv"))
    if not drift_logs:
        print("No eval/calibration/drift_*.csv found -- skipping real-log replay.")
        return

    log_path = drift_logs[-1]
    print(f"Using {log_path.name}")
    for name, column in (("mq2", "mq2_avg"), ("mq135", "mq135_avg")):
        cfg = SENSORS[name]
        clamp_events, total_ticks = simulate_real_log(cfg, log_path, column)
        pct = 100 * clamp_events / total_ticks if total_ticks else 0
        verdict = "OK -- cap never engaged" if clamp_events == 0 else "CAP ENGAGED ON REAL NORMAL DATA -- likely too tight"
        print(f"{name:6s}: clamp fired {clamp_events}/{total_ticks} ticks ({pct:.2f}%) -- {verdict}")


if __name__ == "__main__":
    sys.exit(main())
