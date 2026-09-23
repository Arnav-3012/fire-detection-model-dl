"""Live hardware verification of currently-burned-in firmware constants
(arduino/sensor_esp32_node/sensor_esp32_node.ino).

Unlike calibrate_mq.py (which derives NEW baseline/warn/danger values
from raw readings using the old formula/CSV-only sketch), this reads the
CURRENT PRODUCTION firmware's own live-printed OK-state line --

    mq2,mq135,ok,baseline_mq2=...,warn_mq2=...,danger_mq2=...,
    baseline_mq135=...,warn_mq135=...,danger_mq135=...

-- and checks whether a fresh stimulus still agrees with the constants
already burned into the sketch. It does NOT recompute warn/danger to
decide anything -- it trusts the firmware's own printed values, and
separately cross-checks them against the ratio formula so a
firmware/script mismatch (e.g. board not reflashed) is caught loudly
rather than silently skewing every other number in the report.

NOTE (2026-09-23): WARN/DANGER are now RATIO-based
(WARN_RS_RATIO=0.50, DANGER_RS_RATIO=0.37 -- Rs relative to the
baseline's Rs), not the old baseline + 0.30/0.50 * CALIBRATED_DELTA
form. The delta constants are no longer part of the threshold path;
the observed-vs-burned-in delta comparison below is retained purely as
a sensor-consistency check ("is this sensor still producing the same
response to the same stimulus?"), not as a threshold check.

Both sensors respond to the gas-stove stimulus (MQ135's original delta
was itself measured as cross-talk from stove gas), so ONE stove run
exercises both -- a separate breath test is not required.

Usage:
  python3 eval/verify_live.py --stimulus gas_stove

Logs continuously (like calibrate_mq.py --peak), tracks the observed
peak raw reading AND the baseline_* printed by the firmware AT THAT
MOMENT (not a separately-computed one, since the tracked baseline
moves during a stimulus per guard 1's freeze-above-WARN rule). Ctrl+C
to stop and print a verification report: observed delta vs burned-in
delta, % difference, and headroom against the hard ceiling.

Only WARMUP/BASELINE_CAPTURE/ok/ok(BASELINE_TROUBLE)/GAS_HIGH state
strings are recognized (must match sensor_esp32_node.ino's Serial.print
calls exactly) -- an unrecognized state string is treated as a
malformed line and skipped, same convention as calibrate_mq.py.
"""

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import serial
import yaml

CALIBRATION_DIR = Path(__file__).resolve().parent / "calibration"

# Burned-in firmware constants, kept in sync BY HAND with
# arduino/sensor_esp32_node/sensor_esp32_node.ino -- there is no shared
# source of truth between the .ino and this script. If you change one,
# change the other. See logs.md 2026-09-23 entries for how each was set.
BURNED_IN = {
    "mq2": dict(delta=1121, hard_ceiling=1400),
    "mq135": dict(delta=572, hard_ceiling=750),
}

# WARN/DANGER became ratio-based on 2026-09-23 (see the RATIO-BASED
# WARN/DANGER THRESHOLDS block in sensor_esp32_node.ino). The delta
# values above are NO LONGER used by the firmware's threshold path --
# they are kept here only as the reference "what a full stimulus
# produced" figure that the observed-delta comparison reports against,
# which is still a useful consistency check on the sensor itself even
# though it no longer drives any threshold.
ADC_MAX = 4095.0
WARN_RS_RATIO = 0.50
DANGER_RS_RATIO = 0.37


def ratio_threshold(baseline_adc: float, rs_ratio: float) -> float:
    """Port of ratioThreshold() in sensor_esp32_node.ino."""
    if baseline_adc <= 0 or baseline_adc >= ADC_MAX:
        return -1
    rs_base = ADC_MAX / baseline_adc - 1.0
    return ADC_MAX / (1.0 + rs_ratio * rs_base)

# Matches the OK-state line's key=value fields, e.g. "baseline_mq2=140.23"
FIELD_RE = re.compile(r"([a-zA-Z0-9_]+)=(-?\d+\.?\d*)")


@dataclass
class Reading:
    timestamp: float
    mq2: int
    mq135: int
    state: str
    fields: dict  # parsed baseline_mq2/warn_mq2/danger_mq2/... when present, else {}


def load_serial_config() -> tuple[str, int]:
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config["sensors"]["serial_port"], config["sensors"]["baud"]


