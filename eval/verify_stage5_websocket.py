"""Stage 5 offline verification: the /ws/live payload is IDENTICAL to
GET /api/live-sensors, and firmware thresholds override stale config.

The identity claim is the whole premise of the stage — it is what lets
LiveSensorChart.jsx be reused unchanged and makes falling back to polling
a one-line change. If the two ever drift, that promise silently breaks.

Run from the repo root:  python3 eval/verify_stage5_websocket.py
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

fails = 0
def check(desc, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {desc:<58} -> {got}")
    if not ok:
        print(f"        expected {want}")

# An OS-assigned free port, not a fixed one: a fixed port collides with a
# leftover listener from a previous crashed run and reports as "backend did
# not become ready", which looks like a code failure and is not.
import socket as _socket
_probe = _socket.socket()
_probe.bind(("127.0.0.1", 0))
PORT = _probe.getsockname()[1]
_probe.close()
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "dashboard.backend.main:app",
     "--port", str(PORT), "--log-level", "warning"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Poll for readiness rather than sleeping a fixed time: startup also opens
# the camera relay, whose connect time depends on whether a real board is
# configured and reachable.
for _ in range(60):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1):
            break
    except Exception:
        time.sleep(0.5)
else:
    print("backend did not become ready")
    proc.kill()
    out = proc.stdout.read() if proc.stdout else ""
    print(out[:2000])
    sys.exit(1)

try:
    print("=== REST endpoint still works (unchanged contract) ===")
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/live-sensors", timeout=5) as r:
        rest = json.load(r)
    check("GET /api/live-sensors responds", r.status, 200)
    check("payload has the documented keys",
          sorted(rest.keys()), ["ok", "readings", "reason", "thresholds"])
    check("thresholds carry all six values", len(rest["thresholds"]), 6)

    print("\n=== WebSocket pushes the SAME payload ===")
    try:
        from websockets.sync.client import connect
    except ImportError:
        print("  (websockets.sync unavailable — skipping live socket test)")
        raise SystemExit(1 if fails else 0)

    with connect(f"ws://127.0.0.1:{PORT}/ws/live", open_timeout=5) as ws:
        first = json.loads(ws.recv(timeout=5))
        check("sends immediately on connect (no blank first second)",
              sorted(first.keys()), ["ok", "readings", "reason", "thresholds"])
        check("WS payload keys IDENTICAL to REST",
              sorted(first.keys()), sorted(rest.keys()))
        check("WS thresholds IDENTICAL to REST",
              first["thresholds"], rest["thresholds"])
        check("WS ok flag matches REST", first["ok"], rest["ok"])

        t0 = time.time()
        second = json.loads(ws.recv(timeout=5))
        elapsed = time.time() - t0
        check("pushes again at ~1 Hz", 0.5 < elapsed < 2.0, True)
        check("second push has the same shape",
              sorted(second.keys()), sorted(first.keys()))

    print("\n=== firmware thresholds OVERRIDE stale config ===")
    # Regression for a real bug: the firmware names fields warn_mq2 while
    # the dashboard contract uses mq2_warn, so merging the raw firmware
    # dict ADDED six keys instead of replacing the stale six — the chart
    # would have kept drawing config.yaml's 10-bit Arduino-era lines while
    # appearing to update.
    th = rest["thresholds"]
    check("exactly six threshold keys (no duplicate naming)", len(th), 6)
    check("keys use the dashboard's contract naming",
          sorted(th.keys()),
          ["mq135_baseline", "mq135_danger", "mq135_warn",
           "mq2_baseline", "mq2_danger", "mq2_warn"])
    sidecar = _REPO / "data" / "live_sensors_thresholds.json"
    if sidecar.exists():
        live = json.loads(sidecar.read_text())
        check("mq2_warn comes from the FIRMWARE, not stale config",
              th["mq2_warn"], live["warn_mq2"])
        check("...and is NOT config.yaml's stale value",
              th["mq2_warn"] == 115.57, False)
    else:
        print("  (no firmware sidecar present — run edge/main.py to generate it)")

    print("\n=== many simultaneous clients ===")
    socks = [connect(f"ws://127.0.0.1:{PORT}/ws/live", open_timeout=5) for _ in range(5)]
    got = [json.loads(s.recv(timeout=5))["thresholds"] for s in socks]
    check("5 concurrent clients each receive a payload", len(got), 5)
    check("...and all agree on thresholds", all(g == got[0] for g in got), True)
    for s in socks:
        s.close()

    print("\n=== a client disconnecting does not disturb the server ===")
    with connect(f"ws://127.0.0.1:{PORT}/ws/live", open_timeout=5) as ws:
        json.loads(ws.recv(timeout=5))
    time.sleep(1.5)  # server notices the close mid-send
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5) as r:
        check("server healthy after an abrupt disconnect", r.status, 200)

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

print(f"\n{'ALL CHECKS PASSED' if not fails else str(fails)+' CHECK(S) FAILED'}")
sys.exit(1 if fails else 0)
