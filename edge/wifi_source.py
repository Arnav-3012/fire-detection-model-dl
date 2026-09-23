"""Stage 3 WiFi transport: sensor readings over HTTP instead of USB serial.

DROP-IN for SensorReader. Exposes the identical surface — start(), stop(),
latest(), thresholds(), first_reading_monotonic(), set_alarm() — so
edge/main.py swaps transports with one if/else and nothing downstream
changes. latest() returns the same {"mq2", "mq135", "state"} dict and
thresholds() the same six firmware-published keys.

WHY THE INGEST SERVER LIVES HERE, IN THE EDGE LOOP (2026-09-23 decision,
option B). The obvious place was dashboard/backend/main.py, but that
process is (a) documented as deliberately read-only — "no fusion, no
decision logic, no writes" — and (b) an OPTIONAL dev-time process. Routing
sensor data through it would make the dashboard a hard dependency of the
DETECTOR: no dashboard, no gas readings, no gas verdict. That inverts the
project's core safety claim (fusion.py: detection is "No model, no LLM, no
network"). The edge loop already owns detection, so it owns its own
ingest. The dashboard keeps reading data/live_sensors.json exactly as
before — Stage 3 changes nothing in dashboard/.

THREADING follows livelog.py's established pattern: all work on a daemon
thread, the main loop's only cost is a lock-guarded dict read in latest().
That is strictly CHEAPER than the serial path it replaces (which parsed a
CSV line per read), so info.md 2.2's "the loop may never be slowed" holds
by construction.

STALENESS is the one genuinely new failure mode. Serial detects a dead
board implicitly — the port errors, readings stop. HTTP does not: if the
board loses power mid-run, the last POST just sits in memory and would
look like a healthy, frozen reading forever. A stale reading feeding
gas_high is a SAFETY bug (it could hold gas_high=True on stale data, or
mask a real event), so latest() returns None readings once the last POST
is older than stale_seconds — exactly the "no data yet" state main.py
already handles by forcing gas_high False.

WHAT THIS TRANSPORT DOES *NOT* CARRY: the alarm. The board owns its buzzer
outright (sensor_esp32_node.ino has no Serial.read() — see
sensors.set_alarm's docstring), and sounds it autonomously off its own
GAS_HIGH. So a total WiFi outage degrades telemetry, the dashboard and the
agent notification — never the local alarm. That is what makes this stage
low-risk: the network was never on the safety path and still isn't.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml

from sensors import THRESHOLD_FIELDS, VALID_STATES

# Bound on one request body. A legitimate payload is ~200 bytes; this is
# generous enough for added fields but small enough that a malformed or
# hostile Content-Length cannot make the handler allocate freely.
MAX_BODY_BYTES = 8192


class WifiSensorSource:
    """HTTP ingest endpoint presenting itself as a SensorReader.

    The board POSTs one JSON reading per second to /ingest. Everything
    the serial line carried is carried here: mq2, mq135, state, and the
    six live firmware thresholds.
    """

    def __init__(self, config_path: str = "config.yaml") -> None:
        with open(config_path) as f:
            sensors = yaml.safe_load(f)["sensors"]
        self._port: int = int(sensors.get("ingest_port", 8002))
        self._host: str = str(sensors.get("ingest_host", "0.0.0.0"))
        # How long a reading stays trustworthy. Default 5s = 5 missed
        # 1 Hz POSTs, loose enough to ride out normal WiFi jitter and a
        # retry, tight enough that a dead board is noticed within one
        # fusion cycle rather than never.
        self._stale_seconds: float = float(sensors.get("ingest_stale_seconds", 5.0))

        # Same guarantee as SensorReader's _lock: the pair (plus state)
        # is published atomically, so a reader can never pair mq2 from
        # one POST with mq135 from another.
        self._lock = threading.Lock()
        self._mq2: int | None = None
        self._mq135: int | None = None
        self._state: str | None = None
        self._thresholds: dict[str, float] = {}
        self._last_post_monotonic: float | None = None
        self._first_reading_monotonic: float | None = None

        # Counters for the once-only staleness log; a 30 FPS loop must
        # not print a warning per frame while the board is down.
        self._stale_announced = False

        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # --- SensorReader surface -------------------------------------------

    def start(self) -> None:
        """Bind and serve on a daemon thread. Never raises on a bind
        failure — per info.md 3.2 a broken transport degrades to None
        readings (vision keeps running), it does not stop the edge loop."""
        try:
            self._server = _make_server(self._host, self._port, self)
        except OSError as exc:
            print(
                f"WARNING: WiFi ingest could not bind {self._host}:{self._port} "
                f"({exc}); continuing with NO gas readings — vision detection "
                f"unaffected. Is another edge loop already running?"
            )
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="wifi-ingest", daemon=True
        )
        self._thread.start()
        print(f"WiFi ingest listening on http://{self._host}:{self._port}/ingest")

    def stop(self) -> None:
        """Orderly shutdown (the thread is a daemon and would die with
        the process anyway — this exists for tests and clean restarts,
        matching SensorReader.stop's contract)."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def latest(self) -> dict[str, int | str | None]:
        """Most recent POSTed reading, or all-None when stale/absent.

        Identical shape and contract to SensorReader.latest(). Returning
        None on staleness is deliberate: main.py already treats None as
        "no data yet -> gas_high False", so a dead board degrades along
        a path that is already tested rather than a new one.
        """
        with self._lock:
            if self._is_stale():
                return {"mq2": None, "mq135": None, "state": None}
            return {"mq2": self._mq2, "mq135": self._mq135, "state": self._state}

    def thresholds(self) -> dict[str, float]:
        """The six firmware-published thresholds, or {} if none yet.

        NOT cleared on staleness, unlike latest(): these describe how the
        board is configured, not what it is currently reading. The
        dashboard drawing a slightly old threshold line is correct; the
        fusion path drawing a stale READING is not.
        """
        with self._lock:
            return dict(self._thresholds)

    def first_reading_monotonic(self) -> float | None:
        """time.monotonic() of the first valid POST, None if none yet.

        Only the FALLBACK warm-up path in main.py consumes this (the
        firmware path uses the board's own state), but it is part of the
        SensorReader surface so it is implemented faithfully.
        """
        with self._lock:
            return self._first_reading_monotonic

    def set_alarm(self, on: bool) -> None:
        """No-op. Present only to complete the SensorReader surface.

        There is no reverse channel here by design, and none is needed:
        the board owns its buzzer and sounds it autonomously off its own
        GAS_HIGH state (sensor_esp32_node.ino has no Serial.read()). The
        serial set_alarm() is equally inert against this firmware — see
        its docstring — so this transport removes nothing that worked.
        Silent rather than logging: main.py calls it on every alarm
        transition, and a warning there would be noise about a
        non-problem.
        """

    # --- internals ------------------------------------------------------

    def _is_stale(self) -> bool:
        """True when the last POST is too old to trust. Caller holds the lock."""
        if self._last_post_monotonic is None:
            return True
        return (time.monotonic() - self._last_post_monotonic) > self._stale_seconds

    def _ingest(self, payload: dict) -> bool:
        """Validate and store one POSTed reading. Returns False if rejected.

        Validation mirrors sensors._parse_line exactly, for the same
        reasons: an unknown state string means firmware this code does
        not understand, so the readings are not trustworthy either, and
        a partial threshold set is ignored rather than half-applied.
        """
        try:
            mq2 = int(float(payload["mq2"]))
            mq135 = int(float(payload["mq135"]))
        except (KeyError, TypeError, ValueError):
            return False

        state = payload.get("state")
        if state is not None:
            if not isinstance(state, str) or state not in VALID_STATES:
                return False

        thresholds = None
        try:
            if all(k in payload for k in THRESHOLD_FIELDS):
                thresholds = {k: float(payload[k]) for k in THRESHOLD_FIELDS}
        except (TypeError, ValueError):
            thresholds = None

        now = time.monotonic()
        with self._lock:
            was_stale = self._is_stale() and self._last_post_monotonic is not None
            self._mq2 = mq2
            self._mq135 = mq135
            self._state = state
            if thresholds is not None:
                self._thresholds = thresholds
            self._last_post_monotonic = now
            if self._first_reading_monotonic is None:
                self._first_reading_monotonic = now
            recovered = was_stale and self._stale_announced
            if recovered:
                self._stale_announced = False
        if recovered:
            print("*** SENSOR TRANSPORT RECOVERED — readings arriving again ***")
        return True

    def note_stale_once(self) -> None:
        """Log the first time readings go stale, then stay quiet.

        Called from main.py's status path rather than a timer thread so
        there is no second thread to reason about; the latch makes it
        safe to call at 30 FPS.
        """
        with self._lock:
            if self._last_post_monotonic is None or not self._is_stale():
                return
            if self._stale_announced:
                return
            self._stale_announced = True
            age = time.monotonic() - self._last_post_monotonic
        print(
            f"*** WARNING: no sensor POST for {age:.1f}s (stale after "
            f"{self._stale_seconds:.0f}s) — gas readings now None, gas_high "
            f"forced False. Vision detection unaffected; the BOARD's own "
            f"buzzer is independent of this link. ***"
        )


def _make_server(host: str, port: int, source: WifiSensorSource) -> ThreadingHTTPServer:
    """Build the ingest server bound to `source`."""

    class _Handler(BaseHTTPRequestHandler):
        # Threading so one slow/half-open client cannot block the next
        # POST. Readings are 1 Hz and tiny, so this costs nothing.
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            if self.path.rstrip("/") not in ("/ingest", "/api/sensor-ingest"):
                self._reply(404, {"ok": False, "error": "unknown path"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self._reply(400, {"ok": False, "error": "bad Content-Length"})
                return
            if length <= 0 or length > MAX_BODY_BYTES:
                self._reply(400, {"ok": False, "error": "bad body size"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (OSError, ValueError):
                self._reply(400, {"ok": False, "error": "bad JSON"})
                return
            if not isinstance(payload, dict) or not source._ingest(payload):
                self._reply(422, {"ok": False, "error": "rejected reading"})
                return
            self._reply(200, {"ok": True})

        def do_GET(self) -> None:  # noqa: N802
            """Health/debug view of what the loop currently sees."""
            if self.path.rstrip("/") != "/ingest":
                self._reply(404, {"ok": False, "error": "unknown path"})
                return
            self._reply(200, {"ok": True, "latest": source.latest(),
                              "thresholds": source.thresholds()})

        def _reply(self, code: int, body: dict) -> None:
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args) -> None:
            """Silence per-request logging — at 1 Hz it would bury the
            edge loop's own status line, which is the thing worth reading."""

    return ThreadingHTTPServer((host, port), _Handler)
