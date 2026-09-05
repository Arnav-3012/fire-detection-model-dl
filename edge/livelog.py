"""Phase 11 live-readings buffer: 1 Hz samples of mq2/mq135/p_fire for the dashboard.

Why this design (info.md 2.2 — the detection/fusion/alarm loop may NEVER be
slowed or risked by anything added for the dashboard):

- The main loop's ONLY cost is record(): a monotonic-clock comparison and,
  at most once per second, a SimpleQueue.put() of one small tuple. No file
  handle, no lock shared with file I/O, no serialization — put() on an
  unbounded SimpleQueue never blocks and never raises for capacity.
- ALL file I/O happens on a separate daemon thread that drains the queue
  into its own deque(maxlen=buffer_size) and rewrites one small JSON file.
  If the disk stalls, only this thread stalls; the queue simply grows a few
  entries (at 1 Hz, ~70 bytes each) until the disk recovers.
- The file is replaced atomically (write .tmp, os.replace) so the dashboard
  backend can never read a half-written file.
- This is a live-view window, not a record: buffer_size overwrites oldest.
  dispatch_log.jsonl / alert_feedback.csv / S3 remain the permanent record.
- 1 Hz, not per-frame: the Arduino streams at 1 Hz (edge/sensors.py), so
  30 Hz logging would be 30x the volume for zero information — p_fire is
  simply sampled at each tick.
"""

import json
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path

import yaml


class LiveLogWriter:
    """Owns the rolling live-readings file; safe to call from the edge loop.

    Failure contract (info.md 3.2): a write failure logs one warning and
    keeps trying on later ticks — it can never raise into, block, or slow
    the caller, and the thread never dies from a single bad write.
    """

    def __init__(self, config_path: str = "config.yaml") -> None:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)["live_log"]
        self._path = Path(cfg["path"])
        self._interval = float(cfg["sample_interval_seconds"])
        self._buffer: deque[dict] = deque(maxlen=int(cfg["buffer_size"]))
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        # Seeded in the past so the first loop iteration samples immediately.
        self._last_sample = time.monotonic() - self._interval
        self._warned = False
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="live-log-writer", daemon=True
        )

    def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def record(self, mq2: int | None, mq135: int | None, p_fire: float, level: str) -> None:
        """Sample the current readings if the 1s interval has elapsed.

        Called every frame (~30 FPS) but enqueues at most once per interval,
        so the steady-state per-frame cost is one time.monotonic() compare.

        `level` (2026-09-04, dashboard live-health request): the fused
        SAFE/WATCH/WARNING/CRITICAL verdict, already computed by fuse() on
        this same frame in edge/main.py — passed in as a plain string, not
        recomputed here, so this module never duplicates fusion logic (the
        one-fusion-implementation rule info.md holds edge/fusion.py to).
        Free to include: it costs nothing beyond one more dict key on a
        sample this loop already builds every second.
        """
        now = time.monotonic()
        if now - self._last_sample < self._interval:
            return
        self._last_sample = now
        self._queue.put(
            {"timestamp": time.time(), "mq2": mq2, "mq135": mq135,
             "p_fire": round(float(p_fire), 4), "level": level}
        )

    def _run(self) -> None:
        """Drain the queue into the rolling buffer; rewrite the file per sample.

        get(timeout=1) doubles as the idle heartbeat so stop() is honored
        within a second even when the edge loop has gone quiet.
        """
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            self._buffer.append(item)
            # Drain any backlog (e.g. after a disk stall) before writing once.
            while True:
                try:
                    self._buffer.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            self._write()

    def _write(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(list(self._buffer)))
            os.replace(tmp, self._path)  # atomic: readers never see a partial file
            self._warned = False
        except OSError as exc:
            if not self._warned:  # once per failure streak, not once per second
                self._warned = True
                print(f"WARNING: live-log write failed ({exc}) — dashboard live "
                      f"chart will be stale; detection loop unaffected")
