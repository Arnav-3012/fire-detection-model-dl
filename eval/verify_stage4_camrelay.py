"""Stage 4 offline verification: the relay satisfies cam_node.ino's
ONE-CLIENT limit while serving many consumers.

Runs a fake ESP32-CAM that emits cam_node.ino's exact multipart format AND
enforces its one-client-at-a-time behaviour, so the regression this stage
exists to prevent is actually reproduced rather than assumed.

Run from the repo root:  python3 eval/verify_stage4_camrelay.py
"""
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, "edge")
from camrelay import CameraRelay

fails = 0
def check(desc, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] {desc:<58} -> {got}")
    if not ok:
        print(f"        expected {want}")

# Minimal valid JPEG (SOI ... EOI), distinguishable per frame by a counter byte.
def fake_jpeg(n: int) -> bytes:
    return b"\xff\xd8\xff" + bytes([n % 256]) * 64 + b"\xff\xd9"


class FakeCam(threading.Thread):
    """Serves /stream in cam_node.ino's format, ONE client at a time."""
    daemon = True

    def __init__(self):
        super().__init__()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        # backlog=0: cam_node.ino is single-threaded and accepts the next
        # connection only once the current /stream client disconnects.
        # A larger backlog would let the OS queue (and partially serve)
        # a second client, which the real board cannot do.
        self.sock.listen(0)
        self.port = self.sock.getsockname()[1]
        self.stop_flag = threading.Event()
        self.concurrent = 0
        self.max_concurrent = 0
        self.connections = 0
        self.frame_n = 0
        self._lock = threading.Lock()

    def run(self):
        while not self.stop_flag.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with self._lock:
                self.connections += 1
                self.concurrent += 1
                self.max_concurrent = max(self.max_concurrent, self.concurrent)
            # Each connection is handled on its own thread so the
            # refusal path below is exercised WHILE the first client is
            # still being served -- which is the situation the real board
            # is in. The refusal itself is what models cam_node.ino:
            # single-threaded firmware answers nobody while
            # handle_stream() holds loop(), so a second client gets its
            # connection closed without a response.
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        with self._lock:
            busy = self.concurrent > 1
        try:
            if busy:
                conn.close()
                return
            self._serve(conn)
        except OSError:
            pass
        finally:
            with self._lock:
                self.concurrent -= 1
            try:
                conn.close()
            except OSError:
                pass

    def _serve(self, conn):
        conn.recv(1024)  # request line
        conn.sendall(b"HTTP/1.1 200 OK\r\n"
                     b"Content-Type: multipart/x-mixed-replace;boundary=frame\r\n\r\n")
        # THE CONSTRAINT: like cam_node.ino, this occupies the server for
        # the life of the connection. A second client gets nothing until
        # this returns.
        while not self.stop_flag.is_set():
            self.frame_n += 1
            jpg = fake_jpeg(self.frame_n)
            conn.sendall(b"--frame\r\nContent-Type: image/jpeg\r\n"
                         + f"Content-Length: {len(jpg)}\r\n\r\n".encode()
                         + jpg + b"\r\n")
            time.sleep(0.05)


cam = FakeCam()
cam.start()
url = f"http://127.0.0.1:{cam.port}/stream"
print(f"fake ESP32-CAM on {url}\n")

print("=== THE PROBLEM Stage 4 exists to fix ===")
# Two DIRECT consumers: the second is starved by the first, as on real hardware.
def direct_reader(results, hold):
    """A direct consumer, like edge/main.py holding /stream today.

    Records BOTH outcomes explicitly: a frame received, or the error the
    board's refusal produces. The refusal raises rather than returning an
    empty stream, so counting frames alone would silently miss it.
    """
    results["frames"] = 0
    results["error"] = None
    try:
        r = urllib.request.urlopen(url, timeout=1.5)
        deadline = time.time() + 1.5
        while time.time() < deadline:
            line = r.readline()
            if not line:
                break
            if line.strip().lower().startswith(b"content-length:"):
                results["frames"] += 1
                break
        if hold:
            time.sleep(1.5)   # keep the connection, like the edge loop
        r.close()
    except Exception as exc:
        results["error"] = type(exc).__name__

first, second = {}, {}
a = threading.Thread(target=direct_reader, args=(first, True), daemon=True)
a.start(); time.sleep(0.4)          # let A take the single slot
b = threading.Thread(target=direct_reader, args=(second, False), daemon=True)
b.start(); b.join(timeout=2.0)
check("1st direct consumer is served", first["frames"] >= 1, True)
check("2nd DIRECT consumer gets NO frame (the real constraint)",
      second["frames"], 0)
check("...it is actively refused while the board is busy",
      second["error"] is not None, True)
a.join(timeout=3.0)
time.sleep(0.3)

print("\n=== THE FIX: one upstream connection, many consumers ===")
before = cam.connections
relay = CameraRelay(url, stale_seconds=2.0)
relay.start()
deadline = time.time() + 5
while time.time() < deadline and not relay.is_live():
    time.sleep(0.05)
check("relay receives frames", relay.is_live(), True)

jpeg, age = relay.latest_jpeg()
check("frame is valid JPEG (SOI/EOI preserved)",
      jpeg is not None and jpeg[:3] == b"\xff\xd8\xff" and jpeg[-2:] == b"\xff\xd9", True)
check("frame age is fresh", age is not None and age < 1.0, True)

# Many simultaneous consumers, all served from the slot.
results = []
def consumer():
    j, _ = relay.latest_jpeg()
    results.append(j is not None and j[:3] == b"\xff\xd8\xff")
ts = [threading.Thread(target=consumer) for _ in range(10)]
[t.start() for t in ts]; [t.join() for t in ts]
check("10 simultaneous consumers all get a frame", (len(results), all(results)), (10, True))
check("...while the relay holds exactly ONE upstream connection",
      cam.connections - before, 1)

print("\n=== frames advance (live, not a frozen slot) ===")
first, _ = relay.latest_jpeg()
nxt = relay.wait_for_frame(timeout=2.0)
check("wait_for_frame() returns the NEXT frame", nxt is not None, True)
time.sleep(0.2)
later, _ = relay.latest_jpeg()
check("slot advances over time", first != later, True)

print("\n=== no re-encoding: bytes are passed through verbatim ===")
j, _ = relay.latest_jpeg()
check("payload matches the fake cam's exact frame bytes",
      j in [fake_jpeg(n) for n in range(max(1, cam.frame_n - 4), cam.frame_n + 2)], True)

print("\n=== STALENESS: a frozen frame must not look live ===")
cam.stop_flag.set()
time.sleep(2.5)  # exceed the 2.0s stale window
check("upstream stops -> is_live() False", relay.is_live(), False)
j, age = relay.latest_jpeg()
check("...but the last frame is still retrievable, with its age",
      j is not None and age is not None and age > 2.0, True)
st = relay.stats()
check("stats() reports not-live", st["live"], False)
check("stats() counted frames", st["frames"] > 0, True)

relay.stop()
cam.stop_flag.set()
try:
    cam.sock.close()
except OSError:
    pass

print(f"\n{'ALL CHECKS PASSED' if not fails else str(fails)+' CHECK(S) FAILED'}")
sys.exit(1 if fails else 0)