def open_serial(port: str, baud: int) -> serial.Serial:
    ser = serial.Serial(port, baud, timeout=1)
    time.sleep(3)  # ESP32 auto-resets when the port opens; first reads are garbage/empty otherwise
    ser.reset_input_buffer()
    for _ in range(10):
        if read_one(ser) is not None:
            return ser
    print(f"WARNING: no valid line received from {port} in the first ~10s after connecting. "
          "The board may still be resetting, the wrong sketch may be uploaded, or the port may be stale.",
          file=sys.stderr)
    return ser


def read_one(ser: serial.Serial) -> Reading | None:
    """Parse one line of sensor_esp32_node.ino's per-loop Serial output.

    Format: 'mq2,mq135,STATE[,key=val,...]'. Lines during WARMUP/
    BASELINE_CAPTURE have no trailing key=val fields; the main OK-state
    loop line does. Bracketed [TAG]-prefixed diagnostic lines (e.g.
    [WARMUP_STABLE], [SUSPECT_JUMP]) are printed separately by the
    firmware and are not 'mq2,mq135,...' lines -- skipped here as
    malformed, same as any other non-matching line.
    """
    raw = ser.readline().decode("utf-8", errors="ignore").strip()
    if not raw or raw.startswith("["):
        return None
    parts = raw.split(",")
    if len(parts) < 3:
        return None
    try:
        mq2 = int(float(parts[0]))
        mq135 = int(float(parts[1]))
    except ValueError:
        return None
    state = parts[2]
    fields = dict(FIELD_RE.findall(",".join(parts[3:])))
    fields = {k: float(v) for k, v in fields.items()}
    return Reading(timestamp=time.time(), mq2=mq2, mq135=mq135, state=state, fields=fields)


def open_csv_writer(label: str):
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    path = CALIBRATION_DIR / f"verify_{label}_{int(time.time())}.csv"
    f = open(path, "w", newline="")
    writer = csv.writer(f)
    writer.writerow(["timestamp", "mq2", "mq135", "state", "baseline_mq2", "warn_mq2", "danger_mq2",
                      "baseline_mq135", "warn_mq135", "danger_mq135"])
    return f, writer, path


