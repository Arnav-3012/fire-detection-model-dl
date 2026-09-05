"""MQ-2 / MQ-135 calibration helper (plan.md section 8, Day 6b; formula: section 5.5).

Connects to the Arduino over serial, logs raw MQ-2 and MQ-135 ADC values
with timestamps to a CSV in eval/calibration/, and supports two modes:

  --baseline  Log both sensors for N minutes in a normal (unexposed) room.
              At the end, print mean/std/min/max for BOTH sensors and the
              suggested warn/danger thresholds for BOTH sensors.
  --peak      Log continuously and print a live rolling max for BOTH
              sensors, labeled by which trigger test produced it.

Threshold formula (plan.md 5.5, MQ-2):
    warn   = baseline + 0.30 * (peak - baseline)
    danger = baseline + 0.60 * (peak - baseline)

MQ-135 threshold formula — decision (2026-08-30, this session): reuse the
SAME structural formula as MQ-2, rather than inventing a different ratio.
The formula is ratio-based ("how far above this sensor's own normal is
this reading"), not a sensor-specific chemistry constant, so it transfers
directly. This resolves the open item from Phase 0 where mq135_warn's
formula was never specified in plan.md.

MQ-135 peak trigger — decision (2026-08-30, this session): use a BREATH
test (exhale directly near the sensor for ~5s), not the lighter test used
for MQ-2. MQ-2 is tuned for LPG/methane/propane/smoke, so the lighter
(unlit, gas released) is the right stimulus. MQ-135 is tuned for
CO2/ammonia/benzene/general air quality, not primarily combustible gas —
breath is a safe, relevant, easily-repeatable CO2 source for it, whereas
the lighter test targets gases MQ-135 isn't the primary sensor for. See
logs.md Phase 6 for the full reasoning.

--peak supports labeling which peak belongs to which sensor's trigger test
via --label, since the two trigger tests (lighter near MQ-2, breath near
MQ-135) are done as separate passes and must not be confused.
"""

import argparse
import csv
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import serial
import yaml

CALIBRATION_DIR = Path(__file__).resolve().parent / "calibration"


def load_serial_config() -> tuple[str, int]:
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config["sensors"]["serial_port"], config["sensors"]["baud"]


@dataclass
class Reading:
    timestamp: float
    mq2: int
    mq135: int


def open_serial(port: str, baud: int) -> serial.Serial:
    ser = serial.Serial(port, baud, timeout=1)
    time.sleep(3)  # Arduino auto-resets when the port opens; first reads are garbage/empty otherwise
    ser.reset_input_buffer()

    # Confirm the board is actually sending valid lines before handing the
    # connection back — a reopen right after a prior run closed the same
    # port can catch the OS/driver mid-reset, silently returning empty
    # reads with no exception (readline() just times out). Without this
    # check, a mode that only proceeds on a non-None Reading (run_peak)
    # can loop forever reading nothing and report a false all-zero result.
    for _ in range(10):
        if read_one(ser) is not None:
            return ser
    print(f"WARNING: no valid '{{mq2}},{{mq135}}' line received from {port} in the first ~10s after connecting. "
          "The board may still be resetting, the wrong sketch may be uploaded, or the port may be stale — "
          "check the Serial Monitor is closed and the correct sketch (arduino/sensor_node.ino) is active.",
          file=sys.stderr)
    return ser


def read_one(ser: serial.Serial) -> Reading | None:
    """Read and parse a single CSV line ('mq2,mq135'). Returns None on a malformed line."""
    raw = ser.readline().decode("utf-8", errors="ignore").strip()
    if not raw:
        return None
    parts = raw.split(",")
    if len(parts) < 2:
        return None
    try:
        mq2 = int(float(parts[0]))
        mq135 = int(float(parts[1]))
    except ValueError:
        return None
    return Reading(timestamp=time.time(), mq2=mq2, mq135=mq135)


def open_csv_writer(name: str):
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    path = CALIBRATION_DIR / f"{name}_{int(time.time())}.csv"
    f = open(path, "w", newline="")
    writer = csv.writer(f)
    writer.writerow(["timestamp", "mq2", "mq135"])
    return f, writer, path


def suggest_thresholds(baseline: float, peak: float) -> tuple[float, float]:
    warn = baseline + 0.30 * (peak - baseline)
    danger = baseline + 0.60 * (peak - baseline)
    return warn, danger


