# FireWatch — WiFi Transport, Event-Triggered Lambda, and Live View

**Status: EXECUTED 2026-09-23. Stages 1–5 built and hardware-verified;
Stage 6 built and live-tested 2026-09-24 (logs.md "Phase 13g").** See logs.md "Phase 13f" for what was actually done, including where the implementation deviated from this
plan. Kept as written for the record — the reasoning below is what the work
was based on.

Deviations worth knowing when reading the stages below:
- **Stage 3's ingest went into `edge/main.py`, not `dashboard/backend`**
  (the plan said the latter). The backend is optional and read-only;
  routing detection input through it would make the dashboard a hard
  dependency of the detector.
- Consequently **no CORS widening was needed** — all dashboard camera
  endpoints are GET.
- Stage 3 also needed host discovery the plan did not anticipate (mDNS +
  subnet scan), because the laptop's IP changes between home WiFi and a
  phone hotspot.
- **Stage 6's trigger lives in the edge loop, not the backend** (the plan
  said "Backend, on a GAS_HIGH ingest"). Same reason as Stage 3: the
  edge loop is where gas_high and the frame local actually scored both
  live, and the backend is optional.
- **Stage 5 additionally repointed the edge loop at the relay**
  (`camera.edge_source`): it was silently defaulting to the laptop webcam,
  which the plan did not catch.

---

## Context

The sensor board and camera board both work and are hardware-validated. What's
missing is how their data reaches the dashboard: `plan.md §10.6` left transport
as an explicitly undecided open item, and the sensor firmware still logs
*"no data transmitted yet, by design (Phase 13f open item)"*.

While planning this, three pre-existing bugs surfaced that must be fixed first —
**the edge loop is currently broken against the new firmware** and silently
detects no gas at all. Transport work on top of a broken pipeline would just hide
these.

Decisions taken (developer, 2026-09-23 session):
- **Everything over WiFi.** Serial is replaced as the data path, not kept.
- **Lambda genuinely runs the ONNX inference**, as `plan.md §10.6` intended —
  but **event-triggered**, not per-frame. Continuous inference costs $18–89/mo;
  gating on the board's own `GAS_HIGH` keeps it at **$0.00/mo inside the AWS
  free tier** (verified: even 2hr/day of gas activity @2fps stays free).
- **Local edge inference stays** as the always-on safety net. This is not
  redundancy for its own sake: `edge/fusion.py:12-13` states detection is
  *"No model, no LLM, no network"*, and rule 4 caps vision-only fire at WARNING
  precisely because vision is untrusted alone. A WAN outage must never silently
  downgrade the detector. Lambda becomes the cloud *second opinion* that
  `plan.md` wanted, layered on top of a detector that never depends on it.

Outcome: board → WiFi → backend → WebSocket → Live View tab, with cloud
inference on gas events, at zero AWS cost, and the detection path still local.

---

## Stage 1 — Unbreak the edge loop (blocking; do first)

**`edge/sensors.py:190` `_parse_line()` rejects every line the new firmware
sends.** It guards `if len(parts) != 2: return`, but the ESP32 emits 3 fields
(`145,42,WARMUP`) or 9 (`145,42,ok,baseline_mq2=…,warn_mq2=…,…`). Every line is
dropped, `latest()` returns `{mq2: None, mq135: None}` forever, and gas
detection is dead. Verified by simulation against real firmware output.

- Accept 2, 3, and 9 field lines. Skip lines starting with `[` (the
  `[WARMUP_STABLE]` / `[SUSPECT_JUMP]` / `[BASELINE_TROUBLE]` diagnostics) and
  the non-CSV `BASELINE_CAPTURE done:` line.
- Capture `parts[2]` as the firmware STATE; extend `latest()` to return
  `{"mq2", "mq135", "state"}`.
- When the 9-field form is present, capture the six live threshold values into a
  new `thresholds()` accessor. This is what removes the stale-config problem at
  its source.

Reuse the already-correct parser in `eval/verify_live.py:read_one()` — it
handles exactly this format and is hardware-proven.

**Gate:** run `edge/main.py` against the board; `latest()` must return non-None
within ~1s.

## Stage 2 — One source of truth for the gas verdict

`config.yaml:22-27` holds **August 10-bit Arduino-era** thresholds
(`mq2_warn: 115.57`, from the old `baseline + 0.30*(peak-baseline)` formula).
The current 12-bit board computes WARN ≈ 237–252 dynamically per boot from
ratio thresholds. `edge/fusion.py:load_gas_thresholds()` / `compute_gas_high()`
re-derive a *second* verdict from those stale numbers — so host and board can
disagree live, and the dashboard draws stale threshold lines.

**The firmware is the source of truth.** It owns the per-boot baseline, the
ratio math, and the buzzer.

- `edge/main.py:184` — replace `compute_gas_high(...)` with
  `gas_high = (state == "GAS_HIGH")`.
- Keep `compute_gas_high()` / `load_gas_thresholds()` as a **fallback only**,
  used when `state is None` (old 2-field firmware), and log loudly when it fires.
- Treat `WARMUP` / `BASELINE_CAPTURE` as `gas_high=False` — the board already
  withholds its verdict during those. Keep the `gas_warmup_seconds` timer only
  on the fallback path.
- Re-comment `config.yaml:22-27` as *fallback-only, superseded by
  firmware-published thresholds*. Do not delete (the dashboard reads them).