def run_verify(ser: serial.Serial, label: str) -> None:
    f, writer, path = open_csv_writer(label)
    max_mq2 = max_mq135 = 0
    # Track baseline AT THE MOMENT of each sensor's peak, since the
    # tracked baseline can move (guard 1 freezes it only once WARN is
    # exceeded, so it can still drift beforehand) -- using a single
    # end-of-run baseline would misattribute drift-before-stimulus as
    # part of the observed delta.
    baseline_mq2_at_peak = baseline_mq135_at_peak = None
    warn_at_peak = {}
    warn_seen_mq2 = warn_seen_mq135 = False
    gas_high_seen = False
    n_ok_lines = 0

    print(f"Logging for stimulus test '{label}'. Writing to {path}")
    print("Apply the stimulus now (UNLIT gas-stove release, ~20cm, ~5s -- matching the original "
          "calibration method; both sensors respond to it). Ctrl+C to stop and report.\n")
    try:
        while True:
            r = read_one(ser)
            if r is None:
                continue
            writer.writerow([r.timestamp, r.mq2, r.mq135, r.state,
                              r.fields.get("baseline_mq2"), r.fields.get("warn_mq2"), r.fields.get("danger_mq2"),
                              r.fields.get("baseline_mq135"), r.fields.get("warn_mq135"), r.fields.get("danger_mq135")])

            if r.state in ("WARMUP", "BASELINE_CAPTURE"):
                print(f"\r  [{r.state}] mq2={r.mq2:4d} mq135={r.mq135:4d} -- waiting for OK state...",
                      end="", flush=True)
                continue

            n_ok_lines += 1
            if r.mq2 > max_mq2:
                max_mq2 = r.mq2
                baseline_mq2_at_peak = r.fields.get("baseline_mq2")
                warn_at_peak["mq2"] = r.fields.get("warn_mq2")
            if r.mq135 > max_mq135:
                max_mq135 = r.mq135
                baseline_mq135_at_peak = r.fields.get("baseline_mq135")
                warn_at_peak["mq135"] = r.fields.get("warn_mq135")

            if r.fields.get("warn_mq2") is not None and r.mq2 >= r.fields["warn_mq2"]:
                warn_seen_mq2 = True
            if r.fields.get("warn_mq135") is not None and r.mq135 >= r.fields["warn_mq135"]:
                warn_seen_mq135 = True
            if r.state == "GAS_HIGH":
                gas_high_seen = True

            print(f"\r  [{r.state:20s}] mq2={r.mq2:4d} (max {max_mq2:4d})  mq135={r.mq135:4d} (max {max_mq135:4d})",
                  end="", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        f.close()
    print("\n")

    if n_ok_lines == 0:
        print("No OK-state readings captured -- board never left WARMUP/BASELINE_CAPTURE. "
              "Nothing to verify; run again and wait for OK state before Ctrl+C.")
        return

    print(f"--- Verification report, label='{label}' ({n_ok_lines} OK-state samples) ---\n")
    print(f"Live buzzer/alarm observed this run: {'YES (GAS_HIGH state seen)' if gas_high_seen else 'no'}")
    print(f"WARN crossed this run: MQ2={'yes' if warn_seen_mq2 else 'no'}  MQ135={'yes' if warn_seen_mq135 else 'no'}\n")

    for name, max_raw, baseline_at_peak in (
        ("mq2", max_mq2, baseline_mq2_at_peak),
        ("mq135", max_mq135, baseline_mq135_at_peak),
    ):
        burned = BURNED_IN[name]
        print(f"[{name.upper()}]")
        if baseline_at_peak is None:
            print("  Could not determine baseline at peak (firmware didn't print baseline_* fields "
                  "on the peak line -- was this really the OK-state line?). Skipping delta comparison.\n")
            continue

        observed_delta = max_raw - baseline_at_peak
        burned_delta = burned["delta"]
        pct_diff = 100 * (observed_delta - burned_delta) / burned_delta

        print(f"  baseline at peak:     {baseline_at_peak:.1f}")
        print(f"  observed peak (raw):  {max_raw}")
        print(f"  observed delta:       {observed_delta:.1f}")
        print(f"  burned-in delta:      {burned_delta}  (MQ{'2' if name=='mq2' else '135'}_CALIBRATED_DELTA_PLACEHOLDER)")
        print(f"  difference:           {pct_diff:+.1f}%")
        if abs(pct_diff) < 10:
            print("  -> within 10%, consistent with the burned-in value.")
        else:
            direction = "HIGHER" if pct_diff > 0 else "LOWER"
            suggested = round(observed_delta)
            print(f"  -> {direction} than burned-in by >10%. Consider updating "
                  f"MQ{'2' if name=='mq2' else '135'}_CALIBRATED_DELTA_PLACEHOLDER to ~{suggested} "
                  "(or re-run to confirm before changing firmware -- one run is not enough on its own, "
                  "per this project's existing n=3 convention for delta calibration).")

        # Cross-check: does the firmware's own printed WARN match what the
        # ratio formula predicts from the same baseline? A mismatch means
        # the .ino and this script have drifted out of sync (different
        # ratio constants, or the firmware wasn't reflashed) -- worth
        # catching loudly, since every other number here would then be
        # comparing against the wrong thing.
        printed_warn = warn_at_peak.get(name)
        if printed_warn is not None:
            expected_warn = ratio_threshold(baseline_at_peak, WARN_RS_RATIO)
            if expected_warn > 0 and abs(printed_warn - expected_warn) > 1.0:
                print(f"  !! WARN MISMATCH: firmware printed {printed_warn:.1f}, "
                      f"ratio formula predicts {expected_warn:.1f} -- the board may be running "
                      "older firmware (reflash), or the ratio constants differ between "
                      "sensor_esp32_node.ino and this script.")
            else:
                print(f"  firmware WARN:        {printed_warn:.1f}  (matches ratio formula)")

        ceiling = burned["hard_ceiling"]
        headroom_pct = 100 * max_raw / ceiling
        print(f"  hard ceiling:         {ceiling}  (MQ{'2' if name=='mq2' else '135'}_HARD_CEILING_PLACEHOLDER)")
        print(f"  peak as % of ceiling: {headroom_pct:.1f}%")
        if headroom_pct >= 90:
            print("  -> WARNING: observed peak is within 10% of the hard ceiling. If this was a normal-strength "
                  "stimulus (not a deliberate attempt to saturate), the ceiling may need review.")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stimulus", type=str, required=True,
                         help="label for this run, e.g. 'mq2_stove' or 'mq135_breath' (used in the output CSV filename)")
    parser.add_argument("--port", type=str, default=None, help="override config.yaml sensors.serial_port")
    parser.add_argument("--baud", type=int, default=None, help="override config.yaml sensors.baud")
    args = parser.parse_args()

    config_port, config_baud = load_serial_config()
    port = args.port or config_port
    baud = args.baud or config_baud

    if port in (None, "NOT SET"):
        print("serial_port is not set in config.yaml and no --port was given.", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to {port} @ {baud} baud...")
    try:
        ser = open_serial(port, baud)
    except serial.SerialException as e:
        print(f"Could not open serial port {port}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        run_verify(ser, args.stimulus)
    finally:
        ser.close()


if __name__ == "__main__":
    main()
