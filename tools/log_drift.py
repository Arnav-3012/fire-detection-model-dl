"""FireWatch Phase 13b overnight drift-capture logger.

Reads live serial output from arduino/sensor_calibration_capture/
sensor_calibration_capture.ino for a FIXED duration, then exits on its
own -- no keyboard interaction needed, safe to leave running unattended
(e.g. overnight). This is deliberately dumber than
tools/calibrate_sensors.py: it does not track min/max, does not accept
'b'/'p'/'q' commands, and does not compute a delta. Its only job is to
write every line to a CSV so BASELINE_DRIFT_CAP_PER_HOUR can be derived
from real multi-hour data afterward, offline.

Usage:
    python tools/log_drift.py <port> [minutes] [baud]

    <port>     serial port, e.g. /dev/cu.usbserial-0001 or COM5
    [minutes]  optional, default 65 -- stops automatically after this
               many minutes (default gives a comfortable margin over
               a clean 60-minute capture)
    [baud]     optional, default 9600 -- matches
               sensor_calibration_capture.ino's Serial.begin(9600)

Expects each serial line in the format documented in
sensor_calibration_capture.ino:

    <millis_since_boot>,<mq2_avg>,<mq135_avg>,<WARMUP|OK>

Lines starting with '#' (the sketch's own header/status comments) and
any line that doesn't parse to that shape are written to the output
file verbatim, prefixed so they're easy to filter out later, but never
crash the run -- a garbled or reset-related line should not end an
overnight capture early.

Output: CSV written incrementally (flushed after every line) to the
path given, so a crash or early stop still leaves partial data usable.
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port")
    parser.add_argument("minutes", nargs="?", type=float, default=65)
    parser.add_argument("baud", nargs="?", type=int, default=9600)
    parser.add_argument(
        "--out",
        default=None,
        help="output CSV path (default: eval/calibration/drift_<timestamp>.csv)",
    )
    args = parser.parse_args()

    out_path = args.out or f"eval/calibration/drift_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    deadline = time.monotonic() + args.minutes * 60

    print(f"Logging {args.port} @ {args.baud} baud for {args.minutes:.0f} minutes -> {out_path}")
    print("No keyboard interaction needed. Safe to leave unattended. Ctrl+C to stop early.")

    line_count = 0
    skip_count = 0

    with serial.Serial(args.port, args.baud, timeout=5) as ser, open(out_path, "w", newline="") as f:
        f.write("wall_clock_utc,millis_since_boot,mq2_avg,mq135_avg,state\n")
        f.flush()

        try:
            while time.monotonic() < deadline:
                try:
                    raw = ser.readline()
                except serial.SerialException as e:
                    f.write(f"# [SERIAL_ERROR] {e}\n")
                    f.flush()
                    print(f"[SERIAL_ERROR] {e} -- stopping capture")
                    break

                if not raw:
                    continue  # readline timeout, no data this cycle -- keep waiting

                try:
                    line = raw.decode("utf-8", errors="replace").strip()
                except Exception:
                    skip_count += 1
                    continue

                if not line or line.startswith("#"):
                    continue

                parts = line.split(",")
                wall_clock = datetime.now(timezone.utc).isoformat()

                if len(parts) == 4:
                    f.write(f"{wall_clock},{parts[0]},{parts[1]},{parts[2]},{parts[3]}\n")
                    f.flush()
                    line_count += 1
                else:
                    skip_count += 1
                    f.write(f"# [SKIP] malformed line: {line!r}\n")
                    f.flush()

                if line_count % 300 == 0 and line_count > 0:
                    remaining_min = (deadline - time.monotonic()) / 60
                    print(f"  {line_count} lines logged, ~{remaining_min:.0f} min remaining")

        except KeyboardInterrupt:
            print("\nStopped early by user (Ctrl+C).")

    print(f"Done. {line_count} lines logged, {skip_count} skipped. Output: {out_path}")


if __name__ == "__main__":
    main()
