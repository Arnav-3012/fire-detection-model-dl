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

ADC_MAX = 4095.0
WARN_RS_RATIO = 0.50  # matches WARN_RS_RATIO in sensor_esp32_node.ino


def ratio_threshold(baseline_adc, rs_ratio=WARN_RS_RATIO):
    """Port of ratioThreshold() in sensor_esp32_node.ino.

    WARN/DANGER became ratio-based (Rs relative to the baseline's Rs)
    on 2026-09-23, replacing the old baseline + 0.30*delta form -- see
    that file's RATIO-BASED WARN/DANGER THRESHOLDS block for why.
    """
    if baseline_adc <= 0 or baseline_adc >= ADC_MAX:
        return -1
    rs_base = ADC_MAX / baseline_adc - 1.0
    return ADC_MAX / (1.0 + rs_ratio * rs_base)

# ramp_total is sized to 1.5x the WARN gap at this sensor's starting
# baseline so the ramp alone, if fully absorbed into the baseline
# (cap OFF), comfortably would have reached WARN -- otherwise "WARN
# never crossed" is meaningless: it could mean the cap is working, or
# just that the ramp was too small to ever reach WARN regardless of the
# cap. An earlier version used a fixed ramp_total=50/25 without checking
# this and produced "never crossed" under BOTH cap ON and cap OFF --
# not a finding, just an undersized ramp. See logs.md.
_MQ2_BASE, _MQ135_BASE = 140, 40
SENSORS = {
    "mq2": dict(baseline0=_MQ2_BASE, cap=10, ramp_hours=2, noise=4,
                ramp_total=1.5 * (ratio_threshold(_MQ2_BASE) - _MQ2_BASE)),
    "mq135": dict(baseline0=_MQ135_BASE, cap=5, ramp_hours=2, noise=2,
                  ramp_total=1.5 * (ratio_threshold(_MQ135_BASE) - _MQ135_BASE)),
}


def step(baseline, anchor, anchor_tick, t, raw, cap, cap_enabled):
    """One simulated tick, in the same order as loop() in the .ino."""
    warn = ratio_threshold(baseline)
    exceeded = (warn > 0) and (raw >= warn)

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
            baseline, anchor, anchor_tick, t, raw, cfg["cap"], cap_enabled
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
                baseline, anchor, anchor_tick, t, raw, cfg["cap"], True
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
