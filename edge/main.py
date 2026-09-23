"""Edge loop v3 (Phase 7): camera -> vision + sensors -> fusion -> LOCAL alarm -> (network).

The ordering inside the loop is MANDATORY per info.md 2.2 and is the core
architectural claim of the project:

    1. compute the fusion level
    2. drive the local buzzer            <- never conditional on network
    3. THEN attempt the network step, in try/except

Nothing network-related appears before the set_alarm() call, and nothing
may reorder this — a network failure must never delay the local alarm.

GAS VERDICT — ONE SOURCE OF TRUTH (2026-09-23, Stage 2). The FIRMWARE
decides. sensor_esp32_node.ino owns the per-boot baseline, the ratio
thresholds and the buzzer, and publishes a STATE field; gas_high is
simply (state == "GAS_HIGH"). The host does NOT re-derive a second
verdict, because config.yaml's gas thresholds are August 10-bit
Arduino-era numbers (mq2_warn=115.57) while the 12-bit board computes
WARN ~237-252 dynamically per boot — two verdicts that can disagree
live, with the board's being the correct one.

compute_gas_high()/load_gas_thresholds() survive as a FALLBACK ONLY, for
legacy 2-field firmware that sends no state, and fire a loud once-only
warning when used.

The Phase 7 host warm-up gate (gas_warmup_seconds, forcing gas_high
False because a cold MQ-135 reads ~100-102, above the warmed-sensor
mq135_warn=98.77) now applies ON THE FALLBACK PATH ONLY. On the firmware
path the board's own slope-based warm-up gate replaces it — it is
strictly better than a fixed timer, and stacking both would suppress a
real GAS_HIGH the board is already buzzing on. WARMUP/BASELINE_CAPTURE
report gas_high False regardless, since the board withholds its verdict
during them. Only the gas contribution is ever suppressed; vision
detection runs normally throughout, so the worst case during the gate is
a WARNING (vision-only cap), never a false gas-corroborated CRITICAL.

BUZZER OWNERSHIP: the ESP32 firmware has no Serial.read() and buzzes
autonomously off its own GAS_HIGH, so set_alarm() is inert against it —
stated loudly at startup rather than silently pretending otherwise.

Video source (phase13a-2, togglable test mode): defaults to the laptop
webcam. Pass --video-source http://<esp32-ip>/stream to read frames from
the ESP32-CAM's MJPEG stream instead — only where frames come from
changes; model loading, preprocessing, TemporalVoter, and thresholds in
vision.py are untouched.

    python edge/main.py --video-source http://<esp32-ip>/stream
"""

import argparse
import base64
import time

import cv2
import requests
import yaml

from camera import Camera
from fusion import Level, compute_gas_high, fuse, load_gas_thresholds, temp_spiking
from livelog import LiveLogWriter
from sensors import SensorReader
from vision import VisionModel

# Reporting cadence only — affects nothing about detection (see Phase 4).
FPS_REPORT_EVERY = 30


def notify_agent(
    url: str,
    level: Level,
    reason: str,
    result: dict[str, bool | float | int],
    readings: dict[str, int | None],
    gas_high: bool,
    gated: bool,
    frame,
) -> None:
    """POST the incident to the agent. Fire-and-forget: 2s timeout, never raises.

    Runs strictly AFTER set_alarm() in the loop (info.md 2.2) — a dead
    agent, dead network, or slow encode must cost nothing but this one
    call's 2 seconds, and can never suppress the local alarm that already
    fired. The verdict travels ready-made; the agent composes the response
    and never re-decides it (info.md 2.3).
    """
    try:
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        payload = {
            "level": level.name,
            "reason": reason,
            "vision": {k: (float(v) if k == "p_fire" else v) for k, v in result.items()},
            "sensors": {**readings, "gas_high": gas_high, "gated": gated},
            "snapshot_b64": base64.b64encode(jpeg.tobytes()).decode() if ok else None,
        }
        requests.post(url, json=payload, timeout=2)
        print(f"*** agent notified: {level.name} ***")
    except requests.RequestException as exc:
        print(f"WARNING: agent notify failed ({exc.__class__.__name__}) — local alarm unaffected")