def run_baseline(ser: serial.Serial, minutes: float) -> None:
    f, writer, path = open_csv_writer("baseline")
    readings: list[Reading] = []
    end_time = time.time() + minutes * 60
    print(f"Logging baseline for {minutes} minutes. Room should be at normal, unexposed conditions.")
    print(f"Writing to {path}")
    try:
        while time.time() < end_time:
            r = read_one(ser)
            if r is None:
                continue
            readings.append(r)
            writer.writerow([r.timestamp, r.mq2, r.mq135])
            remaining = end_time - time.time()
            print(f"\r  mq2={r.mq2:4d}  mq135={r.mq135:4d}  ({remaining:5.0f}s left)", end="", flush=True)
    finally:
        f.close()
    print()

    if not readings:
        print("No valid readings collected — check the serial connection and CSV format.")
        return

    mq2_vals = [r.mq2 for r in readings]
    mq135_vals = [r.mq135 for r in readings]

    def summarize(name: str, vals: list[int]) -> float:
        mean = statistics.mean(vals)
        std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        print(f"{name}: mean={mean:.1f}  std={std:.1f}  min={min(vals)}  max={max(vals)}  n={len(vals)}")
        return mean

    print(f"\n--- Baseline summary ({len(readings)} samples) ---")
    mq2_baseline = summarize("MQ-2  ", mq2_vals)
    mq135_baseline = summarize("MQ-135", mq135_vals)

    print("\nSuggested thresholds (plan.md 5.5 formula, applied to both sensors):")
    print("  warn   = baseline + 0.30 * (peak - baseline)")
    print("  danger = baseline + 0.60 * (peak - baseline)")
    print(f"\n  MQ-2   baseline = {mq2_baseline:.1f}. Run --peak with the lighter test near MQ-2 to get its peak,")
    print("         then compute mq2_warn / mq2_danger with the formula above.")
    print(f"  MQ-135 baseline = {mq135_baseline:.1f}. Run --peak with the breath test near MQ-135 to get its peak,")
    print("         then compute mq135_warn / mq135_danger with the same formula.")
    print(f"\n  (Example, if you already have a peak: suggest_thresholds({mq2_baseline:.1f}, <peak>) "
          f"-> (warn, danger))")


def run_peak(ser: serial.Serial, label: str) -> None:
    f, writer, path = open_csv_writer(f"peak_{label}")
    max_mq2 = 0
    max_mq135 = 0
    print(f"Logging continuously for the '{label}' trigger test. Writing to {path}")
    print("Ctrl+C to stop and print the final rolling max for both sensors.")
    try:
        while True:
            r = read_one(ser)
            if r is None:
                continue
            writer.writerow([r.timestamp, r.mq2, r.mq135])
            max_mq2 = max(max_mq2, r.mq2)
            max_mq135 = max(max_mq135, r.mq135)
            print(f"\r  mq2={r.mq2:4d} (max {max_mq2:4d})   mq135={r.mq135:4d} (max {max_mq135:4d})",
                  end="", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        f.close()
    print(f"\n\n--- Peak summary, label='{label}' ---")
    print(f"  MQ-2   rolling max: {max_mq2}")
    print(f"  MQ-135 rolling max: {max_mq135}")
    print(f"\n  Use the max from the sensor this trigger test targeted:")
    print(f"    lighter test near MQ-2   -> MQ-2's max ({max_mq2}) is the MQ-2 peak")
    print(f"    breath test near MQ-135  -> MQ-135's max ({max_mq135}) is the MQ-135 peak")
    print("  The other sensor's max in this same run is incidental cross-talk, not its trigger peak.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--baseline", action="store_true", help="log baseline for --minutes")
    mode.add_argument("--peak", action="store_true", help="log continuously for a live rolling max")
    parser.add_argument("--minutes", type=float, default=15.0, help="baseline duration in minutes (default 15, plan.md 5.5)")
    parser.add_argument("--label", type=str, default="unlabeled",
                         help="which trigger test this --peak run is for, e.g. 'mq2_lighter' or 'mq135_breath'")
    parser.add_argument("--port", type=str, default=None, help="override config.yaml sensors.serial_port")
    parser.add_argument("--baud", type=int, default=None, help="override config.yaml sensors.baud")
    args = parser.parse_args()

    config_port, config_baud = load_serial_config()
    port = args.port or config_port
    baud = args.baud or config_baud

    if port in (None, "NOT SET"):
        print("serial_port is not set in config.yaml and no --port was given. Set it from the Arduino IDE "
              "(Tools -> Port) first.", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to {port} @ {baud} baud...")
    try:
        ser = open_serial(port, baud)
    except serial.SerialException as e:
        print(f"Could not open serial port {port}: {e}", file=sys.stderr)
        print("Check: Arduino IDE Serial Monitor is closed, correct port name, board is connected.",
              file=sys.stderr)
        sys.exit(1)

    try:
        if args.baseline:
            run_baseline(ser, args.minutes)
        else:
            run_peak(ser, args.label)
    finally:
        ser.close()


if __name__ == "__main__":
    main()
