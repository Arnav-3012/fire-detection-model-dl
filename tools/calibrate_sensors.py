"""FireWatch Phase 13b calibration tool.

Reads live serial output from arduino/sensor_calibration_capture/
sensor_calibration_capture.ino, tracks running baseline (min) and peak
(max) per sensor during a real stimulus test, and prints a
CALIBRATED_DELTA candidate (peak - baseline, same session) for manual
review -- NOT an absolute threshold. sensor_esp32_node.ino moved to
per-boot relative baselines (2026-09-20 redesign): the board captures
its own clean-air baseline fresh every boot, so the only thing this
tool needs to hand over from a stimulus test is the DELTA the gas
produced above whatever that boot's baseline was, plus, from repeated
power-cycle runs, the plausible clean-air baseline RANGE used to
sanity-check future boot captures.

This script is READ-ONLY with respect to sensor_esp32_node.ino. It does
NOT edit that file. The developer must copy the printed values into its
placeholder constants themselves, as a deliberate, reviewed step.

Usage:
    python calibrate_sensors.py <port> [baud]

    <port>  serial port, e.g. /dev/cu.usbserial-0001 or COM5
    [baud]  optional, default 9600 -- matches sensor_calibration_capture.ino's
            Serial.begin(9600)

Expects each serial line in the format documented in
sensor_calibration_capture.ino:

    <millis_since_boot>,<mq2_avg>,<mq135_avg>,<WARMUP|OK>

Lines starting with '#' (the sketch's own header comments) and any line
that doesn't parse to that shape are skipped and logged, not treated as
fatal.

While running:
    b  -- snapshot current MIN as confirmed baseline for both sensors
          (this run's clean-air baseline, for the delta calc AND as one
          data point toward the boot-baseline range below)
    p  -- snapshot current MAX as confirmed peak for both sensors
    q  -- quit and print final delta block (Ctrl+C also works)

Formula (project convention, plan.md, now relative):
    CALIBRATED_DELTA = peak - baseline   (same session/boot)
    (sensor_esp32_node.ino computes WARN = boot_baseline + 0.30*delta,
    DANGER = boot_baseline + 0.60*delta, at runtime, per boot)

RECOMMENDED WORKFLOW: run this tool across 3+ SEPARATE power cycles
of sensor_calibration_capture.ino (different times/positions), marking
baseline ('b') each time and letting the process exit ('q') between
runs. Pass --history <file> so each run's confirmed baseline is
appended to a small local record; the final run in the series prints
the min/max clean-air baseline observed across ALL recorded runs, which
is the plausible-baseline range for sensor_esp32_node.ino's boot-
baseline sanity bounds (guard 4). A single run only gives one boot's
baseline -- not, by itself, a realistic range across boots.
"""

import argparse
import json
import os
import sys
import threading

import serial


def load_history(path):
    if not path or not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def append_history(path, mq2_baseline, mq135_baseline):
    if not path:
        return
    records = load_history(path)
    records.append({"mq2_baseline": mq2_baseline, "mq135_baseline": mq135_baseline})
    with open(path, "w") as f:
        json.dump(records, f, indent=2)


def baseline_range(records, key):
    values = [r[key] for r in records if r.get(key) is not None]
    if not values:
        return None, None
    return min(values), max(values)


def read_stdin_commands(command_queue, stop_event):
    while not stop_event.is_set():
        try:
            line = sys.stdin.readline()
        except (EOFError, ValueError):
            return
        if not line:
            return
        cmd = line.strip().lower()
        if cmd:
            command_queue.append(cmd)
            if cmd == "q":
                return


def parse_line(line):
    parts = line.strip().split(",")
    if len(parts) != 4:
        return None
    millis_str, mq2_str, mq135_str, status = parts
    if status not in ("WARMUP", "OK"):
        return None
    try:
        millis_since_boot = int(millis_str)
        mq2_avg = int(mq2_str)
        mq135_avg = int(mq135_str)
    except ValueError:
        return None
    return millis_since_boot, mq2_avg, mq135_avg, status


def compute_delta(baseline, peak):
    return peak - baseline


