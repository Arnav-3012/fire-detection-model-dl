"""Day 6 SensorReader: background serial reader for the Arduino MQ node.

Plan.md's Day 6 prompt, adjusted for the DHT22 cut (Phase 0g) exactly as
every other file already is: arduino/sensor_node.ino streams a two-field
"mq2,mq135" CSV line once per second at 9600 baud, and (since Phase 7)
accepts a single alarm command byte — see set_alarm(). There is
no temp/humidity parsing and no temp_rate computation here — not stubbed,
removed: with DHT22 cut there is no temperature signal to rate-limit, and
dead code pretending otherwise would be exactly the kind of silent
placeholder this project keeps getting burned by (see logs.md: both
sensor_node.ino and this very file were referenced for days before anyone
noticed they'd never been written).

Failure contract (info.md 3.2): serial problems log a warning and the
loop continues with last-known values — nothing here may ever crash or
block the vision loop, and the reader thread must never die from one
malformed line.
"""

import threading
import time

import serial
import yaml

# The Uno auto-resets when its port is opened; opening and reading
# immediately yields nothing. 3s (not 2s) because calibrate_mq.py's 2s
# settle produced a real all-zero calibration run (logs.md Phase 6
# addendum, 2026-08-31) — this number is a measured lesson, not a guess.
SERIAL_SETTLE_SECONDS = 3.0

# How long the reader sleeps after a serial-level failure before trying
# to reopen. Long enough not to spam warnings, short enough that a USB
# replug (the observed real-world fix for a stuck board) is picked up
# within a few seconds.
RECONNECT_DELAY_SECONDS = 3.0

# Alarm command bytes, fixed by arduino/sensor_node/sensor_node.ino
# (plan.md Day 6 spec: 'A' = alarm on, 'S' = safe). Constants here, NOT
# config.yaml: changing them requires reflashing the firmware, so putting
# them in config would falsely advertise them as tunables — editing the
# yaml alone would silently break the alarm.
ALARM_ON_BYTE = b"A"
ALARM_OFF_BYTE = b"S"


