"""Record one labelled clip for the paper's test sessions (research-steps.md 4.2).

Reads the ESP32-CAM through the dashboard relay (same frames as live) and polls
the edge loop's sensor ingest at 1 Hz, so one clip yields video, frame
timestamps, gas readings and metadata.

Needs running: `uvicorn dashboard.backend.main:app --port 8001` and `python edge/main.py`.

    python scripts/record_session.py --session S01 --cls fire --category camphor_lit \
        --distance 1.5 --room balcony --light day --seconds 45 --note "sensor 0.5m, wind low"

Keys in the preview window: `e` = hazard starts now (stores event_start_ts), `q` = stop early.
"""
import argparse
import csv
import json
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import cv2

STREAM_URL = "http://127.0.0.1:8001/api/camera/stream"
INGEST_URL = "http://127.0.0.1:8002/ingest"
OUT_ROOT = Path("data/test_raw")
CLASSES = ("fire", "smoke", "neutral", "hazard_gas")


def poll_sensors(csv_path: Path, stop: threading.Event) -> None:
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["wall_ts", "mq2", "mq135", "state"])
        while not stop.is_set():
            t = time.time()
            try:
                with urllib.request.urlopen(INGEST_URL, timeout=1) as r:
                    latest = json.load(r)["latest"]
                w.writerow([f"{t:.3f}", latest["mq2"], latest["mq135"], latest["state"]])
            except Exception:
                w.writerow([f"{t:.3f}", "", "", "unreachable"])
            f.flush()
            stop.wait(max(0.0, 1.0 - (time.time() - t)))


def next_clip_id(out_dir: Path, prefix: str) -> str:
    n = len(list(out_dir.glob(f"{prefix}_c*.mp4"))) + 1
    return f"{prefix}_c{n:02d}"


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--session", required=True, help="S01.. for test sessions, T00.. for development")
    p.add_argument("--cls", required=True, choices=CLASSES)
    p.add_argument("--category", required=True)
    p.add_argument("--distance", required=True, type=float, help="camera-to-subject metres")
    p.add_argument("--room", required=True)
    p.add_argument("--light", required=True, help="day / night / lamp / dark")
    p.add_argument("--seconds", type=int, default=45)
    p.add_argument("--lux", type=float)
    p.add_argument("--note", default="")
    a = p.parse_args()

    out_dir = OUT_ROOT / a.session / a.cls / a.category
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_id = next_clip_id(out_dir, f"{a.session}_{a.cls}_{a.category}_d{a.distance:g}")
    base = out_dir / clip_id

    cap = cv2.VideoCapture(STREAM_URL)
    ok, frame = cap.read()
    if not ok:
        raise SystemExit(f"cannot read {STREAM_URL}: is the dashboard backend running with the camera relay?")
    h, w = frame.shape[:2]

    # MJPEG fps varies, so measure it over the first frames and also log every frame's timestamp.
    frames_f = open(f"{base}_frames.csv", "w", newline="")
    frames_w = csv.writer(frames_f)
    frames_w.writerow(["frame_idx", "wall_ts"])

    stop = threading.Event()
    sensor_thread = threading.Thread(target=poll_sensors, args=(Path(f"{base}_sensors.csv"), stop), daemon=True)
    sensor_thread.start()

    frames: list[tuple[float, object]] = []
    start_ts = time.time()
    event_ts = None
    print(f"recording {clip_id} for {a.seconds}s. 'e' = hazard starts, 'q' = stop")
    while time.time() - start_ts < a.seconds:
        ok, frame = cap.read()
        if not ok:
            break
        now = time.time()
        frames.append((now, frame))
        frames_w.writerow([len(frames) - 1, f"{now:.3f}"])
        view = frame.copy()
        cv2.putText(view, f"{clip_id}  {now - start_ts:4.1f}s  event={'SET' if event_ts else '-'}",
                    (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
        cv2.imshow("record_session", view)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("e") and event_ts is None:
            event_ts = now
            print(f"  event marked at +{now - start_ts:.1f}s")
        elif key == ord("q"):
            break
    end_ts = time.time()
    stop.set()
    cap.release()
    cv2.destroyAllWindows()
    frames_f.close()

    duration = max(end_ts - start_ts, 1e-6)
    fps = len(frames) / duration
    writer = cv2.VideoWriter(f"{base}.mp4", cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for _, f in frames:
        writer.write(f)
    writer.release()

    meta = {**vars(a), "clip_id": clip_id, "start_ts": start_ts, "event_start_ts": event_ts,
            "end_ts": end_ts, "fps": round(fps, 2), "n_frames": len(frames),
            "git_commit": git_commit(), "stream_url": STREAM_URL}
    Path(f"{base}.json").write_text(json.dumps(meta, indent=2))
    print(f"saved {base}.mp4  ({len(frames)} frames, {fps:.1f} fps, event={'set' if event_ts else 'NOT set'})")
    if a.cls in ("fire", "smoke", "hazard_gas") and event_ts is None:
        print("WARNING: hazard clip with no event marker; it can't be used for time-to-detection.")


if __name__ == "__main__":
    main()