def format_status(
    result: dict[str, bool | float | int],
    readings: dict[str, int | None],
    gas_high: bool,
    gated: bool,
    level: Level,
    reason: str,
) -> str:
    """One console line per frame: raw vision, raw gas, fused verdict.

    Everything appears together because fusion disagreements ARE the
    information — "p_fire high but level=WARNING" is rule 4 (the TV-fire
    cap) visibly working, and "gas_high=False (GATED)" shows the warm-up
    gate suppressing, not a sensor failure.
    """
    gas = f"mq2={readings['mq2']} mq135={readings['mq135']}"
    # Board state shown verbatim so a disagreement between the firmware's
    # verdict and gas_high is visible at a glance rather than inferred.
    state = readings.get("state")
    gas += f" state={state}" if state is not None else " state=- (fallback)"
    gate_note = " (GATED)" if gated else ""
    # p_smoke/smoke_votes added 2026-09-04: the smoke-noise investigation
    # had only p_fire on this line, so the actual smoke evidence behind a
    # WATCH was invisible. Trailing "{level.name}: {reason}" is what
    # eval/run_trial.py parses — keep it last and unchanged.
    return (
        f"p_fire={result['p_fire']:.2f} votes={result['votes']} "
        f"alarm={result['alarm']} | p_smoke={result['p_smoke']:.2f} "
        f"smoke_votes={result['smoke_votes']} | {gas} gas_high={gas_high}{gate_note} | "
        f"{level.name}: {reason}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FireWatch edge loop")
    parser.add_argument(
        "--video-source",
        default=None,
        help=(
            "Video source: an MJPEG stream URL (e.g. http://<esp32-ip>/stream) "
            "to read from the ESP32-CAM. Omit to use the laptop webcam "
            "(edge/camera.py's default DEVICE_INDEX), the normal path."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    warmup_seconds = float(config["sensors"]["gas_warmup_seconds"])
    notify_cooldown = float(config["fusion"]["notify_cooldown_seconds"])
    agent_url = config["agent"]["incident_url"]

    # camera failure = loud error + exit, per edge/camera.py. --video-source
    # swaps only where frames come from (phase13a-2); everything downstream
    # (vision, fusion, alarm) is identical either way.
    camera = Camera(args.video_source) if args.video_source else Camera()
    model = VisionModel()
    thresholds = load_gas_thresholds()
    reader = SensorReader()
    reader.start()  # never raises; a dead port degrades to None readings
    live_log = LiveLogWriter()
    live_log.start()  # dashboard live-view only; all file I/O on its own thread

    print("FireWatch edge loop v3 (fusion + local alarm) running. Ctrl+C to stop.")
    print(
        "Gas verdict: FIRMWARE state field is authoritative (board owns baseline, "
        "ratio math and buzzer)."
    )
    print(
        f"  config.yaml gas thresholds are FALLBACK ONLY, used if the board sends no "
        f"state; the {warmup_seconds:.0f}s host warm-up gate applies on that path only."
    )
    # set_alarm() is a no-op against the current ESP32 firmware, which has
    # no Serial.read() at all — it buzzes autonomously off its own
    # GAS_HIGH. Said once, loudly, at startup rather than changing
    # safety-critical firmware before a deadline (2026-09-23 decision).
    print(
        "  NOTE: the BOARD owns the buzzer. set_alarm() writes are inert against "
        "sensor_esp32_node.ino (no Serial.read()); host alarm state is display-only."
    )

    # Buzzer state lives HERE, not on the Arduino: the sketch is a dumb
    # actuator ('A'/'S', no ack), so this flag is what makes alarm writes
    # transition-driven instead of spamming a byte every frame at 30 FPS.
    alarm_on = False
    # Seeded so the first WARNING+ frame notifies immediately.
    last_notify = time.monotonic() - notify_cooldown
    gate_announced = False
    gate_cleared_announced = False
    # Latches the once-only "no STATE field" fallback warning below.
    fallback_announced = False
    frame_count = 0
    window_start = time.perf_counter()

    try:
        while True:
            frame = camera.read()
            result = model.predict_smoothed(frame)
            readings = reader.latest()

            # --- gas signal, warm-up gated -------------------------------
            # Three states: no data yet (sensor absent/booting -> gas_high
            # False, per sensors.latest()'s contract that fusion must not
            # fire on an absent sensor), gated (valid data, still inside
            # the settle window), or live.
            first_reading = reader.first_reading_monotonic()
            state = readings["state"]
            gated = False

            if readings["mq2"] is None or readings["mq135"] is None or first_reading is None:
                # No data yet (sensor absent/booting).
                gas_high = False

            elif state is not None:
                # --- PRIMARY PATH: the board's own verdict ---------------
                # The firmware owns the per-boot baseline, the ratio math
                # and the buzzer, so its GAS_HIGH state IS the verdict —
                # host-side re-derivation from config.yaml's stale 10-bit
                # Arduino-era numbers could disagree with the board live.
                # One source of truth (2026-09-23 Stage 2 decision).
                gas_high = state == "GAS_HIGH"

                # WARMUP/BASELINE_CAPTURE already withhold the board's
                # verdict (it has no baseline yet, and its own buzzer is
                # suppressed during both), so those states are gas_high
                # False by the line above. Surfacing them as `gated`
                # keeps the status line honest about *why* gas is
                # inactive. The host-side warm-up TIMER is deliberately
                # NOT applied here — the board's slope-based gate is
                # strictly better than a fixed 240s guess, and applying
                # both would suppress a real GAS_HIGH the board is
                # already buzzing on.
                if state in ("WARMUP", "BASELINE_CAPTURE"):
                    gated = True
                    if not gate_announced:
                        gate_announced = True
                        print(
                            f"*** BOARD WARM-UP ({state}) — board withholds its gas "
                            f"verdict until its own baseline is captured; vision "
                            f"detection unaffected ***"
                        )
                elif gate_announced and not gate_cleared_announced:
                    gate_cleared_announced = True
                    print(f"*** BOARD WARM-UP CLEARED (state={state}) — gas_high now live ***")

            else:
                # --- FALLBACK PATH: legacy 2-field firmware -------------
                # No state field, so there is no board verdict to trust
                # and the host must re-derive one from config.yaml. These
                # thresholds are stale by design (see config.yaml's
                # sensors block) — hence the loud, once-only warning. The
                # fixed warm-up TIMER applies only here, because this
                # firmware has no slope-based gate of its own.
                if not fallback_announced:
                    fallback_announced = True
                    print(
                        "*** WARNING: sensor board reports no STATE field — falling "
                        "back to host-side gas thresholds from config.yaml. These are "
                        "stale 10-bit Arduino-era values and may disagree with the "
                        "board. Flash arduino/sensor_esp32_node/sensor_esp32_node.ino "
                        "to restore the firmware verdict. ***"
                    )
                if time.monotonic() - first_reading < warmup_seconds:
                    gated = True
                    gas_high = False
                    if not gate_announced:
                        gate_announced = True
                        print(
                            f"*** GAS WARM-UP GATE ACTIVE (fallback) — gas_high forced "
                            f"False for {warmup_seconds:.0f}s (cold MQ-135 reads above "
                            f"its warn threshold); vision detection unaffected ***"
                        )
                else:
                    gas_high = compute_gas_high(
                        float(readings["mq2"]), float(readings["mq135"]), thresholds
                    )
                    if gate_announced and not gate_cleared_announced:
                        gate_cleared_announced = True
                        print("*** GAS WARM-UP GATE CLEARED — gas_high now live ***")

            # --- 1. fusion level ----------------------------------------
            # vision_fire is the temporal voter's smoothed alarm, not the
            # lenient per-frame flag — a single 0.30-threshold frame must
            # not reach the fusion table (Phase 4's whole point). Smoke gets
            # the same treatment since 2026-09-04 (smoke_sustained, not the
            # raw per-frame `smoke`): isolated frames were firing WATCH.
            level, reason = fuse(
                vision_fire=bool(result["alarm"]),
                vision_smoke=bool(result["smoke_sustained"]),
                gas_high=gas_high,
                temp_spiking=temp_spiking(),  # always False — DHT22 cut, see fusion.py
            )

            # --- 2. LOCAL alarm — before any network code (info.md 2.2) --
            # Direct fire-and-forget write on THIS thread, decoupled from
            # the reader thread (see sensors.set_alarm's docstring).
            # Transition-driven across the WARNING boundary: WARNING and
            # CRITICAL both sound the buzzer (both are act-now levels;
            # only the network escalation differs), SAFE/WATCH silence it.
            if level >= Level.WARNING and not alarm_on:
                alarm_on = True
                reader.set_alarm(True)
                print(f"*** LOCAL ALARM ON — {level.name}: {reason} ***")
            elif level < Level.WARNING and alarm_on:
                alarm_on = False
                reader.set_alarm(False)
                print(f"*** LOCAL ALARM OFF — de-escalated to {level.name} ***")

            # --- 3. network step (Phase 8) — strictly after set_alarm ----
            # Cooldown applies ONLY here: the buzzer above has none. One
            # sustained fire = one agent notification per 60s, not 30/s.
            if level >= Level.WARNING and (
                time.monotonic() - last_notify >= notify_cooldown
            ):
                last_notify = time.monotonic()
                notify_agent(
                    agent_url, level, reason, result, readings, gas_high, gated, frame
                )

            print(format_status(result, readings, gas_high, gated, level, reason))

            # --- 4. live-view sample (Phase 11) — last, after alarm+network.
            # At most one queue put per second; never touches a file on this
            # thread (see livelog.py). Purely additive for the dashboard.
            # `level.name` passed through as-is (2026-09-04 dashboard fix):
            # this is the SAME already-computed fuse() verdict from step 1
            # above, at every level including SAFE/WATCH — not a second
            # fusion call, not gated to WARNING+ like notify_agent() is.
            # That gate exists for notify_agent specifically because it does
            # a JPEG encode + network POST (too expensive for 30 FPS); this
            # call was already unconditional and near-free before this
            # change, so recording every level costs nothing new.
            live_log.record(readings["mq2"], readings["mq135"], float(result["p_fire"]), level.name)

            frame_count += 1
            if frame_count % FPS_REPORT_EVERY == 0:
                now = time.perf_counter()
                fps = FPS_REPORT_EVERY / (now - window_start)
                window_start = now
                print(f"--- rolling FPS over last {FPS_REPORT_EVERY} frames: {fps:.1f} ---")
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        # Best-effort silence on exit — without this, Ctrl+C during an
        # alarm leaves the buzzer latched HIGH until the board resets.
        if alarm_on:
            reader.set_alarm(False)
        reader.stop()
        live_log.stop()
        camera.release()


if __name__ == "__main__":
    main()