class SensorReader:
    """Reads the Arduino's CSV stream on a daemon thread.

    A daemon thread (not inline reads in the main loop) because the
    Arduino emits one line per second while the vision loop runs at
    ~30 FPS — blocking the loop on readline() would cut frame rate 30x.
    The vision loop instead calls latest() and gets whatever the most
    recent parse produced, which is at most ~1s stale: fine, because the
    MQ signal itself changes on multi-second timescales.
    """

    def __init__(self, config_path: str = "config.yaml") -> None:
        with open(config_path) as f:
            sensors = yaml.safe_load(f)["sensors"]
        self._port: str = sensors["serial_port"]
        self._baud: int = sensors["baud"]

        # Last-known values, None until the first valid line arrives.
        # Guarded by a lock only for atomicity of the pair — a reading
        # split across two updates would pair mq2 from one second with
        # mq135 from another.
        self._lock = threading.Lock()
        self._mq2: int | None = None
        self._mq135: int | None = None

        # time.monotonic() of the FIRST valid parsed line, None until then.
        # main.py's gas warm-up gate anchors to this, not process start:
        # the MQ heaters only begin settling once the board is actually
        # powered and talking, and a late USB plug-in must not shorten
        # the gate.
        self._first_reading_monotonic: float | None = None

        # Live serial handle, owned by the reader thread, shared with
        # set_alarm(). A SEPARATE lock from _lock: this one guards the
        # handle reference against the reconnect loop swapping/closing it
        # mid-write. readline() deliberately runs OUTSIDE it (it blocks up
        # to the 2s timeout; holding the lock there would stall every
        # alarm write for up to 2s — exactly the coupling info.md 2.2
        # forbids). One thread reading + one thread writing on the same
        # pyserial object is safe without a lock: on POSIX, read() and
        # write() are independent syscalls on a full-duplex fd — the
        # documented-unsafe patterns are two writers, or close() under a
        # live call, and the lock exists for that second case only.
        self._port_lock = threading.Lock()
        self._serial: serial.Serial | None = None

        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._read_loop, name="sensor-reader", daemon=True
        )

    def start(self) -> None:
        """Start the reader thread. Never raises on serial failure —
        per info.md 3.2 a missing/stuck Arduino degrades to last-known
        (here: None) values rather than stopping the edge loop."""
        self._thread.start()

    def stop(self) -> None:
        """Signal the thread to exit (it also dies with the process,
        being a daemon — this exists for orderly shutdown in tests)."""
        self._stop.set()

    def latest(self) -> dict[str, int | None]:
        """Most recent raw ADC readings; values are None before the
        first valid line (caller decides how to treat 'no data yet' —
        fusion's gas_high must not fire on an absent sensor)."""
        with self._lock:
            return {"mq2": self._mq2, "mq135": self._mq135}

    def first_reading_monotonic(self) -> float | None:
        """time.monotonic() of the first valid line, None if none yet.

        Exists solely so main.py's gas warm-up gate can measure "time
        since the sensors actually started talking" — see __init__'s
        comment on why process start is the wrong anchor.
        """
        with self._lock:
            return self._first_reading_monotonic

    def set_alarm(self, on: bool) -> None:
        """Fire-and-forget alarm byte, written on the CALLER's thread.

        Deliberately NOT routed through the reader thread or any queue:
        info.md 2.2 makes the local alarm the step nothing may delay, so
        the write path and the read path must not share a failure mode —
        a wedged readline() cannot stall this call, and this call cannot
        stall reading. Same Serial object, same port: opening a second
        connection to the port would conflict (and re-opening resets the
        Uno). Safe against the concurrent readline() because one reader +
        one writer on a full-duplex fd is the documented-safe pyserial
        pattern; _port_lock only guards against the reconnect loop
        swapping the handle mid-write (see __init__).

        A dead/absent port logs loudly and returns — it must not crash
        the edge loop (info.md 3.2), and there is genuinely nothing to
        write to; the reconnect loop is already working on recovery.
        """
        byte = ALARM_ON_BYTE if on else ALARM_OFF_BYTE
        with self._port_lock:
            if self._serial is None:
                print(
                    f"WARNING: alarm byte {byte!r} NOT sent — serial not "
                    "connected (reader is retrying); buzzer state unchanged"
                )
                return
            try:
                self._serial.write(byte)
            except (serial.SerialException, OSError) as exc:
                print(f"WARNING: alarm byte {byte!r} write failed ({exc})")

    def _read_loop(self) -> None:
        """Open-read-reopen forever. Two failure tiers, per info.md 3.2:
        a malformed LINE is skipped silently in _parse_line (one bad line
        must never kill the thread); a failed PORT (unplug, stuck board)
        logs one warning and retries, so a USB replug mid-run recovers
        without restarting the edge loop."""
        while not self._stop.is_set():
            try:
                with serial.Serial(self._port, self._baud, timeout=2) as ser:
                    time.sleep(SERIAL_SETTLE_SECONDS)  # Uno auto-reset settle
                    ser.reset_input_buffer()  # discard boot-time partial lines
                    # Publish the handle for set_alarm() only once the
                    # settle is done — a write during the Uno's boot
                    # window would be silently dropped by the sketch.
                    with self._port_lock:
                        self._serial = ser
                    try:
                        while not self._stop.is_set():
                            self._parse_line(ser.readline())
                    finally:
                        # Unpublish BEFORE the context manager closes the
                        # port, so set_alarm() can never write into a
                        # handle that is mid-close.
                        with self._port_lock:
                            self._serial = None
            except (serial.SerialException, OSError) as exc:
                print(
                    f"WARNING: sensor serial unavailable ({exc}); "
                    f"continuing with last-known values, retrying in "
                    f"{RECONNECT_DELAY_SECONDS:.0f}s"
                )
                time.sleep(RECONNECT_DELAY_SECONDS)

    def _parse_line(self, raw: bytes) -> None:
        """Update the pair from one line; anything unparseable is
        dropped without comment (partial boot lines and serial noise are
        routine, and per-line warnings would flood the console at 1 Hz
        for a transient that fixes itself on the next line)."""
        try:
            parts = raw.decode("ascii", errors="strict").strip().split(",")
            if len(parts) != 2:
                return
            mq2, mq135 = int(parts[0]), int(parts[1])
        except (UnicodeDecodeError, ValueError):
            return
        with self._lock:
            self._mq2 = mq2
            self._mq135 = mq135
            if self._first_reading_monotonic is None:
                self._first_reading_monotonic = time.monotonic()
