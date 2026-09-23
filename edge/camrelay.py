"""Stage 4 camera relay: one upstream connection, many consumers.

THE PROBLEM. arduino/cam_node/cam_node.ino's /stream handler holds loop()
for the entire life of a connection, so the board serves exactly ONE
stream client at a time and cannot answer anything else -- not /capture,
not a health check -- until that client disconnects. Its own source
comment says so. In practice that means edge/main.py holding the stream
locks the dashboard out of the camera completely, and vice versa.

THE FIX. A single thread here owns the one upstream connection and keeps
the newest JPEG in a lock-guarded slot. Every consumer reads the slot
instead of the board, so the one-client limit is satisfied permanently no
matter how many readers there are. This is the standard relay/fan-out
pattern, chosen over the alternative of rewriting the firmware for
multi-client FreeRTOS serving -- high-risk surgery on a working camera
path, for no gain the relay does not already provide.

NO RE-ENCODING. Frames are passed through as the exact JPEG bytes the
board sent. Decoding to a numpy array and re-encoding per consumer would
cost CPU, add latency and lose quality for nothing: consumers that want
pixels (the vision loop) decode once themselves, and consumers that want
bytes (an MJPEG viewer) want precisely these bytes.

STALENESS, as in wifi_source.py and for the same reason: a frozen last
frame must not masquerade as a live camera. latest_jpeg() reports the
frame's age so callers can decide, and is_live() applies the threshold.

FAILURE CONTRACT (info.md 3.2): the upstream connection dying logs one
warning and retries with backoff forever. It never raises into a
consumer, never blocks one, and the thread never dies from a bad frame.
A dead camera degrades consumers to "no frame available", which is a
state they must handle anyway (the board reboots, WiFi drops, someone
unplugs it).
"""

import threading
import time
import urllib.error
import urllib.request

# Upstream read timeout. Generous relative to the board's ~4-8 fps
# (measured, logs.md Phase 13a-2) so a slow frame is not mistaken for a
# dead connection, but bounded so a genuinely wedged socket is noticed.
UPSTREAM_TIMEOUT_SECONDS = 10.0

# Backoff between reconnect attempts. Matches sensors.py's serial
# reconnect cadence -- same intent: long enough not to spam, short enough
# that a board reboot is picked up within a few seconds.
RECONNECT_DELAY_SECONDS = 3.0

# A frame older than this is stale. ~3x the board's slowest observed
# frame interval, so normal jitter never trips it.
DEFAULT_STALE_SECONDS = 5.0

# Hard cap on one JPEG. The board sends QVGA/VGA frames of tens of KB; a
# multi-MB Content-Length means a corrupt header, and reading it would be
# an unbounded allocation driven by remote input.
MAX_FRAME_BYTES = 2 * 1024 * 1024


