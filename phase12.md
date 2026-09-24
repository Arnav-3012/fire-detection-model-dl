# phase12.md — FireWatch two-board / ESP32-CAM update: remaining work

**This file tracks the remaining steps for the current hardware/architecture
update** (two ESP32 boards — camera-only ESP32-CAM + sensor-only plain ESP32
DevKit, cloud vision inference, new dashboard Live View). Internally this work
is "Phase 13" in `plan.md` §10 and `logs.md`; this file is named `phase12.md`
per developer instruction, for this session's own context-management purposes,
and is a separate tracking document — it does not replace or renumber
anything in `plan.md`/`logs.md`/`context.md`.

**Source of truth for everything below:** `plan.md` §10 (spec), `logs.md`'s
Phase 13 entries (history — read those before touching hardware/firmware, not
this file). This file will go stale as work completes — update it or delete
it once the update phase closes, don't let it drift into a second plan.md.

**Status: CLOSED 2026-09-24** — see the checklist at the end. Sections 0-13
below are the original 2026-09-16 plan, kept unedited as the record.

---

## 0. Current state (don't redo this)

- ESP32-CAM: OV2640 seated, MB-shield programmer working, GPIO4 LED blink
  test sketch confirmed live. Camera board is otherwise a blank slate —
  no camera-streaming firmware, no WiFi, no Lambda POST logic written yet.
- Plain ESP32 DevKit: MQ-2 → GPIO34, MQ-135 → GPIO35, buzzer → GPIO33,
  270Ω/270Ω dividers on both sensor lines, wiring confirmed via Serial
  Monitor (raw analogRead only — no project firmware written yet either).
  Burn-in running, not yet confirmed stable.
- Two open decisions **flagged but not made**, both need to happen before
  step 2 below: the 12-bit-vs-10-bit calibration-formula question, and the
  airflow false-positive mitigation approach.
- Nothing in `edge/`, `agent/`, `fusion.py`, or `dashboard/` has been touched
  by this update yet.

---

## 1. Finish burn-in and settle the sensor baseline

- Let the plain ESP32 DevKit continue burning in (24–48h total from first
  power-on per `info.md` §8) undisturbed — current wall-charger setup is
  correct, keep it away from handling/airflow during this window.
- Confirm stability the same way `plan.md` Appendix A.4 always required:
  readings steady within ±20 (12-bit terms: treat as roughly ±80, i.e. the
  same *proportional* stability, not the literal old 10-bit number) over a
  15-minute watch window.
- Do **not** treat any number logged before this is confirmed as real
  baseline data — this includes the ~100-190 range already observed.

## 2. Decide the calibration-formula question (developer decision required)

Before running the actual MQ calibration procedure, decide one of:

- **(a) Reuse `plan.md` §5.5's formula unchanged**, just computed fresh
  against real 12-bit baseline/peak numbers off the new hardware
  (`mq2_warn = baseline + 0.30 × (peak − baseline)`, etc. — the formula
  is a proportion, so it's scale-invariant; only the absolute numbers it's
  fed change).
- **(b) Re-derive something 12-bit-specific** if there's a reason (a) isn't
  good enough — e.g. if 12-bit's finer resolution changes what proportion
  actually separates "concerning" from "noise" in practice.

This decision is intentionally not made in `plan.md`/`logs.md` — pick one and
record it (with reasoning) in `logs.md` before step 3.

## 3. Run MQ calibration on the new hardware

Once burn-in is confirmed stable and the formula question (step 2) is
settled:

1. Log raw ADC values for 15 minutes in a normal room → baseline (mean, max).
2. Hold an unlit lighter with gas released ~20cm from MQ-2 for 5 seconds →
   peak. Repeat similarly for MQ-135 if it has its own trigger substance
   (per `plan.md` §5.5/§6.6 — ammonia/alcohol-class trigger, not the lighter).
3. Compute `mq2_warn`/`mq2_danger`/`mq135_warn`/`mq135_danger` per the
   decided formula.
4. Write the values into `config.yaml` (only once actually measured — never
   placeholder, per `info.md` §2.4).
