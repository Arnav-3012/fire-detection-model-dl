"""Stage 3 offline verification: WiFi transport presents the same surface
as SensorReader, validates payloads identically, and goes None when stale.

Runs a real ingest server on a loopback port and POSTs to it. No board, no
network hardware. Run from the repo root:

    python3 eval/verify_stage3_transport.py
"""
import json
import sys
import time
import types
import urllib.request
import urllib.error

sys.path.insert(0, "edge")
for m in ("serial",):
    try:
        __import__(m)
    except ImportError:
        sys.modules[m] = types.ModuleType(m)

from sensors import SensorReader
from wifi_source import WifiSensorSource

PORT = 8099
OK_PAYLOAD = {
    "mq2": 245, "mq135": 60, "state": "ok",
    "baseline_mq2": 180, "warn_mq2": 237.5, "danger_mq2": 306.2,
    "baseline_mq135": 50, "warn_mq135": 98.7, "danger_mq135": 127.3,
}

fails = 0
def check(desc, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {desc:<58} -> {got}")
    if not ok:
        print(f"        expected {want}")

def post(payload, path="/ingest"):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code

# --- interface parity: the whole premise of the stage ---------------
print("=== INTERFACE PARITY with SensorReader ===")
surface = ("start", "stop", "latest", "thresholds",
           "first_reading_monotonic", "set_alarm")
for name in surface:
    check(f"WifiSensorSource.{name}() exists",
          callable(getattr(WifiSensorSource, name, None)), True)
missing = [n for n in surface if not hasattr(SensorReader, n)]
check("...and every one of those exists on SensorReader too", missing, [])

# --- boot a real server ---------------------------------------------
src = WifiSensorSource.__new__(WifiSensorSource)
import threading
src._lock = threading.Lock()
src._host, src._port = "127.0.0.1", PORT
src._stale_seconds = 1.0
src._mq2 = src._mq135 = src._state = None
src._thresholds = {}
src._last_post_monotonic = src._first_reading_monotonic = None
src._stale_announced = False
src._server = src._thread = None
src.start()
time.sleep(0.3)

print("\n=== HAPPY PATH ===")
check("valid POST accepted", post(OK_PAYLOAD), 200)
check("latest() matches the reading",
      src.latest(), {"mq2": 245, "mq135": 60, "state": "ok"})
check("thresholds() carries all six",
      src.thresholds(), {"baseline_mq2": 180.0, "warn_mq2": 237.5,
                         "danger_mq2": 306.2, "baseline_mq135": 50.0,
                         "warn_mq135": 98.7, "danger_mq135": 127.3})
check("first_reading_monotonic() set", src.first_reading_monotonic() is not None, True)
check("GAS_HIGH round-trips",
      (post({**OK_PAYLOAD, "mq2": 900, "state": "GAS_HIGH"}), src.latest()["state"]),
      (200, "GAS_HIGH"))

print("\n=== VALIDATION mirrors sensors._parse_line ===")
check("unknown state rejected", post({**OK_PAYLOAD, "state": "BOGUS"}), 422)
check("missing mq2 rejected", post({"mq135": 60, "state": "ok"}), 422)
check("non-numeric mq2 rejected", post({**OK_PAYLOAD, "mq2": "abc"}), 422)
check("unknown path 404s", post(OK_PAYLOAD, "/nope"), 404)
check("2-field (no state) accepted, state None",
      (post({"mq2": 145, "mq135": 42}), src.latest()["state"]), (200, None))
post({**OK_PAYLOAD, "warn_mq2": None})
check("partial thresholds ignored, previous kept",
      src.thresholds()["warn_mq2"], 237.5)

print("\n=== STALENESS: the new failure mode HTTP introduces ===")
post(OK_PAYLOAD)
check("fresh reading is live", src.latest()["mq2"], 245)
time.sleep(1.3)  # exceed the 1.0s stale window
check("STALE -> latest() all None (=> gas_high False)",
      src.latest(), {"mq2": None, "mq135": None, "state": None})
check("thresholds() NOT cleared by staleness (config, not a reading)",
      src.thresholds()["warn_mq2"], 237.5)
check("recovery restores readings",
      (post(OK_PAYLOAD), src.latest()["mq2"]), (200, 245))

# ---------------------------------------------------------------------
# MILESTONE 3: link death DURING an active gas alarm.
#
# Hardware-verified 2026-09-23 (gas triggered over WiFi, then the laptop's
# WiFi killed mid-alarm: the board's buzzer kept sounding throughout and
# the edge loop degraded cleanly). This encodes that scenario so a future
# change cannot silently break it.
#
# The property under test is NOT "the buzzer keeps sounding" -- this host
# cannot observe the buzzer, and that is exactly the point: the board owns
# it outright and no host-side code participates. What IS testable here is
# the host's half of the contract: a dead link must degrade gas_high to
# False (never latch it True on stale data), must not crash, and must
# recover cleanly.
# ---------------------------------------------------------------------
print("\n=== MILESTONE 3: link dies DURING an active GAS_HIGH ===")
GAS_PAYLOAD = {**OK_PAYLOAD, "mq2": 900, "mq135": 300, "state": "GAS_HIGH"}
post(GAS_PAYLOAD)
check("alarm active over the link", src.latest()["state"], "GAS_HIGH")
check("...and gas_high would be True", src.latest()["state"] == "GAS_HIGH", True)

time.sleep(1.3)  # link dies mid-alarm; exceed the stale window
stale = src.latest()
check("link dies mid-alarm -> readings None, NOT a latched GAS_HIGH",
      stale, {"mq2": None, "mq135": None, "state": None})
check("...so gas_high degrades to False (fail-safe, not fail-stuck)",
      stale["state"] == "GAS_HIGH", False)
check("thresholds survive the outage (board config, not a reading)",
      src.thresholds()["warn_mq2"], 237.5)

# The gas event may still be ongoing when the link returns -- the host
# must show the CURRENT state, not resume the pre-outage one.
post(GAS_PAYLOAD)
check("link returns mid-event -> live GAS_HIGH again", src.latest()["state"], "GAS_HIGH")
post(OK_PAYLOAD)
check("event ends -> back to ok, no stuck alarm", src.latest()["state"], "ok")

# A reading arriving DURING the stale window must be accepted normally:
# a brief outage must not require any reset or re-registration.
time.sleep(1.3)
check("stale again after silence", src.latest()["mq2"], None)
check("single POST fully recovers the source",
      (post(OK_PAYLOAD), src.latest()["mq2"]), (200, 245))

print("\n=== set_alarm is an inert no-op, never raises ===")
try:
    src.set_alarm(True); src.set_alarm(False)
    check("set_alarm(True/False) safe to call", True, True)
except Exception as exc:
    check("set_alarm(True/False) safe to call", f"raised {exc}", True)

src.stop()
print(f"\n{'ALL CHECKS PASSED' if not fails else str(fails)+' CHECK(S) FAILED'}")
sys.exit(1 if fails else 0)