def print_final_block(sensor_name, const_prefix, baseline, peak, baseline_range_minmax):
    print(f"\n--- {sensor_name} ---")
    if baseline is None or peak is None:
        missing = []
        if baseline is None:
            missing.append("baseline ('b')")
        if peak is None:
            missing.append("peak ('p')")
        print(f"  Not computed -- never marked: {', '.join(missing)}")
    else:
        delta = compute_delta(baseline, peak)
        print(f"  this-run clean-air baseline: {baseline}")
        print(f"  {const_prefix}_CALIBRATED_DELTA_PLACEHOLDER -> {delta}")

    range_min, range_max = baseline_range_minmax
    if range_min is None:
        print("  Boot-baseline range: no recorded history yet -- pass --history and run 3+ power cycles")
    else:
        print(f"  Observed clean-air baseline range across recorded runs: [{range_min}, {range_max}]")
        print(f"  {const_prefix}_BASELINE_MIN_PLACEHOLDER -> {range_min}")
        print(f"  {const_prefix}_BASELINE_MAX_PLACEHOLDER -> {range_max}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("port", help="serial port, e.g. /dev/cu.usbserial-0001 or COM5")
    parser.add_argument("baud", nargs="?", type=int, default=9600)
    parser.add_argument(
        "--history",
        default=None,
        help="JSON file recording each run's confirmed clean-air baseline, "
        "used to compute the boot-baseline range across 3+ power cycles",
    )
    parsed = parser.parse_args()

    port = parsed.port
    baud = parsed.baud
    history_path = parsed.history

    try:
        ser = serial.Serial(port, baud, timeout=1)
    except serial.SerialException as e:
        print(f"Could not open serial port {port}: {e}")
        sys.exit(1)

    print(f"Reading {port} @ {baud} baud. Commands: 'b'=mark baseline, 'p'=mark peak, 'q'=quit.")

    mq2_min = mq2_max = None
    mq135_min = mq135_max = None
    mq2_baseline = mq2_peak = None
    mq135_baseline = mq135_peak = None

    command_queue = []
    stop_event = threading.Event()
    stdin_thread = threading.Thread(
        target=read_stdin_commands, args=(command_queue, stop_event), daemon=True
    )
    stdin_thread.start()

    try:
        while True:
            if command_queue:
                cmd = command_queue.pop(0)
                if cmd == "b":
                    if mq2_min is not None and mq135_min is not None:
                        mq2_baseline = mq2_min
                        mq135_baseline = mq135_min
                        print(f"\n[BASELINE MARKED] MQ2={mq2_baseline} MQ135={mq135_baseline}")
                    else:
                        print("\n[BASELINE] No OK readings yet -- nothing to mark.")
                elif cmd == "p":
                    if mq2_max is not None and mq135_max is not None:
                        mq2_peak = mq2_max
                        mq135_peak = mq135_max
                        print(f"\n[PEAK MARKED] MQ2={mq2_peak} MQ135={mq135_peak}")
                    else:
                        print("\n[PEAK] No OK readings yet -- nothing to mark.")
                elif cmd == "q":
                    break

            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode(errors="replace").strip()
            if not line or line.startswith("#"):
                continue

            parsed = parse_line(line)
            if parsed is None:
                print(f"[SKIP] malformed line: {line!r}")
                continue

            _, mq2_avg, mq135_avg, status = parsed
            if status == "WARMUP":
                # Still excluded from min/max -- warmup readings must not
                # pollute the baseline or peak. But DO show them, because a
                # silently-skipped line is indistinguishable on screen from a
                # dead serial port, and that ambiguity cost three aborted
                # stove tests on 2026-09-21 before the cause was found.
                print(
                    f"\r[warming up] MQ2: cur={mq2_avg} | MQ135: cur={mq135_avg}"
                    "  (not counted)    ",
                    end="",
                    flush=True,
                )
                continue

            mq2_min = mq2_avg if mq2_min is None else min(mq2_min, mq2_avg)
            mq2_max = mq2_avg if mq2_max is None else max(mq2_max, mq2_avg)
            mq135_min = mq135_avg if mq135_min is None else min(mq135_min, mq135_avg)
            mq135_max = mq135_avg if mq135_max is None else max(mq135_max, mq135_avg)

            print(
                f"\rMQ2: cur={mq2_avg} min={mq2_min} max={mq2_max} | "
                f"MQ135: cur={mq135_avg} min={mq135_min} max={mq135_max}    ",
                end="",
                flush=True,
            )
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        ser.close()

    if mq2_baseline is not None and mq135_baseline is not None:
        append_history(history_path, mq2_baseline, mq135_baseline)
    elif history_path:
        print("\n[HISTORY] baseline not marked ('b') this run -- nothing appended to history.")

    history_records = load_history(history_path)
    mq2_range = baseline_range(history_records, "mq2_baseline")
    mq135_range = baseline_range(history_records, "mq135_baseline")

    print("\n\n=== Calibration results (paste into sensor_esp32_node.ino manually) ===")
    print_final_block("MQ-2", "MQ2", mq2_baseline, mq2_peak, mq2_range)
    print_final_block("MQ-135", "MQ135", mq135_baseline, mq135_peak, mq135_range)
    if history_path:
        print(f"\n[HISTORY] {len(history_records)} boot(s) recorded in {history_path} so far -- run 3+ separate power cycles before trusting the range above.")
    print("\nNOTE: sensor_esp32_node.ino was NOT modified by this script.")


if __name__ == "__main__":
    main()