5. Record baseline, peak, and derived thresholds in `logs.md`, same as the
   original Arduino-era calibration entry did.

**Safety notes carry over unchanged from `plan.md` §5.5**: ventilated room,
no ignition source, ideally someone else present, never open fire indoors.

## 4. Decide and implement the airflow false-positive mitigation

Two candidates were identified in the last session, neither chosen:

- **(a) Sustained-duration gas check** — require an elevated reading to
  persist N seconds/samples before counting as `gas_high`, mirroring the
  N-of-M `TemporalVoter` already used for vision in `edge/vision.py`. Likely
  the more principled fix since it directly targets "was this a `disturbance
  spike` or a real sustained event," which is exactly the airflow finding's
  shape (~105 baseline → ~170-185 spike, transient).
- **(b) Wider baseline margin** — raise the 0.30/0.60 multipliers so ordinary
  airflow disturbance falls under `warn`. Simpler, but blunter — raises the
  bar for detecting a real slow gas leak too.

**Before implementing either:** open and actually read `edge/fusion.py` and
whatever currently exists of the sensor-reading path (this was explicitly
deferred last session specifically so it wouldn't be guessed at blind). Decide
with the developer which approach fits, then implement it — likely in the new
sensor-board firmware (step 5) and/or `edge/fusion.py`/`edge/sensors.py`
depending on where gas thresholding ends up living post-migration.

## 5. Write firmware for the plain ESP32 DevKit (sensor board)

Not started. Needs, at minimum:

- Read GPIO34 (MQ-2) and GPIO35 (MQ-135) via `analogRead()`, matching the
  existing CSV convention (`mq2,mq135`) so downstream parsing logic can be
  reused/adapted rather than reinvented.
- Apply the calibration thresholds from step 3 and the mitigation from
  step 4 to compute `gas_high` locally.
- Drive the buzzer (GPIO33) directly and immediately on `gas_high`,
  independent of WiFi/network state — this is the core "local alarm fires
  before the network is touched" guarantee (`info.md` §2.2, scoped to
  gas detection per the 2026-09-09 resolution) and must not regress.
- Decide and implement how this board reports its readings/`gas_high` state
  over WiFi to the rest of the system (§10.6's open item in `plan.md`) —
  likely a small HTTP POST to the same FastAPI backend that will receive
  Lambda's vision callback, so fusion can happen in one place. This needs
  a design decision, not just code — figure out where fusion logically
  lives now that vision and gas arrive from two independent network paths
  instead of one shared `edge/main.py` loop.
- WiFiManager-style dual-network setup (home direct / college via the
  laptop's shared hotspot) applies to this board too if it needs internet
  access to report readings — confirm whether it does, or whether it can
  stay purely local (gas-only fallback board) and let the camera board be
  the only one that needs real connectivity.

## 6. Write firmware for the ESP32-CAM (camera board)

Not started beyond the LED blink test. Needs:

- Camera init and JPEG capture at the settled target (640×480 @ 5fps per
  `plan.md` §10.3).
- WiFiManager dual-context setup (home direct WPA2-Personal / college via
  the developer's laptop-shared hotspot) per `plan.md` §10.4.
- POST each captured frame to the AWS Lambda endpoint (step 7) within the
  cost/bandwidth envelope already estimated in `plan.md` §10.2.
- Handle a failed/timeout POST gracefully — per `info.md` §3.2's failure
  table, a Lambda/network failure must not crash the camera loop; the
  camera board itself has no local alarm responsibility (that's the sensor
  board's job per the two-board split), but it should still fail loud/
  visibly (e.g. flash LED pattern) rather than silently.

## 7. Build the AWS Lambda inference endpoint

Not started. Needs:

- Package the existing v4 ONNX model (`models/fire_mnv3.onnx`) and
  `onnxruntime` into a Lambda deployment (layer or container image —
  onnxruntime's package size may require a container image rather than a
  plain zip layer; check Lambda's 250MB unzipped limit before choosing).
- Endpoint accepts a JPEG frame, runs the same preprocessing
  `edge/vision.py` already does (224×224 normalize, BGR→RGB, etc. — reuse
  logic, don't reimplement it independently and risk divergence), returns
  `{fire, smoke, p_fire, p_smoke}` in the same shape `edge/vision.py`
  already produces.
- Wire real AWS cost/usage monitoring so the ~15h-usage / free-tier
  estimate in `plan.md` §10.2 can be checked against reality, not just
  assumed.
- Decide whether/how the existing `TemporalVoter` (N-of-M smoothing) moves
  into this new data path — it currently lives in `edge/vision.py`'s
  in-process loop; with frames now arriving asynchronously via camera board
  → Lambda → backend, the temporal-voting state needs to live somewhere
  persistent between calls (the backend, most likely) rather than inside a
  stateless Lambda invocation.

## 8. New FastAPI backend endpoint(s) — vision + gas fusion + WebSocket

Not started. Needs:

- A new endpoint (or endpoints) to receive: (a) Lambda's vision inference
  result per frame, and (b) the sensor board's gas readings/`gas_high`
  state (step 5). This is a new architectural seam that didn't exist in
  the single-loop `edge/main.py` design — fusion (`fuse()`'s existing
  4-rule table) needs to run somewhere that has both signals available,
  which is now the backend, not a single Python process.
- A new WebSocket endpoint (per `plan.md` §10.6/§10.7) that broadcasts the
  fused level + live `p_fire` to connected dashboard clients in real time.
- Reuse `edge/fusion.py`'s `fuse()` function directly rather than
  reimplementing the rule table a second time — this is the same
  "don't duplicate detection logic" discipline the project has followed
  throughout (`info.md` §2.3/§3.4).
- Decide how/whether this new real-time path coexists with the existing
  `/incident` (agent trigger) and `/api/live-sensors` (dashboard polling)
  endpoints, or replaces parts of them — needs explicit design, not an
  incidental collision.

## 9. New dashboard "Live View" tab

Not started (`plan.md` §10.7). Needs:

- A new React tab consuming the WebSocket from step 8.
- Live camera feed rendering (frame-by-frame or short-lived video, matching
  whatever the camera board actually streams).
- An AI classification badge overlaid, reusing the existing fusion-level
  color language (`src/levels.js` — SAFE/WATCH/WARNING/CRITICAL colors,
  unchanged, not a new palette).
- A live-updating `p_fire` confidence indicator alongside the feed (not
  just a static badge flip) — per `plan.md` §10.7's explicit requirement.
- Should visually and structurally match the existing five-tab dashboard's
  glass design system (`index.css`), not introduce a second design
  language.

## 10. Testing the new vision pipeline (camera → Lambda → dashboard)

Not started — no camera-board firmware exists yet to test against. Once
steps 6–8 are built:

- **Latency test:** measure real end-to-end time from a frame being
  captured to the fused result reaching the dashboard (camera capture →
  WiFi upload → Lambda inference → backend fusion → WebSocket broadcast →
  browser render). This is a new number that didn't exist in the old
  single-process design and needs measuring, not assuming.
- **Offline/WiFi-loss test:** the core demo claim (`plan.md` §2's "with the
  internet disconnected") now needs re-verifying under the new
  architecture specifically for the **gas-only fallback path** (sensor
  board's local buzzer, independent of the camera board's cloud
  dependency) — confirm the buzzer still fires with zero network, and that
  the dashboard visibly shows "vision offline / gas-only" rather than
  silently going stale.
- **Adversarial re-run, cloud path:** re-run at least the highest-value
  adversarial scenarios already proven on v4 locally (TV-fire known
  limitation, bright-wall smoke-recall fix, candle) through the actual
  camera board → Lambda path, to confirm cloud inference on real captured
  JPEGs (compression, lighting, camera-specific artifacts) reproduces the
  same behavior as the local webcam tests did — a genuinely different
  image pipeline (webcam frame vs. OV2640 JPEG) could behave differently
  even with the identical ONNX model.
- **Cost/usage re-check:** confirm actual Lambda invocation count and
  GB-seconds against the ~15h-usage estimate in `plan.md` §10.2 once real
  testing has generated genuine traffic.

## 11. Testing the new sensor pipeline (post-calibration)

Once steps 1–5 are done:

- Confirm `gas_high` computed on the new hardware correctly fires on a
  real gas trigger (lighter/alcohol test, same method as calibration) and
  does **not** false-trigger on the airflow-disturbance scenario already
  found (physically move/disturb the board without introducing gas, watch
  for a false `gas_high`) — this is the direct verification that step 4's
  mitigation actually worked, not just theorized.
- Re-confirm local buzzer-only operation with zero WiFi connectivity on
  the sensor board specifically (should be simpler to prove than before,
  since this board's fallback path no longer shares hardware/radio with
  the camera board).

## 12. Re-run/extend the Phase 11 evaluation trial set under the new architecture

The existing 12-trial set (`plan.md` "Day 11 — evaluation trial plan") was
run entirely against the old single-laptop-process architecture. Once the
two-board/cloud pipeline is live, decide with the developer whether to:

- Re-run the same 12 trials end-to-end on the new architecture as a
  regression check, or
- Treat the new architecture as a distinct system requiring its own
  smaller trial set (new latency numbers, new failure modes possible from
  network/Lambda involvement that didn't exist before), documented
  separately rather than merged into the existing `eval/results.csv` history
  without a note distinguishing old-architecture vs. new-architecture rows.

This is a **decision to raise, not to make unilaterally** — flag it,
don't just pick one.

## 13. Documentation close-out for this update

- Update `report.md` (or a report addendum) once the above is actually
  built and tested — per `info.md` §2.4, no metrics get written until
  measured. The existing report's "Future Work" section (§12) currently
  describes this migration as aspirational; it will need rewriting to
  past tense once real.
- Update `context.md`'s Phase 13 section and hardware-status table again
  once each major step above closes (camera pipeline live, sensor
  calibration done, dashboard tab built) — same append-to-logs.md /
  regenerate-context.md discipline used throughout the project
  (`info.md` §6).
- This file (`phase12.md`) itself should be checked off / retired once the
  update phase is done — it's a working checklist, not permanent project
  memory.

---

## Quick checklist (same order as above)

**PHASE CLOSED 2026-09-24.** Every item below is done. This file is kept
as the working record only; current state lives in `context.md`, history
in `logs.md` (Phase 13a-13h).

- [x] 1. Burn-in confirmed stable — logs.md Phase 13b sessions 1-2
- [x] 2. Calibration-formula question decided — superseded: per-boot baselines, then **ratio** WARN/DANGER thresholds computed by the firmware (logs.md "WARN/DANGER switched from absolute-delta to RATIO-based thresholds")
- [x] 3. MQ calibration run on new hardware — firmware-owned; config.yaml gas values are now a legacy fallback only
- [x] 4. Airflow false-positive mitigation — firmware 3-of-5 vote window (a real gas rise holds above WARN for ~39 s; a disturbance spike is brief), plus fixed mounting. Developer re-tested airflow 2026-09-24: reported pass
- [x] 5. Sensor-board (plain ESP32) firmware written — `arduino/sensor_esp32_node`
- [x] 6. Camera-board (ESP32-CAM) firmware written — `arduino/cam_node`
- [x] 7. AWS Lambda endpoint built — **as an advisory second opinion, not the detector**: local ONNX inference stayed primary (logs.md Phase 13g)
- [x] 8. Backend WebSocket endpoint built — `/ws/live`; fusion stayed in `edge/` (Phase 13f)
- [x] 9. Dashboard live view built — Phase 13f tab, then folded into the home page (Phase 13h)
- [x] 10. Vision pipeline tested — developer-run 2026-09-24, reported pass; numbers not yet recorded
- [x] 11. Sensor pipeline tested — developer-run 2026-09-24, reported pass; numbers not yet recorded
- [x] 12. Evaluation-trial re-run — developer-run on two-board hardware 2026-09-24, reported pass; numbers not yet recorded
- [x] 13. Documentation closed out — 2026-09-24 (report.md §13, context.md regenerated, logs.md)