class CameraRelay:
    """Holds the single upstream MJPEG connection; serves the newest frame.

    Consumers call latest_jpeg() (bytes, for an MJPEG response) or
    latest_frame_age() / is_live(). Nothing here decodes JPEG -- callers
    that need pixels do that themselves, once.
    """

    def __init__(self, url: str, stale_seconds: float = DEFAULT_STALE_SECONDS) -> None:
        self._url = url
        self._stale_seconds = float(stale_seconds)

        self._lock = threading.Lock()
        self._jpeg: bytes | None = None
        self._received_monotonic: float | None = None
        self._frame_count = 0
        self._connected = False

        # Signalled on every new frame so a consumer can wait for the NEXT
        # frame instead of polling the slot -- an MJPEG response that
        # polls would either burn CPU or add latency.
        self._new_frame = threading.Condition(self._lock)

        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._read_loop, name="camera-relay", daemon=True
        )

    # --- lifecycle ------------------------------------------------------

    def start(self) -> None:
        """Begin relaying. Never raises: an unreachable camera is a
        logged warning and a retry loop, not a startup failure."""
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # --- consumer surface -----------------------------------------------

    def latest_jpeg(self) -> tuple[bytes | None, float | None]:
        """(jpeg_bytes, age_seconds), or (None, None) before any frame.

        Returns the frame even when stale, with its age, rather than
        hiding it: a viewer showing a visibly old frame plus a staleness
        badge is more useful than a blank panel, and the caller has the
        age to decide. is_live() exists for callers that just want the
        boolean.
        """
        with self._lock:
            if self._jpeg is None or self._received_monotonic is None:
                return None, None
            return self._jpeg, time.monotonic() - self._received_monotonic

    def wait_for_frame(self, timeout: float) -> bytes | None:
        """Block until the NEXT frame arrives, or timeout. Used by the
        MJPEG response so it emits at the upstream frame rate without
        polling or duplicating frames."""
        with self._new_frame:
            if not self._new_frame.wait(timeout):
                return None
            return self._jpeg

    def is_live(self) -> bool:
        """True when a frame arrived within stale_seconds."""
        with self._lock:
            if self._received_monotonic is None:
                return False
            return (time.monotonic() - self._received_monotonic) <= self._stale_seconds

    def stats(self) -> dict:
        """Diagnostics for a health endpoint."""
        with self._lock:
            age = (
                time.monotonic() - self._received_monotonic
                if self._received_monotonic is not None
                else None
            )
            return {
                "url": self._url,
                "connected": self._connected,
                "frames": self._frame_count,
                "age_seconds": round(age, 2) if age is not None else None,
                "live": age is not None and age <= self._stale_seconds,
            }

    # --- internals ------------------------------------------------------

    def _publish(self, jpeg: bytes) -> None:
        with self._new_frame:
            self._jpeg = jpeg
            self._received_monotonic = time.monotonic()
            self._frame_count += 1
            self._new_frame.notify_all()

    def _read_loop(self) -> None:
        """Connect-read-reconnect forever, mirroring sensors.py's two
        failure tiers: a bad FRAME is skipped, a dead CONNECTION logs one
        warning and retries."""
        while not self._stop.is_set():
            try:
                req = urllib.request.Request(self._url)
                with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT_SECONDS) as resp:
                    with self._lock:
                        self._connected = True
                    print(f"Camera relay connected to {self._url}")
                    self._consume(resp)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                pass
            finally:
                with self._lock:
                    was = self._connected
                    self._connected = False
                if was:
                    print(
                        f"WARNING: camera relay lost {self._url}; retrying in "
                        f"{RECONNECT_DELAY_SECONDS:.0f}s (consumers see stale/no frame; "
                        f"detection continues on last-known behaviour)"
                    )
            if not self._stop.is_set():
                time.sleep(RECONNECT_DELAY_SECONDS)

    def _consume(self, resp) -> None:
        """Parse multipart/x-mixed-replace from cam_node.ino.

        The board emits, per frame:
            --frame\\r\\n
            Content-Type: image/jpeg\\r\\n
            Content-Length: <n>\\r\\n
            \\r\\n
            <n bytes of JPEG>\\r\\n

        Content-Length is present on every part (cam_node.ino:386), so
        the body is read by length rather than by scanning for the next
        boundary -- exact, and it cannot be fooled by boundary-like bytes
        inside JPEG data.
        """
        while not self._stop.is_set():
            length = None
            # Read part headers until the blank line.
            while not self._stop.is_set():
                line = resp.readline()
                if not line:
                    return  # upstream closed
                s = line.strip()
                if not s:
                    break  # end of headers
                low = s.lower()
                if low.startswith(b"content-length:"):
                    try:
                        length = int(s.split(b":", 1)[1])
                    except ValueError:
                        length = None

            if length is None or length <= 0 or length > MAX_FRAME_BYTES:
                # Unparseable part: skip it rather than killing the
                # connection. One bad frame must not drop the stream.
                continue

            jpeg = resp.read(length)
            if len(jpeg) != length:
                return  # short read: connection is dying, reconnect
            self._publish(jpeg)