**`set_alarm()` is now a silent no-op** (`edge/sensors.py:126`): it writes
`b"A"`/`b"S"`, which the old `arduino/sensor_node/sensor_node.ino:31` listened
for, but the new ESP32 firmware has no `Serial.read()` at all — it buzzes
autonomously. Fix by making this **explicit, not by changing firmware**: update
the docstring and log once at startup that the board owns the buzzer. Adding
host-forced alarm to safety-critical firmware before a deadline is not worth it.

## Stage 3 — WiFi transport (replaces serial)

Add an HTTP POST client to `arduino/sensor_esp32_node/sensor_esp32_node.ino` at
the `:1156` stub, sending one JSON reading per second to a new backend ingest
endpoint. Mirror the existing discipline in `edge/main.py:notify_agent()` —
short timeout, fire-and-forget, never blocks the alarm path. Reuse
`cam_node.ino`'s non-blocking `ensureWifi()` pattern.

Payload carries what the board already knows: `mq2`, `mq135`, `state`,
and the six live thresholds.

- New `POST /api/sensor-ingest` on `dashboard/backend/main.py`, holding the
  latest reading in memory.
- **CORS must widen** — `dashboard/backend/main.py:49` is `allow_methods=["GET"]`.
- New `WifiSensorSource` in `edge/sensors.py` exposing the *same* surface as
  `SensorReader` (`latest()`, `first_reading_monotonic()`, `set_alarm()`,
  `start()`, `stop()`) so `edge/main.py` swaps sources with no downstream change.
- Keep serial selectable via a config flag for fallback during bring-up.

## Stage 4 — Camera fan-out via local relay

`cam_node.ino`'s `/stream` serves **exactly one client** — the edge loop holding
it open blocks the dashboard entirely. Do **not** rewrite the firmware
(FreeRTOS multi-client is high-risk before a deadline); use the standard relay
pattern instead.

New `edge/camrelay.py`: one thread holds the single upstream
`http://<cam-ip>/stream`, parses the multipart boundary, and keeps the newest
JPEG in a lock-guarded slot. **No re-encoding.** Every consumer reads the slot,
so the one-client limit is satisfied permanently.

Run the relay **inside the dashboard backend** so the Live View tab works even
when the edge loop is stopped. Expose `GET /api/camera/stream` (MJPEG
`StreamingResponse`) and `GET /api/camera/snapshot`.

## Stage 5 — WebSocket + Live View tab

- `dashboard/backend/main.py`: add `@app.websocket("/ws/live")`. Send the
  current payload on connect, then push at 1Hz. Payload shape **identical to
  `/api/live-sensors`** (`{ok, reason, readings[], thresholds{}}`) so
  `components/LiveSensorChart.jsx` drops in unchanged. Source `thresholds` from
  the firmware-published values, falling back to config.
  Note: the WS handshake bypasses CORS middleware, so no extra CORS work here.
- New `dashboard/frontend/src/useWebSocket.js` returning the exact
  `{data, error, loading}` contract of `usePolling.js`, with auto-reconnect.
  Identical shape means falling back to polling is a one-line change.
- New `dashboard/frontend/src/tabs/LiveView.jsx`: `<LiveSensorChart>` plus
  `<img src="/api/camera/stream">`. Register in `App.jsx:51-79`. Reuse
  `StateCard`, `LevelBadge`, and `Overview.jsx:21`'s `LIVE_STALE_MS = 12_000`
  staleness convention.

## Stage 6 — Event-triggered Lambda inference

Triggered only when the board reports `GAS_HIGH` — this is what keeps it free.

- Backend, on a `GAS_HIGH` ingest, POSTs the current relay frame to API Gateway
  → Lambda running the v4 ONNX model.
- Lambda's verdict returns as a **cloud second opinion**, displayed alongside
  the local verdict in Live View. It never gates the local alarm.
- Extend `cloud/uploader.py` (already works, has a 50-upload breaker) to archive
  CRITICAL incidents to S3.
- Amend `plan.md §10.6` to record that *continuous* per-frame inference was
  considered and rejected on cost ($18–89/mo) and safety-path grounds, and that
  event-triggered inference was chosen instead.

---

## Verification

1. **Stage 1:** flash board, run `edge/main.py`, confirm live mq2/mq135 values
   appear (they currently do not) and `state` tracks `WARMUP` → `ok`.
2. **Stage 2:** trigger gas; confirm `gas_high` flips from the board's own
   `GAS_HIGH` state and the fallback warning does *not* appear.
3. **Stage 3:** `curl` the ingest endpoint; then unplug USB and confirm readings
   still arrive over WiFi.
4. **Stage 4:** open `/api/camera/stream` in a browser **while** `edge/main.py`
   is running — both must get frames simultaneously. This is the regression the
   relay exists to prevent.
5. **Stage 5:** open Live View; confirm chart updates at 1Hz, threshold lines
   match the board's printed `warn_*` values, and it reconnects after restarting
   the backend.
6. **Stage 6:** trigger gas, confirm exactly one Lambda invocation per event
   (not per frame) in CloudWatch, and that local detection still works with WiFi
   disabled.

## Cut lines if time runs short

Stages 1–2 are pure bug fixes and are **not optional** — the system currently
detects no gas. Stage 6 can be cut entirely. Stage 5's WebSocket can downgrade
to `usePolling` at 1Hz (one-line change, identical contract). Stage 3 can fall
back to serial via the config flag if WiFi ingest proves flaky during bring-up.
