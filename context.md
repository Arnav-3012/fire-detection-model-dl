# context.md — fast context recovery

This file is regenerated, not appended to. It is a summary only — it may be
stale. **`logs.md` remains the source of truth.**

---

## 1. What FireWatch is

FireWatch is an IoT fire and gas hazard detection system with local edge
inference and agentic response, deadline 30 August 2026. Core deliverable
(plan.md §2): a laptop-hosted edge node with a webcam and an Arduino sensor
board detects fire or smoke locally, cross-checks it against gas and
temperature readings, and within 10 seconds produces a verified alert that
reaches a real phone and a logged simulated dispatch packet — with the
internet disconnected.

---

## 2. Corrected architecture (plan.md §1)

1. Simulated dispatch, full payload logged but never transmitted
2. Model runs locally on the edge device. Cloud logs and retrains only
3. Camera **plus** gas sensors, fused
4. **Laptop is the edge device.** Pi is optional stretch
5. Fine-tune pretrained MobileNetV3-Small
6. Agent handles **response only**, never detection
7. Threshold plus temporal smoothing
8. Hardcoded coordinates, GPS optional

**DHT22 is cut** (Phase 0g) — `temp_spiking()` stubbed always-False.

---

## 3. Current phase and status

**Project status: FUNCTIONALLY COMPLETE (2026-09-06).** Every planned
software phase (0-11) is built and has been demo-verified end-to-end at
least once: v4 is the promoted production model, live in
`models/fire_mnv3.onnx`; the full edge -> fusion -> agent -> cloud
pipeline is wired and confirmed (see §4 item -20 — the agent
auto-triggers on real WARNING/CRITICAL, no manual invocation needed);
all 12 Phase 11 evaluation trials are complete (11/12 PASS, one
documented new limitation — total darkness producing a false
vision-only WARNING). Remaining work is Phase 12 (documentation/report)
plus a short list of developer-run LIVE RE-VERIFICATION checks carried
in §7 below (dashboard never yet opened in a browser; the standing
SAFETY-CRITICAL FPS/buzzer re-check; Phase 8b's Twilio drills never
confirmed live) — these are re-checks of already-built, already
demo-working functionality, not unbuilt features, but they are real
pending items and are kept below rather than dropped from the record.

**Phase 13 (ESP32-CAM migration) — finalized PLAN only, NOT STARTED
(2026-09-07).** A faculty-suggested advancement beyond the original
12-day scope, planned in `plan.md` §10 with hardware already in hand
(AI-Thinker ESP32-CAM + OV2640, FTDI programmer, reusing existing
MQ-2/MQ-135/buzzer). The Arduino Uno and `arduino/sensor_node.ino` are
fully retired by this migration, not supplemented. Key decisions:
cloud inference (AWS Lambda running the existing v4 ONNX model
unmodified — on-device TinyML ruled out on memory/compute grounds),
~$0 cost within AWS Lambda's free tier for the estimated 15h demo
usage pattern, a two-context WiFiManager WiFi setup (home direct;
college via the developer's laptop sharing its authenticated
captive-portal connection as a WPA2-Personal hotspot), a disclosed
gas-only/local-only buzzer fallback on total WiFi loss, and a new
WebSocket-driven "Live View" dashboard tab (camera feed + fusion-level
badge + live `p_fire` indicator). Flags one open design question for
future discussion: how info.md §2.2's "local alarm before network"
principle applies once vision inference is inherently cloud-dependent.
**RESOLVED 2026-09-09** — see info.md §2.2 (scope clarification added
to the principle's text) and plan.md §10.9: the principle is scoped to
GAS-based detection (fully local, unchanged); vision detection is
disclosed as cloud-dependent by design, with the existing gas-only
WiFi-loss fallback (§10.5) consistent with, not a violation of, the
principle.
**This is planning only — it does not change the FUNCTIONALLY COMPLETE
status above, which refers to the existing, submitted, working
Arduino-based v4 system, unaffected by this future-phase plan.**

**Phase 13 hardware progress (2026-09-08) — BLOCKED on hardware, first
flash attempt failed:** OV2640 camera seating, FTDI wiring, and the
Arduino IDE compile toolchain are all complete and verified (clean
compiles, correct AI Thinker ESP32-CAM board profile, genuine ESP32-S
chip confirmed). **Upload itself is BLOCKED** — every attempt failed
with "Failed to connect to ESP32: No serial data received" across
every wiring/baud/timing variation tried. Diagnostic isolation cleared
both the FTDI board (loopback test passed) and the ESP32-CAM itself
(IO4-to-3V3 LED test confirmed it powers on) as fully dead — narrowing
the fault to the connection between them. **Suspected but unconfirmed
root cause:** the generic FTDI/HW-417C adapter's onboard regulator
likely cannot supply enough stable current for the ESP32 bootloader
stage (matches Espressif's own esptool docs and community reports; no
multimeter available this session to confirm). **Decision:** stop
debugging the bare FTDI setup and acquire an ESP32-CAM-MB USB
programmer shield (own regulator + BOOT/RESET buttons, eliminates the
suspected failure points) — purchase in progress. **No code has ever
been successfully uploaded to the ESP32-CAM.** See logs.md "Phase 13 —
ESP32-CAM first flash attempt, BLOCKED (hardware)".

**UPDATE 2026-09-09 — UNBLOCKED, first flash CONFIRMED:** the
ESP32-CAM-MB shield (HW-381) resolved the upload blockage entirely.
Hardware wiring, camera seating, and toolchain were already complete
per the note above; **upload itself now also succeeds** (esptool
"Hard resetting via RTS pin", no manual button press needed) and was
verified end-to-end with a GPIO4 LED blink test sketch running
correctly on the device. FTDI-direct wiring is retired for this
project. See logs.md "Phase 13 — ESP32-CAM first successful flash, MB
shield".

**UPDATE 2026-09-09 — MB-shield sensor pin plan corrected, then
SUPERSEDED entirely (2026-09-16, see next entry):** the developer's
official AI-Thinker pinout diagram showed GPIO34/35/36/39 don't
physically exist on this board's header; the only free candidates
(IO12-15) were ADC2 pins tied to the SD/flash bus, with IO12/IO15
excluded as boot-mode straps and IO13/IO14 accepted with a documented
ADC2-vs-WiFi reliability risk (MQ-2→GPIO14, MQ-135→GPIO13, buzzer→
GPIO2). **This entire MB-shield sensor-wiring plan is now DONE, not
carried forward** — see the architecture change below.

**ARCHITECTURE CHANGE 2026-09-16 — two-board split, MB-shield sensor
plan SUPERSEDED:** FireWatch now uses TWO separate ESP32 boards. (1)
The ESP32-CAM on its MB shield is camera/vision ONLY, untouched,
unchanged from the successful-flash entry above — no sensor wiring on
it anymore. (2) A new plain ESP32 DevKit V1 (30-pin) carries MQ-2,
MQ-135, and the buzzer, chosen specifically because it has genuine
ADC1 pins, eliminating the ADC2-vs-WiFi conflict the MB-shield plan
had to accept as a risk. **Confirmed pins:** MQ-2 → GPIO34, MQ-135 →
GPIO35 (both ADC1, input-only), buzzer → GPIO33; both sensors' A0
lines go through a 270Ω/270Ω (1:1) voltage divider (~9.3mA draw,
confirmed safe) since A0 can swing toward 5V against these 3.3V-max
GPIOs; D0 pins on both sensors intentionally unwired (analog-only,
per plan.md Appendix A.2). **Working hardware confirmed via Serial
Monitor** — both sensors read a stable, correlated ~100-190 range
(12-bit ADC) during warm-up. **New finding:** both sensors show a
real, repeatable reading jump (~105→~170-185) when the board is moved
or disturbed by airflow — not gas presence, both sensors move
together (rules out a wiring fault), a known MQ-sensor airflow-
sensitivity behavior, and a genuine false-positive risk for the
existing threshold formula if the deployment site has ambient air
movement. **Burn-in in progress, not yet confirmed stable** — do not
treat the ~100-190 figures as calibration data (info.md §8). **Two
items explicitly flagged, not decided, this session:** (a) plan.md
§5.5's calibration formula was written for the Arduino Uno's 10-bit
ADC; this hardware is 12-bit — needs a developer decision on whether
the existing proportional formula just gets fresh 12-bit baseline/peak
numbers, or needs re-deriving; (b) the airflow false-positive risk
needs either a sustained-duration gas-alert check (N-of-M style, like
the existing vision TemporalVoter) or a wider baseline margin — this
needs to be decided with the actual `edge/`/`fusion.py` code in view
next session, not guessed at now. No firmware, calibration values, or
`edge/`/`fusion.py`/`agent/`/`dashboard/` code was touched this
session (developer instruction: documentation/status only). See
logs.md "Phase 13 — architecture change: two-board split, MB-shield
sensor wiring abandoned".

**Phase 13a — ESP32-CAM camera hardware smoke test: PASS (2026-09-16),
sketch-writing deliverable still pending.** Camera hardware itself
confirmed working via the Arduino IDE's stock `CameraWebServer` example
sketch (not yet a project-specific sketch): live WiFi stream on the
HOME network, image quality/color/orientation all correct on manual
check. Two issues found and resolved en route — a wrong board define
(`CAMERA_MODEL_ESP_EYE` instead of `CAMERA_MODEL_AI_THINKER` in
`board_config.h`, a config error not a hardware fault) caused an
initial camera-probe failure; after fixing that, a second failure
("JPEG format is not supported on this sensor") was worked around by
switching to `PIXFORMAT_RGB565` — a documented behavior for this
sensor/driver combination per web research this session, not confirmed
against a vendor datasheet for the exact sensor variant. **Open
decision, not resolved:** whether to build the real capture/streaming
pipeline on RGB565 as-is (converting format later if needed) or
investigate getting native JPEG working, since JPEG is smaller/faster
over WiFi and matches the streaming/Lambda design assumptions in
plan.md §10.3/10.6. The actual Phase 13a deliverable — a FireWatch-
specific capture sketch — has not been written yet. See logs.md
"Phase 13a — ESP32-CAM camera hardware smoke test: PASS".

**RESOLVED 2026-09-16 — JPEG rejection root-caused, genuine sensor
limitation, not a config bug:** a diagnostic `s->id.PID` read (under
the working RGB565 config) returned `0x2145`, which decodes exactly to
`GC2145_PID` in the installed `esp32-camera` driver's `sensor.h` — this
specific module has a **GalaxyCore GC2145 sensor, not an OV2640**, a
known aftermarket "AI-Thinker-compatible" clone pattern. GC2145 has no
on-chip JPEG hardware encoder; the driver's per-sensor `support_jpeg`
capability flag correctly rejects `PIXFORMAT_JPEG` for this chip. The
PSRAM/config-mismatch theory was ruled out (`psramFound()==1` confirms
PSRAM is genuinely wired through; the failure is upstream, at the
sensor-capability check). **Decision (path (b) superseded, not
literally native JPEG but the equivalent):** capture stays RGB565
(the only format this sensor supports), then JPEG-encode each frame
on-device in software via the driver's `frame2jpg()` before the frame
reaches WiFi/Lambda — keeps plan.md §10.2/10.3/10.6/10.7's JPEG-based
downstream architecture (Lambda inference, bandwidth budget, MJPEG/
dashboard streaming) intact, with software encoding as a capture-time
step rather than a redesign around raw RGB565 over WiFi. Trade-off:
achievable FPS will be lower than the OV2640-based hardware-JPEG
assumption in plan.md §10.3 and is not yet measured. See logs.md
"Phase 13a addendum — JPEG rejection root-caused: GC2145 sensor, not
OV2640".

**Phase 13a real capture sketch WRITTEN 2026-09-16, not yet flashed/
measured:** `arduino/cam_node/cam_node.ino` replaces the stock
CameraWebServer example — captures `PIXFORMAT_RGB565` at
`FRAMESIZE_VGA` (the GC2145's real native format), converts each frame
to JPEG in software via the driver's `frame2jpg()` immediately before
it reaches the network, and serves `GET /capture` (single JPEG) and
`GET /stream` (MJPEG multipart) mirroring the stock example's own
endpoint convention. Wire format stays JPEG per plan.md's original
assumption; only the capture-side format and the added software-
encode step differ. WiFi is HOME-only/hardcoded for now — plan.md
§10.4's two-context WiFiManager switching is explicitly not built yet.
**Flagged, not silently absorbed:** software JPEG encoding is
CPU-bound (GC2145 has no hardware encoder), a real per-frame latency
cost plan.md §10.3's 640x480@5fps target never budgeted for; the
sketch times and Serial-prints each conversion so this is directly
measurable, but no hardware run has happened yet — achievable FPS is
still unknown. See logs.md "Phase 13a — real capture sketch written:
GC2145 RGB565 + on-device JPEG conversion".

**Phase 13d — sensor board firmware SKELETON written 2026-09-16, NOT
calibrated, NOT live-tested:** `arduino/sensor_esp32_node/sensor_esp32_node.ino`
is the first project sketch ever run on the plain ESP32 DevKit
(MQ-2/MQ-135/buzzer board, §10.0a). Structure only: 12-bit ADC reads on
GPIO34/GPIO35, the existing `gas_warmup_seconds=240` gate reused
unchanged, threshold/baseline constants left as clearly-named
placeholders (`*_PLACEHOLDER`, all `-1`) pending Phase 13b's
post-burn-in calibration, and an N-of-M sustained-duration voting
buffer mirroring `edge/vision.py`'s `TemporalVoter` with placeholder
window/threshold constants pending Phase 13c's still-undecided N/M
values. Buzzer (GPIO33) triggers via direct local `digitalWrite()`
with no WiFi dependency anywhere in its control path (verified by
inspection, plan.md §10.5). WiFi connect-only, reusing
`arduino/cam_node.ino`'s HOME-network pattern — **transmits no data**,
by design, since plan.md §10.6 leaves the sensor board's transport
mechanism to Phase 13f. Not marking Phase 13d complete — pending
Phase 13b/13c real values, a flash to hardware, buzzer wire
reconnection (disconnected during burn-in), and live verification.
Analog reads now go through a `readAveraged()` helper (8 samples,
2ms apart, both tunable constants) instead of single-sample
`analogRead()`, to reduce known ESP32 ADC single-sample noise ahead
of Phase 13b calibration — value stays a plain 0-4095 int, no
normalization added. **UNRESOLVED, not fixed:** physically moving the
board still causes reading jumps despite seated wiring and mesh caps
already present on both sensors; root cause not confirmed (candidates:
marginal Dupont connections under movement, friction-fit divider
resistors, or residual airflow response). Mitigation for now is
deployment-level (mount and don't handle the board), not an
engineering fix. A `SUSPECT_JUMP` stopgap flag (2026-09-17) now logs
when a reading deviates from its recent history beyond
`JUMP_FLAG_DELTA_PLACEHOLDER`, but ships inert (`-1`) until a real
noise floor is measured, and never suppresses a reading — a genuine
gas event must still reach the buzzer path untouched. An interim,
provisional (pre-mount) baseline-sampling procedure is also now
defined for Phase 13b prep, using a median over an undisturbed logging
window rather than a real fixed mount. See logs.md "Phase 13d — plain
ESP32 DevKit sensor firmware SKELETON written, NOT calibrated, NOT
live-tested".

**Hardware update 2026-09-17 — divider changed TWICE, breadboard
replaces direct jumpers (see plan.md §10.0a for full detail):** the
sensor board's voltage divider changed from **270Ω/270Ω (1:1, ×0.5)**
to **10kΩ/15kΩ (2:3, ×0.6)**, then again the same night to
**22kΩ(top)/10kΩ(bottom) (×0.3125, ~1.56V max for a 5V sensor
output)** per sensor. The second change was made without an
immediate log entry; it's recorded here after the fact. Wiring also
moved from direct point-to-point jumpers to a breadboard-based
topology for both sensors, specifically because the direct-jumper
connections were mechanically unreliable under physical movement (the
earlier-logged UNRESOLVED reading-jump issue) and soldering wasn't
available as a fix.

**MQ-135 near-zero WARMUP readings — investigated and RESOLVED as an
attenuation mismatch, not a hardware fault.** Live-tested by bringing
a hand sanitizer stimulus near MQ-135 during WARMUP: reading rose
measurably from ~0, confirming sensor + signal path both work. Root
cause: the ESP32 core's default `ADC_ATTEN_DB_11` attenuation
(accurate range ~150-2450mV) was mismatched to the 22k/10k divider's
real ~0-1.56V output range, compressing the usable signal into a
small, low-resolution slice near the ADC's ~150mV accurate floor.
Fixed by calling `analogSetAttenuation(ADC_6db)` (accurate range
~150-1750mV) in `setup()` — **this DOES count as a real firmware
change**, correcting an earlier over-broad claim that no divider
change would ever require touching `sensor_esp32_node.ino` (true for
the sample/vote/threshold control-flow logic, not true for ADC
attenuation). See logs.md 2026-09-17 for the full investigation and
math. **Live-tested tonight, both sensors, under the corrected
attenuation:** MQ-2 showed a strong, correct response-and-decay curve
to unlit gas-stove gas (baseline ~90-100, peak 147, decayed over ~25
samples); MQ-135 showed a weak response to the same stove-gas
stimulus (expected — MQ-135 is tuned for CO2/NH3/air-quality gases,
not primarily combustible gas) but a clean, correct response-and-decay
curve to the earlier hand-sanitizer stimulus, confirming it is
functioning correctly.

**All raw reading data logged before tonight's final (22k/10k)
divider is VOID** for calibration purposes — a different divider
ratio changes the ADC codes produced for the same real-world gas
concentration, and the earlier 10k/15k-stage readings don't translate.
Phase 13b (baseline capture) still needs a **full fresh start**,
now under the corrected 22k/10k-divider + `ADC_6db`-attenuation
configuration — tonight's stimulus tests are live-evidence that the
measurement foundation works, not calibration data. No
threshold/baseline placeholder has been replaced with a real number;
that is still Phase 13b's job, to be run against this build.

**Phase 13b tooling WRITTEN 2026-09-17, not yet run against real
hardware:** three new files, all separate from production firmware —
`sensor_esp32_node.ino` is unchanged. (1)
`arduino/sensor_calibration_capture/sensor_calibration_capture.ino`
— data-capture-only sketch, reuses sensor_esp32_node.ino's pin map/
ADC config/`readAveraged()`/warmup gate, no buzzer/voting/WiFi/
thresholds, prints one documented
`<millis_since_boot>,<mq2_avg>,<mq135_avg>,<WARMUP|OK>` line per 1Hz
cycle. (2) `arduino/buzzer_test/buzzer_test.ino` — rewritten (prior
version was stale, targeted the retired Arduino's D8 pin); now GPIO33,
3s boot delay, 5×(1s HIGH/1s LOW), prints "buzzer test complete",
standalone hardware check independent of sensors/calibration. (3)
`tools/calibrate_sensors.py` — reads deliverable 1's serial output
live, tracks running min/max per sensor once past WARMUP, `b`/`p`
keyboard commands mark confirmed baseline/peak, computes
WARN=baseline+0.30×range / DANGER=baseline+0.60×range (same convention
as plan.md's calibration formula) on quit, and prints the result as
copy-pasteable `sensor_esp32_node.ino` placeholder-constant values —
**read-only with respect to the .ino; never writes to it.** Real
Phase 13b workflow now: burn-in -> flash `sensor_calibration_capture.ino`
-> run `calibrate_sensors.py` against its serial output during real
stimulus tests -> developer manually transfers the printed numbers
into `sensor_esp32_node.ino`'s placeholders as a reviewed step. No
burn-in or live stimulus test run yet this session. See logs.md
"Phase 13b — data-capture + calibration tooling written".

**Phase 13b REDESIGN 2026-09-20 — relative (per-boot) baselines
replace fixed absolute thresholds, before any calibration numbers were
filled in.** Multi-day burn-in evidence showed clean-air readings are
stable *within* one power-up but the level shifts *between* boots
(MQ-2 clean-air has started at ~90, ~120, ~180, ~200 raw ADC counts
across different power cycles) — normal MQ heater/thermal/ambient
behavior, not a fault, but incompatible with a single fixed baseline
captured once. `sensor_esp32_node.ino` now: (1) captures a fresh
per-boot baseline (median over `BASELINE_CAPTURE_SECONDS`=60s
following the existing 240s warmup gate, no alarming during either
gate); (2) computes WARN/DANGER at runtime as
`boot_baseline + 0.30/0.60 * CALIBRATED_DELTA` (delta = peak-baseline
from a stimulus test, same session) instead of storing an absolute
threshold; (3) slowly EMA-tracks the baseline afterward under three
safety guards — updates only while below WARN, a per-hour drift cap,
and an absolute per-sensor hard ceiling that is never a function of
the tracked baseline and is the actual backstop against a slow-onset
hazard being "learned away" as normal; (4) sanity-bounds the freshly
captured boot baseline against a plausible clean-air range, falling
back to a stored default if it's implausible (sensor fault, or
booting into an already-contaminated room). All new constants
(`CALIBRATED_DELTA`, `HARD_CEILING`, `BASELINE_MIN/MAX`,
`FALLBACK_BASELINE`, `DRIFT_CAP_PER_HOUR`) are placeholders, same `-1`/
disabled-comparison convention as before — no real calibration has
been run against this structure yet. N-of-M voting, `readAveraged()`,
`ADC_6db` attenuation, and the buzzer/WiFi paths are unchanged.
`tools/calibrate_sensors.py` now prints `CALIBRATED_DELTA` and, via a
new `--history` option that records confirmed baselines across
separate runs, the observed boot-baseline range for the sanity bounds
above — recommended over 3+ separate power cycles, since a single
boot's baseline was exactly the thing this redesign moved away from
trusting alone. See logs.md "Phase 13b redesign — relative (per-boot)
baselines replace fixed absolute thresholds, pre-calibration".

From logs.md "Project state at a glance":

| Phase | Name | Status | Date | Key result |
|---|---|---|---|---|
| 0 | Scaffold and config | COMPLETE | 2026-08-18 | Folder tree + config.yaml, parses clean |
| 1 | Dataset preparation | COMPLETE (rebuilt 2026-09-04) | 2026-09-04 | Leak-free split (verified by name AND content): train 18,627 / val 3,287; 251 hard negatives, 8 categories (+bright_light_textured_wall 30, −4 mislabelled stove duplicates) |
| 2 | Model training | COMPLETE — **v4 PRODUCTION since 2026-09-05** | 2026-08-23; v3 promoted 2026-08-30; v4 trained 2026-09-04, **promoted 2026-09-05** | **v4 live in `models/fire_mnv3.onnx`** (== `fire_mnv3_v4.onnx`, sha `36de3559…`; v3 archived as `fire_mnv3_v3_superseded.*`). ONNX diff 5.99e-05 PASS. fire recall 0.9575 @ 0.30 (margin 0.75 — first widening), smoke recall 0.8511 @ 0.45 argmax-AND (**clears the 0.85 bar for the first time**), val acc 0.9129, held-out bright-wall webcam clip smoke-frame rate 98.0% → 0.0%, no adversarial regression. Training data includes people in frame — **developer decision: keep, disclose** (not "clean"). **Live wall re-check on v4 PENDING.** See §4 item -17 |
| 3 | Edge loop v1 | COMPLETE | 2026-08-24 | camera.py + vision.py + main.py, live webcam test passed |
| 4 | Temporal smoothing | COMPLETE | 2026-08-26 | TemporalVoter (5-of-8, tau=0.70) live; alarm in ~0.17s; FPS 29.5-30.5 |
| 5 | Adversarial evaluation | PARTIAL — functionally closed | 2026-08-30 | 4/5 pass. TV/laptop-fire (7 alarms vs <=2) = documented limitation, mitigated by fusion rule 4's vision-only WARNING cap (live-confirmed Phase 7) |
| 6 | Arduino and sensors | COMPLETE | 2026-08-31 | H1-H9 (H7 skipped). MQ calibration real, thresholds live in config.yaml |
| 7 | Fusion logic | COMPLETE | 2026-08-31 | Live end-to-end Test B: WARNING→CRITICAL (rule 1, gas-confirmed — core safety claim), rule 3 fallback, de-escalation cycles, buzzer sounding throughout, FPS 29.5-30.0 |
| 8 | Agent part 1 | COMPLETE — developer-verified live 2026-09-02 | 2026-09-02 | LangGraph agent + Telegram + 30s reply-CANCEL + simulate_dispatch + main.py POST wiring |
| 8b | Agent part 2 | **BUILT 2026-09-02 — developer live verification PENDING** | 2026-09-02 | Twilio informational SMS-only (own number only; **voice call dropped from scope** — Twilio trial-tier "press any key" gate defeats an informational call), Overpass display-only lookup (406 fixed + re-confirmed), RL-shaped feedback CSV. Needs: developer live drill runs. See §4 |
| 10 | Cloud (S3 dispatch upload) | **COMPLETE — developer-verified live 2026-09-03** | 2026-09-03 | `cloud/uploader.py` log_incident(), wired into BOTH graph.py terminal nodes (`simulate()` and `cancelled()`), **CRITICAL-level only, both outcomes** (WARNING never uploads either way; CRITICAL uploads whether or not the owner cancelled — so the S3 corpus covers false alarms too, for log review/model performance). Four cost-safety measures: single-fire-per-node-per-incident, session upload-count circuit breaker (`aws.max_uploads_per_session: 50`), no retry, bounded packet/JPEG size. **Live-verified via real S3 console check:** one CRITICAL object confirmed in `firewatch-dispatch-arnav` under `device_01/2026/09/02/...`, content matches `dispatch_log.jsonl` format, SIMULATED:true + no-contact note both present; cancelled-CRITICAL archival also confirmed (uploads on both timeout AND cancel, cancelled events excluded from dispatch_log.jsonl but archived to S3 with owner_response text, exactly one upload per incident, WARNING never uploads). See §4 |
| 11 | Dashboard and evaluation | **FUNCTIONALLY COMPLETE — dashboard built 2026-09-03, ember brand pivot + accessibility/card-variety pass 2026-09-04 (browser visual verification still PENDING, see §7); trial-logging helper built 2026-09-03; 12-trial evaluation set (reduced from info.md 4.4's ≥20+≥20) COMPLETE 2026-09-06, 11/12 PASS** | 2026-09-06 | **Architecture changed from plan.md's Streamlit to React + FastAPI, developer instruction** — `dashboard/backend/main.py` (new, independent FastAPI app, port 8001, read-only GET-only) serves `/api/incidents` (alert_feedback.csv), `/api/s3-archive` (all `device_XX/` prefixes, graceful error not 500), `/api/trials` (results.csv or explicit not-found), `/api/fire-station` (reuses `agent/locate.py` verbatim). `dashboard/frontend/` is a new Vite+React app, liquid-glass dark theme (ember-amber brand, 2026-09-04 pivot), plain CSS, Plotly.js charts, 5 tabs (Overview/Live Incidents/Historical Archive/Evaluation Trials/Nearest Fire Station). Latest pass (2026-09-04): full WAI-ARIA tab semantics + keyboard-operable incident cards + icon-backed hazard badges (accessibility fixes from a self-audit), plus per-card visual variety (title icons, priority/quiet metric-card weighting, horizontal `.panel-row` layout variant, cool-tint accent for non-hazard location cards) — see logs.md "Phase 11 accessibility fixes + card-level visual variety pass". `requirements.txt`'s `streamlit` removed. `eval/run_trial.py` (new) is a companion CLI that launches `edge/main.py` as a subprocess and reads its existing stdout to log one row per trial to `eval/results.csv` (info.md 4.4 schema: trial_id/timestamp/trial_label/expected_outcome/actual_outcome/detection_latency_seconds/pass) — zero changes to main.py's detection/fusion code. **2026-09-06: all 12 trials from the reduced plan (plan.md "Day 11 — evaluation trial plan") run against production v4 — 11/12 PASS.** One genuine unresolved FAIL (trial 12: total darkness produces a false vision-only WARNING, `gas_high=False` throughout, new and previously undocumented) plus three findings folded into the closing logs.md entry: a loose D8 buzzer wiring connection silently defeated the physical alarm on trial 2's first attempt (found + fixed, not a code bug); camera autofocus/exposure transients twice inflated `p_fire` enough to move the temporal vote (trials 4 and 11 first attempts, resolved by letting the camera settle); trial 8 showed a non-repeatable WATCH/SAFE split across two identical-condition reruns. `gas_warmup_seconds` was temporarily dropped 240→60 for the trial session and restored to 240 afterward. See logs.md "Phase 11 — 12-trial evaluation run CLOSED" |
| 12 | Documentation | **PARTIAL — `report.md` written 2026-09-06** | 2026-09-06 | Full final report at repo root covering: what FireWatch is, the 8 design changes, architecture, dataset, training results (v1-v4), adversarial evaluation table, the full Phase 11 12-trial results table with every finding disclosed (total-darkness FAIL, buzzer wiring, camera-glitch nuisance, trial 8 non-repeatability), hardware status, cost breakdown, ethics/safety, a consolidated limitations section, and future work. Explicitly discloses the 12-vs-≥20+≥20 trial-count reduction and its reasoning rather than presenting it as the original target. Training curves/confusion-matrix image and a projected production cost-per-unit model were NOT compiled (no real data available this session) — noted as such in the report rather than fabricated. Remaining before Phase 12 can close: developer review of report.md for accuracy/completeness, and the two still-pending Phase 11 items (dashboard visual verification, SAFETY-CRITICAL FPS/buzzer re-verification) it references. |

---

## 4. Most recent key decisions (newest first)

-20. **Demo-readiness check: agent auto-trigger wiring CONFIRMED, no
    code change needed (2026-09-06, distinct from Phase 11 trial
    work):** developer asked ahead of a live demo whether `edge/main.py`
    already auto-triggers `agent/graph.py`'s `run_incident()` on a real
    WARNING/CRITICAL, or whether the two pieces were still manual-only.
    Read the actual code and confirmed **already wired since Phase 8**:
    `main.py`'s hot loop POSTs the REAL fusion state (level, reason,
    vision dict, sensors dict, snapshot) to `agent/server.py`'s
    `/incident` on every WARNING+ frame past the 60s cooldown;
    `server.py` runs `run_incident()` in a FastAPI `BackgroundTasks` task
    so the 60s cancel window never blocks `main.py`; ordering is
    fuse() -> local buzzer -> network POST exactly per info.md 2.2,
    unchanged. The synthetic `"warning"`/`"critical"` args only exist in
    `graph.py`'s standalone `python -m agent.graph` drill CLI, never the
    live path. **Dashboard confirmed genuinely separate processes** — no
    unified launcher exists. Full demo command list (in order):
    `uvicorn agent.server:app --port 8000`,
    `uvicorn dashboard.backend.main:app --port 8001`,
    `cd dashboard/frontend && npm run dev`, `python edge/main.py` — no
    fourth manual agent command needed. See logs.md "Demo-readiness
    check — agent auto-trigger wiring".
-19. **Phase 12 report.md written (2026-09-06):** full final report at
    repo root, doc-maker structure (abstract, 12 numbered sections,
    TOC). Covers everything through the Phase 11 trial run. Headline
    section is §7 (Phase 11 evaluation trials) — discloses the 12-vs-
    ≥20+≥20 reduction explicitly, full 12-trial results table (11/12
    PASS), and all four findings from that run (total-darkness FAIL,
    D8 buzzer wiring, camera-glitch nuisance ×2, trial 8 non-
    repeatability) written up as real findings, not smoothed over.
    Training curves/confusion-matrix image and a production cost-per-
    unit model explicitly flagged as not compiled rather than invented.
    Developer has not yet reviewed report.md for accuracy/completeness.
-18. **Phase 11 — 12-trial evaluation set CLOSED, 11/12 PASS
    (2026-09-06):** reduced trial plan (documented 2026-09-05, see
    item -19's sibling below and plan.md "Day 11 — evaluation trial
    plan") fully run against production v4. One genuine unresolved
    FAIL: trial 12 (lighting changes) — total darkness produced a real
    vision-only WARNING (`p_fire` 0.29→0.96 in ~4s, `gas_high=False`
    throughout, self-de-escalated once light returned), a new,
    previously undocumented limitation, cause suspected (lack of
    near-black training negatives) but unconfirmed. Three additional
    findings, all resolved: (a) trial 2's first attempt reached
    CRITICAL correctly in software but the buzzer stayed silent — a
    loose D8 wiring connection, not a code bug, found and fixed; (b)
    trials 4 and 11 each had a first attempt derailed by a camera
    autofocus/exposure transient inflating `p_fire` enough to move the
    temporal vote (trial 4 combined with a real gas trigger to reach a
    spurious CRITICAL) — both resolved by letting the camera settle
    before rerunning, recorded as a recurring nuisance, not fixed at
    the model/fusion level; (c) trial 8 showed a non-repeatable
    WATCH/SAFE split across two back-to-back identical-condition runs.
    `gas_warmup_seconds` temporarily dropped 240→60 for the trial
    session (developer instruction, sensors already warmed up across
    the day's runs) and restored to 240 immediately after. See logs.md
    "Phase 11 — 12-trial evaluation run CLOSED".
-17. **v4 PROMOTED TO PRODUCTION (2026-09-05) — logs.md "Phase 2
    addendum — v4 promotion decision":** promotion was first held
    because the developer's message carried a placeholder where the
    `export_onnx.py` diff should have been; the developer then supplied
    it — **max |PyTorch − ONNX| logit diff 5.99e-05 on 32 real val
    images, PASS ≤1e-4** (same check as v1/v2/v3). The staged block
    was then run verbatim: v3 → `fire_mnv3_v3_superseded.pt/.onnx/
    .onnx.data` (sha `b15d96df…` preserved), v4 → `models/fire_mnv3.onnx`
    + `.onnx.data` (sha `36de3559…` / `06e77cc5…`, == the v4 files).
    `config.yaml` unchanged (`model_path` already the promoted path;
    0.30 / 0.45 re-verified on v4's sweeps). `edge/vision.py` untouched.
    Nothing deleted. **Remaining: live wall re-check on the promoted
    model.** Also in this entry: (a) people-in-frame decision RESOLVED — keep the 60 webcam
    hard negatives and the held-out clip as captured, with the
    developer and 1-3 other people visible in every inspected frame;
    disclosed plainly in logs.md and queued for the final report; this
    data must never be called "clean"/"controlled"/"background-only";
    (b) full v3-vs-v4 gate table recorded — every gate passes: fire
    recall 0.9541→0.9575 @ 0.30 (margin 0.41→0.75, first widening in
    four checkpoints), fire precision 0.8660→0.8664, smoke recall at the
    production argmax-AND@0.45 rule 0.8284→**0.8511 (first time over
    0.85)**, val acc 0.9031→0.9129, macro F1 0.8967→0.9065, sunset/
    steam/red-clothing 0 fire alarms unchanged, TV-fire 7→6 (still the
    documented limitation, rule-4 mitigated), candle 3→4 (expected to
    alarm), steam smoke-WATCH 21→5 events, held-out bright-wall webcam
    clip smoke-frame rate **98.0%→0.0%**, max p_smoke 0.838→0.478,
    max p_fire on the wall 0.578→0.194; (c) promotion block staged
    (v3 → `fire_mnv3_v3_superseded.*`, v4 → `fire_mnv3.onnx`, shasum
    expectations listed; `config.yaml vision.model_path` already points
    at `models/fire_mnv3.onnx`, no config edit needed); (d) live wall
    re-check protocol written with v3-failure vs v4-pass criteria.
    **Next action for the developer: the live wall re-check
    (`python edge/main.py`, activated shell) — see §7.**
-16. **v4 candidate prepared — bright_light_textured_wall hard
    negatives (2026-09-04, info.md 4.2 step 1; training NOT run):**
    live A/B confirmed the smoke WATCH false positive is the bright-lit
    textured wall/ceiling grid itself (developer in frame = SAFE,
    background alone = WATCH). Developer filmed 30.4 s
    (`data/additional_neutral_training/bright_light_textured_wall/
    IMG_6710.mov`); 30 frames extracted with the SAME
    `scripts/extract_tv_fire_frames.py` logic (new `--output-dir`/
    `--prefix` args, defaults unchanged) into
    `data/hard_negatives/bright_light_textured_wall/` (neutral). New
    `train/check_leakage.py` (name + content md5) closes the standing
    leakage-guard open item; `prepare_data.py --clean` now required to
    rebuild, refuses to append, runs the check last. **The content check
    found 4 stock photos byte-identical between `stove_cooking`
    (neutral) and `gas_stove_flame*` (fire)** — 3 cross-class in v3's
    train, 1 straddling train/val; resolved per plan.md 6.4 (stove
    flame = fire) by moving the neutral copies to
    `hard_negatives_rejected/`. Split rebuilt with v3's exact extra-fire
    args: 21,914 images, leakage PASS. `eval/run_eval.py` now reports
    smoke WATCH events / smoke-frame % / max p_smoke per clip and takes
    `--extra-video`. v3 eval PNGs preserved as `eval/*_v3.png`. **All
    v4 metrics NOT YET MEASURED; v3 still production; promotion NOT
    DECIDED** — developer runs the command block in logs.md "Phase 2
    addendum — bright_light_textured_wall hard negatives folded in".
-15. **Smoke temporal voting added (2026-09-04, closes tonight's live
    finding):** even with the 0.45 gate, WATCH fired on isolated,
    unsustained frames against a patterned background (wall panels,
    ceiling grid). Code read confirmed smoke BYPASSED the Phase 4
    TemporalVoter entirely — `predict_smoothed()` voted only on
    p_fire and `main.py` fed the raw per-frame `smoke` flag straight
    into `fuse()`. Fix per info.md 4.2 step 2 (temporal smoothing, no
    data/retrain): `TemporalVoter.update()` split into `cast(vote)`
    (the N-of-M window) + threshold wrapper; a second instance of the
    SAME class votes on smoke's argmax-AND flag; `fuse()` now takes
    `smoke_sustained`. New `config.yaml vision.smoke_votes_needed: 5`
    (equal to fire — smoke is also on the rule-1 CRITICAL path, the
    failure was single frames so any N≥2 clears it, no smoke sweep
    exists to justify another value; separate key for future sweeps).
    Status line now prints `p_smoke`/`smoke_votes`. Pure-logic voter
    check passed; **live re-check on the same patterned wall PENDING**.
    See logs.md "Smoke temporal voting".
-14. **Smoke decision threshold added, closes the "smoke threshold
    untuned" open item (2026-09-04):** live testing showed spurious
    "WATCH: possible smoke" at p_smoke 0.28-0.44 on a neutral scene —
    argmax with no threshold let smoke win 3-way splits. New
    `eval/smoke_threshold_sweep.py` (sibling of the fire sweep) run by
    the developer on v3: argmax smoke recall 0.8295 / FP 107; val FPs are
    confident (median P 0.69, only 4/107 under 0.50), so val can measure
    the recall cost but not the live gain. **Goals conflict:** only
    thresholds LOOSER than argmax (prob ≥ 0.30-0.40) clear the 0.85
    recall bar and they add 26-78 FPs; every FP-reducing threshold drops
    recall further. Developer chose **0.45 with argmax-AND rule** (smoke
    must win argmax AND P ≥ 0.45; 0.50 was recommended) — cost 1 val
    smoke image (recall → 0.8284), val FP unchanged, all observed live
    0.28-0.44 states removed by construction. `config.yaml
    vision.smoke_decision_threshold`, `edge/vision.py predict()` only;
    no retrain, no fusion/main.py change. See logs.md "Smoke decision
    threshold".
-13. **Phase 11 live fusion-level feed (2026-09-04, edge + backend +
    frontend, closes the standing "live-vs-stale" open item):**
    developer asked why the System Health gauge was stuck at 0% and
    directed that SAFE/WARNING/CRITICAL "all logs" should update live
    on the UI. Root cause: `alert_feedback.csv` (`/api/incidents`) is
    the agent's CANCELLED/TIMEOUT outcome log — `edge/main.py`'s
    `notify_agent()` only fires `if level >= Level.WARNING`, so SAFE/
    WATCH never produce a row, and the old health gauge/stat-pill built
    on that data had no way to ever show recovery. **Did NOT make
    notify_agent fire on every frame** (it does a JPEG encode + network
    POST, gated to WARNING+/60s specifically to protect the 30 FPS
    safety requirement) — instead extended `edge/livelog.py`'s already-
    unconditional, already-cheap 1 Hz `record()` (built in an earlier
    Phase 11 pass specifically as the safe-for-the-hot-loop path) to
    also stamp the fused `level` (SAFE/WATCH/WARNING/CRITICAL, all
    tiers) onto each live sample — `level.name` passed through from the
    SAME `fuse()` call already made that iteration, no second fusion
    implementation. `/api/live-sensors` needed no backend change (reads
    the live-log JSON verbatim). `Overview.jsx`'s System Health hero and
    fusion-timeline stat pill now both prefer the freshest live sample's
    level when present, honestly labeling "current" (live) vs.
    "last incident" (fallback, no live feed) rather than guessing.
    `ast.parse` clean on all three touched Python files; `npm run build`
    + `oxlint` clean. **FPS/buzzer-latency re-verification REQUIRED
    before building further on this** — `edge/main.py`'s hot loop was
    touched (one extra string argument on an existing unconditional
    call), and this project's standing rule requires a live re-check
    after any edge-loop touch, not just a syntax check. See logs.md
    "Phase 11 live fusion-level feed — closes the live-vs-stale open
    item".
-12. **Phase 11 fusion-timeline layout bug fix (2026-09-04, developer
    caught via screenshot):** the prior chart-panel redesign left a
    stale `height: 100%` on the fusion timeline's card (a leftover from
    before it had a header row, when the panel was just a bare title +
    320px chart) — this forced the card to stretch to match the taller
    right-hand stack column while the chart itself stayed a fixed
    260px, producing a large dead gap below the plot and making the
    header+chart read as cramped at the top. Removed `height: 100%`;
    confirmed safe since the right column sizes independently via
    flex+gap. Also relabeled the header stat pill "current" →
    "last incident" — it was showing `mostRecent.level` (the latest
    logged incident), not a live status, so an old stale incident could
    misleadingly read as happening right now. **Real live-vs-stale
    fusion status is NOT yet implemented** — the backend has no live
    fusion-level endpoint (only raw mq2/mq135 via `/api/live-sensors`),
    so this needs either a new backend signal or a defined staleness
    rule before the pill can honestly say "LIVE: SAFE" vs. showing
    history; flagged as an open item rather than faked. `npm run build`
    + `oxlint` clean. **Visual result unseen — developer must
    re-verify.** See logs.md "Phase 11 fusion-timeline layout bug fix".
-11. **Phase 11 chart-panel redesign: fusion timeline + live sensor
    chart (2026-09-04, pure frontend):** developer feedback that these
    two Plotly panels still looked like generic chart-library
    containers and felt too heavy on Overview. Both panels gained a
    real header (icon+title + a compact live-stat pill — current
    fusion level; latest MQ-2/MQ-135 readings), a `.chart-glow-well`
    ambient radial glow behind the chart area (data-driven on the
    fusion chart — tracks the current level color live; steady
    steel-blue on the sensor chart, deliberately NOT data-driven since
    raw ADC values aren't themselves a hazard signal), a soft
    `fill: "tozeroy"` area tint under each line trace, and both charts'
    height cut 320px→260px to reduce visual weight. The sensor chart
    also swapped Plotly's default legend box for a hand-built
    `.chart-legend` (dot + small-caps label) and picked up
    `.glass--cool` (steel-blue border glow, same "instrument data, not
    hazard signal" language as the Fire Station cards). No new color
    hues introduced — reuses `levels.js` colors and the existing
    MQ2/MQ135 tones. `npm run build` + `oxlint` clean, zero new
    warnings. **Visual result unseen — developer must view in a
    browser.** See logs.md "Phase 11 chart-panel redesign — fusion
    timeline + live sensor chart".
-10. **Phase 11 accessibility fixes + card-level visual variety pass
    (2026-09-04, pure frontend, no backend/edge changes):** self-audit
    against `/frontend-audit-design`'s pre-delivery checklist found four
    accessibility gaps, all fixed: `Tabs.jsx` now has full WAI-ARIA tab
    semantics (`role="tablist"/"tab"/"tabpanel"`, `aria-selected`,
    roving tabindex, arrow-key navigation); `LiveIncidents.jsx` cards
    are keyboard-operable (`role="button"`, `tabIndex`, `onKeyDown`);
    `LevelBadge.jsx`'s WARNING/CRITICAL badges now carry an icon (not
    color/animation only); dead `.clickable-row` CSS deleted. Separately,
    developer feedback that every card looked visually identical despite
    the new ember palette drove a card-level variety pass: new
    `src/components/icons.jsx` (hand-written inline SVGs, no new
    dependency), per-card title icons everywhere, `.metric-card--priority`
    (CRITICAL count, conditional on >0) / `.metric-card--quiet` (Cancel
    rate) weight tiers, a horizontal `.panel-row` layout variant (Most
    Recent Event, Fire Station cards) replacing the repeated stacked
    label-above-value pattern, and a `.glass--cool` steel-blue accent for
    the Fire Station cards (non-hazard location data, deliberately
    distinct from ember data cards, still nowhere near `levels.js`'s
    fusion-status colors). `npm run build` + `oxlint` clean, zero new
    warnings. **Visual result unseen — developer must view in a
    browser.** See logs.md "Phase 11 accessibility fixes + card-level
    visual variety pass".
-9. **Phase 11 brand-identity pivot: warm ember palette + typography
    (2026-09-04, developer-requested, pure frontend):** replaced the
    dashboard's neutral chrome accent from blue-cyan to amber-ember
    (`#f59e0b`/`#dc2626`) across every tab — gradient card borders,
    tab/focus/hover glows, skeleton shimmer, chart gridlines, background
    radial glow — with base background moved from near-black navy to
    true warm charcoal/ash. Reasoning: "FireWatch" is a fire-safety
    product: cool blue-cyan chrome and the hazard vocabulary (already
    yellow/amber/red) had no thematic link; ember chrome unifies the
    whole interface under one warm identity while the hazard colors
    still visually out-escalate ambient warmth. **Fusion-level status
    colors in `levels.js` are completely unchanged** (SAFE green, WATCH
    yellow, WARNING/CRITICAL amber/red) — the one deliberately
    untouched piece, so hazard signal is never ambiguous with the new
    decorative chrome. Typography: Oswald added as a display face for
    the "FireWatch" wordmark only (body/data text unchanged); metric-
    number-to-label size/weight contrast increased dashboard-wide.
    `npm run build` + `oxlint` clean, no new warnings; full grep sweep
    confirms no leftover cool-toned literals outside comments. **Visual
    result unseen — developer must view in a browser.** See logs.md
    Phase 11 "brand-identity pivot" entry.
-8. **Phase 11 dashboard frontend design pass — Vision UI structure +
    liquid-glass execution (2026-09-03, pure frontend, no backend/edge
    changes):** full glass design system in `index.css` (blur(22px+)
    glass cards, gradient-ring border, specular top-highlight, large
    continuous radii, hover lift + glow, pulsing CRITICAL glow) applied
    across every tab. New: `LiveSensorChart` (mq2/mq135 from
    `/api/live-sensors` with dotted threshold lines, 3s poll, Overview
    tab only), `StateCard` (shared glass empty/error/offline state,
    replacing plain text everywhere), `CountUp` (metric-card number
    animation). `LiveIncidents` tab **replaced its filterable table with
    a feed-style card list** (developer decision: replace, not toggle) —
    filters unchanged. Overview gained a compact fire-station card
    reusing the existing `/api/fire-station` poll (no second lookup).
    Explicitly a synthesis, not a clone of either reference — see logs.md
    for the full breakdown. `npm run build` + `oxlint` clean, no new
    warnings. **Visual result unseen — developer must view in a browser**,
    see logs.md "How to verify".
-7. **Phase 11 dashboard bug fixes + live-sensors feed (2026-09-03):**
    (a) S3-archive "Unable to locate credentials" root cause:
    `dashboard/backend/main.py` never called `load_dotenv()` at all (the
    agent modules that proved AWS working each load .env themselves and
    none is imported by the dashboard) — fixed with
    `load_dotenv(_REPO_ROOT / ".env")`, `_REPO_ROOT` from `__file__`;
    config.yaml/CSV/live-log paths also anchored there (cwd-independent).
    (b) /api/fire-station "could not be determined" root cause: it DOES
    reuse `agent/locate.py` verbatim (live-confirmed working — <local>
    Fire Station, 1.35 km), but `_fire_station_cache` cached the first
    result unconditionally, so one transient Overpass failure stuck for
    the process lifetime — now caches only `found: True` results.
    (c) NEW `edge/livelog.py` + minimal `edge/main.py` wiring: 1 Hz
    mq2/mq135/p_fire samples via SimpleQueue → daemon writer thread →
    atomic-replace `data/live_sensors.json`, rolling 600 samples
    (config.yaml `live_log:` block). Main-loop cost measured 0.16 µs/frame;
    `record()` placed dead last in the iteration, after alarm+network.
    NEW `/api/live-sensors` returns `{ok, reason, readings[], thresholds{
    mq2_warn, mq2_danger, mq135_warn, mq135_danger}}`. **Developer
    re-verification of FPS (29.5-30) and buzzer latency REQUIRED and
    PENDING before this is safe to build on** — see logs.md Phase 11
    addendum "How to verify". Frontend live-chart tab not built.
-6. **Phase 11 trial-logging helper built, subprocess + stdout-parsing
    approach (2026-09-03, developer instruction to not touch
    `edge/main.py`):** `eval/run_trial.py` launches `python edge/main.py`
    as a real subprocess (cwd = repo root) and parses the fusion level off
    its own existing `format_status()` stdout lines — never imports or
    reimplements fusion/detection logic, never modifies main.py. CLI:
    `--label` (free text) + `--expected` (SAFE/WATCH/WARNING/CRITICAL);
    optional `--target-level` for latency-to-a-specific-level. Logs
    `trial_id, timestamp, trial_label, expected_outcome, actual_outcome,
    detection_latency_seconds, pass` to `eval/results.csv`, append-only,
    header written on first run only. `pass` allows a documented
    adversarial bound (info.md 4.2 TV-fire: WARNING acceptable, CRITICAL
    fails) via a small `ACCEPTABLE_BOUNDS` dict, not auto-derived.
    **Schema cross-checked against the dashboard** (developer instruction):
    `/api/trials` does a schema-free `csv.DictReader` passthrough, but
    `EvaluationTrials.jsx` had guessed `row.outcome ?? row.alarm` for its
    chart before this script existed — fixed the frontend to
    `row.actual_outcome` rather than rename the CSV; **`eval/run_trial.py`'s
    columns are now the schema source of truth**. No trials run yet — see
    logs.md Phase 11 trial-helper entry and §7 open items.
-5. **Phase 11 dashboard built as React + FastAPI, NOT Streamlit
    (2026-09-03, developer-instructed deviation from plan.md, flagged
    before building per info.md 1):** plan.md 4.3/8/9 all specify
    Streamlit for Day 11; developer explicitly asked for a thin
    read-only FastAPI backend (`dashboard/backend/main.py`, port 8001,
    a second independent FastAPI process from `agent/server.py`'s
    port 8000) plus a Vite+React frontend (`dashboard/frontend/`),
    reasoning: visual polish prioritized over build simplicity. Five
    tabs (Overview, Live Incidents, Historical Archive/S3, Evaluation
    Trials, Nearest Fire Station), dark Grafana/Datadog-style theme via
    hand-written CSS (no UI framework added), Plotly.js charts with a
    dark theme override, color language mirrors `edge/fusion.py`'s
    `Level` enum exactly (`src/levels.js`). `/api/fire-station` reuses
    `agent/locate.py`'s Overpass+101/112 logic unmodified — no second
    implementation. `/api/s3-archive` reads every `device_XX/` prefix,
    not hardcoded to `device_01/` (supports the Phase 10 close-out's
    fleet-monitoring idea). Poll cadences: incidents 5s, S3 30s,
    trials/fire-station on tab-focus (60s while active). `streamlit`
    removed from `requirements.txt`. **Verified so far:** Python
    `ast.parse` + import checks on the backend, a clean `npm run build`
    on the frontend (dist/ artifact deleted after). **NOT verified:**
    neither service has been started or viewed in a browser —
    developer will launch both themselves. See logs.md Phase 11.
-4. **Phase 10 CLOSED, developer-verified live (2026-09-03):** real S3
    console check confirmed a genuine CRITICAL incident object in
    `firewatch-dispatch-arnav` under `device_01/2026/09/02/...`, content
    matching `dispatch_log.jsonl` format, SIMULATED:true + no-real-contact
    note both correct. Cancelled-CRITICAL archival (both outcomes upload,
    cancelled events excluded from dispatch_log.jsonl but archived to S3
    with `owner_response: "cancelled by owner within window"`, exactly one
    upload per incident, WARNING never uploads) also confirmed working.
    Both of Phase 10's standing verification drills are done — no longer
    an open item. **File-length soft cap reviewed and deliberately NOT
    flagged as debt:** `agent/graph.py` at 325 lines exceeds info.md 3.3's
    ~200-line guideline, but on review a meaningful fraction of that
    length is docstrings/reasoning comments info.md 3.3 itself requires,
    and the file's actual responsibility (orchestrating agent response
    across Telegram/Twilio/Overpass/feedback/S3 through one fixed-edge
    state machine) was judged coherent enough not to warrant a forced
    split right now — a conscious decision, not an oversight. See logs.md
    Phase 10 closing entry.
-3. **Phase 10 CRITICAL upload extended to the cancelled path (2026-09-02,
    developer decision):** originally only `simulate()` (non-cancelled
    CRITICAL) uploaded to S3; developer asked to also cover
    `CRITICAL + cancelled` (false alarms at CRITICAL severity), since S3
    is the cloud log/retrain corpus and false alarms are exactly the hard
    cases worth having there for log review / model performance. Added
    `agent/graph.py`'s `_incident_packet()` (builds an S3-only packet, NOT
    routed through `tools.simulate_dispatch` — a cancelled event was never
    a dispatch, `dispatch_log.jsonl` still only gets genuine
    non-cancelled writes) and `_upload_critical()` (shared CRITICAL-gate +
    JPEG-read helper, called explicitly from both `cancelled()` and
    `simulate()` — two call sites, each still fires at most once per
    incident since the graph's terminal nodes are mutually exclusive).
    WARNING-level still never uploads, either outcome. See logs.md Phase
    10 addendum.
-2. **Phase 10 S3 upload gated to CRITICAL only (2026-09-02, developer
    decision):** plan.md's Day 10 prompt/original design implied
    uploading on every `simulate()` call (WARNING or CRITICAL timeout
    alike, matching `dispatch_log.jsonl`'s existing symmetry); developer
    explicitly chose CRITICAL-only for cost reasons — WARNING is frequent/
    expected (Phase 8's documented common template-fallback/timeout
    behavior), so it must never touch S3. Local dispatch log still fires
    for both levels unchanged. Four cost-safety measures built per
    developer's zero-tolerance requirement: single fire point (one call
    site in `simulate()`, unreachable more than once per incident — traced
    full graph, no back-edges/loops), session upload-count circuit breaker
    (`config.yaml` `aws.max_uploads_per_session: 50`), no retry (one
    attempt, log+return on failure), bounded file size (~700-900 byte JSON
    packet, single already-saved webcam JPEG, nothing accumulated). See
    logs.md Phase 10 for full detail.
-1. **Cancel window raised 30s -> 60s (2026-09-02, deliberate config
    change):** `config.yaml`'s `fusion.cancel_window_seconds` is now `60`
    — more realistic time to notice and respond to an alert across
    Telegram + SMS before simulated dispatch fires. The wait logic
    (`agent/graph.py` notify_owner/wait) already read this value from
    config dynamically, so no code change there; hardcoded "30-second"/
    "30s" text in `agent/compose.py`'s CRITICAL LLM prompt + deterministic
    template, and comments in `compose.py`/`locate.py`/`tools.py`/
    `server.py`, updated to "60" to match. SMS character budget
    re-confirmed unaffected (SMS templates never mentioned a duration).
    Developer live-timing verification PENDING. See logs.md "Cancel
    window: 30s -> 60s."
0. **Twilio voice call dropped from scope, SMS-only (2026-09-02, argued
   scope change, not silent removal):** live testing showed Twilio
   trial-tier accounts gate every call behind an interactive "press any
   key to accept" prompt before any custom TwiML plays — defeats the
   point of a one-way informational alert call; not worth a paid-account
   upgrade for a prototype. SMS is unaffected by this gate and stays in
   scope, fully working. `agent/escalate.py`'s call-placing code is
   commented out in place (not deleted) for a possible future revisit;
   `send_twilio_alerts()` now always returns `call: False`. The prior
   session's cancel-window extension (base 30s + estimated call-speech
   duration) is reverted — `agent/graph.py`'s `wait` node is back to the
   flat `fusion.cancel_window_seconds` (now 60s as of the 30s->60s change
   above), since no call is ever placed to extend it against. See logs.md
   Phase 8b addendum "Twilio voice call dropped from scope."
1. **Phase 8b BUILT, unverified (2026-09-02):** graph is now verify→locate→
   compose→notify_owner→escalate→wait→{cancelled|simulate}, feedback row
   appended in both terminal nodes.
   - `agent/locate.py`: Overpass `amenity=fire_station` lookup, once per
     incident, haversine-nearest, graceful fallback dict on ANY failure
     (including the still-placeholder 0.0/0.0 coordinates — it refuses to
     query Null Island). DISPLAY-ONLY: station name/number is alert
     content on all channels, NEVER a dial target (info.md 2.1). **406
     root-caused and fixed (Overpass blocks generic User-Agent strings;
     fix adds a descriptive UA + `raise_for_status()`), live-verified
     returning a real named station — see §4 item 0's neighboring
     addendum entries in logs.md.** On genuine lookup failure, the
     fallback line now cites real national emergency numbers (Fire 101 /
     Unified 112, from `config.yaml`'s `emergency_fallback` block) instead
     of bare prose — still never a fabricated station, still DISPLAY-ONLY.
   - `agent/escalate.py`: Twilio **SMS only** (voice call out of scope,
     see item 0 above) via REST/`requests` (no SDK dependency), strictly
     to TWILIO_TO_NUMBER (developer's own phone). One-way informational —
     **Telegram remains the ONLY cancel/confirm mechanism** (permanent
     decision; no IVR/`<Gather>`/webhook, ever). Reuses compose's text —
     no second LLM call. SMS explicitly states the system will not
     contact the fire station. Runs AFTER Telegram so a Twilio failure
     can never delay the primary channel. Real-cost service.
   - `agent/feedback.py`: append-only `eval/alert_feedback.csv`, schema
     METADATA/STATE/ACTION/OUTCOME+REWARD as designed 2026-08-31.
     **Reward mapping decided + flagged:** CANCELLED→−1, TIMEOUT→+1
     (implicit confirmation) — flagged that TIMEOUT is weak evidence and
     0 is arguably better; raw `outcome` column makes remapping lossless.
     Awaiting developer verdict. DATA COLLECTION ONLY — no RL built.
2. **Phase 8 CORE closed (2026-09-02):** both drills developer-confirmed
   live. WARNING: template fallback via strict time-phrase guard
   (expected, accepted design — frequent template fallback is NOT a bug),
   timeout → simulated dispatch. CRITICAL: complete urgent message,
   CANCEL correctly logged, no dispatch. Two bugs fixed same session:
   gpt-oss reasoning-token truncation (max_tokens 200→1024 +
   finish_reason guard) and vague "just now" timestamps (always concrete
   clock time now, required verbatim in LLM output).
3. **Groq model is `openai/gpt-oss-20b`** (llama-3.1-8b-instant deprecated
   2026-08-16; still free, 1,000 req/day). Telegram messages carry NO raw
   technical values — composed sentences + station line + cancel
   instruction only.
4. **Message-tone decision (2026-09-02, argued):** WARNING wording is
   honestly uncertain (real-early-fire vs TV false trigger
   indistinguishable), CRITICAL urgent/direct. Wording only — buzzer
   sounds on BOTH tiers.
5. **Fire station name/number IN alert content, both channels
   (2026-09-01):** Telegram body + Twilio TTS/SMS; never auto-dialed.

---

## 5. Real measured values (logs.md "Live values" + phase results)

| Value | Current |
|---|---|
| **Production model** | **v4 since 2026-09-05** (`models/fire_mnv3.onnx` == `fire_mnv3_v4.onnx`, sha `36de3559…`; `.data` `06e77cc5…`; `fire_mnv3_v4.pt` epoch 10/12). Own leak-free split train 18,678 / val 3,296 (neutral 1,522 / smoke 880 / fire 894). **val acc 0.9129; fire recall 0.9575 @ 0.30 (margin 0.75), precision 0.8664; smoke recall 0.8511 @ 0.45 argmax-AND (0.8545 argmax), smoke FP 109; macro F1 0.9065. ONNX diff 5.99e-05 PASS.** Training webcam negatives contain people in frame (disclosed, kept) |
| **Archived v3** (`fire_mnv3_v3_superseded.*`, sha `b15d96df…`; production 2026-08-30 → 2026-09-05) | val acc 0.9031, fire recall 0.9541 @ 0.30 (margin 0.41), smoke recall 0.8284 @ 0.45 argmax-AND (below bar). Measured on a split later found to hold 4 mislabelled stove images (≤1 in val). Rollback reference, never deleted |
| `fire_decision_threshold` / tau / M / N | 0.30 / 0.70 / 8 / 5 |
| **`smoke_votes_needed`** | **5** (2026-09-04): smoke's per-frame flag now needs 5-of-8 votes (same window as fire) before `fuse()` sees it. Live effect NOT YET MEASURED |
| **`smoke_decision_threshold`** | **0.45** (2026-09-04): frame is smoke only if smoke is argmax winner AND P(smoke) >= 0.45. **Production v4 at this rule: smoke recall 0.8511 — clears the 0.85 bar** (re-verified on v4's sweep; 0.45 stays). Archived v3 was 0.8284 (below bar). Val FP 109 (v4) / 107 (v3) |
| Adversarial (production v4) | sunset/steam/red-clothing 0 fire alarms PASS; TV fire 6 (documented limitation, bar ≤2 never met, rule-4 mitigated); candle 4 (expected to alarm); steam 5 smoke-WATCH events (documented limitation, down from 21); held-out bright-wall webcam clip 0.0% smoke frames, 0 WATCH (people in frame — disclosed) |
| Adversarial (archived v3, for comparison) | sunset/steam/red 0 alarms; TV fire 7; candle 3; steam 21 smoke-WATCH; bright-wall webcam clip 98.0% smoke frames, 4 WATCH (the live failure) |
| **Known limitations (v4, final)** | **TV/laptop fire** — vision-only WARNING cap holds (rule 4), never reaches CRITICAL, 6 alarms vs bar ≤2 never met, mitigated not fixed. **Total darkness (NEW, Phase 11 trial 12, 2026-09-06)** — sustained complete darkness produces a real vision-only false WARNING (`p_fire` 0.29→0.96 over ~4s, `gas_high=False` throughout, self-de-escalates once light returns); root cause suspected (lack of near-black training negatives) but unconfirmed; distinct from and opposite the bright-wall issue the v4 retrain fixed. Both are documented, unresolved-by-design limitations for the final report, not bugs to chase further this cycle |
| Inference FPS | 29.5-30.5 rolling |
| MQ-2 baseline/peak, warn/danger | 57.1 / 252; 115.57 / 174.04 (calibrated, live) |
| MQ-135 baseline/peak, warn/danger | 51.1 / 210 (196 live Test B); 98.77 / 146.44 (calibrated, live) |
| `gas_warmup_seconds` | 240 (2026-08-31 developer decision) |
| `notify_cooldown_seconds` | 60 — consumed by main.py notify_agent() (buzzer has NO cooldown) |
| **Agent config** | `agent:` block — incident_url 127.0.0.1:8000/incident, groq_model openai/gpt-oss-20b, dispatch_log dispatch_log.jsonl, snapshot_dir data/incidents, **8b: overpass_url/radius 7000 m/timeout 8 s, twilio_timeout 10 s, feedback_log eval/alert_feedback.csv** |
| `.env` | GROQ/TELEGRAM verified (@designexperience_bot); **all four TWILIO_* verified present 2026-09-02** (never printed); **AWS_* confirmed working 2026-09-03** (real S3 upload succeeded — see Phase 10 closing entry; values never printed) |
| Phase 8 drills | Both CONFIRMED live 2026-09-02 (WARNING timeout→dispatch, CRITICAL CANCEL→no dispatch). **Phase 8b drills NOT YET RUN** |
| Phase 10 drills | Both CONFIRMED live 2026-09-03 (CRITICAL timeout→S3 upload, CRITICAL CANCEL→S3 upload with cancelled owner_response, no dispatch_log.jsonl line) |
| Alarm protocol / serial | 'A'/'S' → D8; `/dev/cu.usbmodem141011` @ 9600, `mq2,mq135` 1 Hz |
| Buzzer | Fusion-triggered sounding confirmed live 2026-08-31 (WARNING + CRITICAL) |
| Hazard-to-buzzer / phone-alert latency, offline test | NOT YET MEASURED / NOT RUN (Phase 11) |
| `location.*`, `temp_rise_rate` | **PLACEHOLDER — real coordinates needed from developer for 8b Overpass** |

---

## 6. Hardware status

| Item | Status |
|---|---|
| Arduino Uno | Working; Phase 7 'A'/'S' alarm sketch confirmed live |
| MQ-2 (A0) / MQ-135 (A1) | Wired, calibrated 2026-08-31; MQ-135 confirmed undamaged post-incident |
| Buzzer (D8) | Confirmed; fusion-triggered sounding confirmed live |
| DHT22 | CUT — temp_spiking stubbed False |
| LEDs / breadboard | Ordered, not received/wired (H3 red LED not re-confirmed) |
| Webcam | MacBook built-in, confirmed through Phase 5 |
| ESP32-CAM + OV2640 (Phase 13, camera/vision ONLY) | Camera seated, wiring + compile toolchain verified, **first successful flash confirmed 2026-09-09 via MB shield** (GPIO4 LED blink test). No sensor wiring on this board anymore — see two-board split below |
| Plain ESP32 DevKit V1, 30-pin (Phase 13, sensors — NEW 2026-09-16) | MQ-2 → GPIO34, MQ-135 → GPIO35 (ADC1), buzzer → GPIO33, 270Ω/270Ω divider on both sensor lines. **Wiring confirmed working via Serial Monitor** (stable correlated ~100-190 readings); **burn-in IN PROGRESS, not yet stable**; airflow-sensitivity false-positive risk found, unresolved. Supersedes the abandoned ESP32-CAM/MB-shield IO12-15 sensor plan |

---

## 7. Standing open items (carried forward)

- `agent/graph.py` at 325 lines exceeds the 200-line soft cap — this is
  now a REVIEWED, deliberate decision (2026-09-03, see §4 item -4), not
  an open item requiring action. Noted here only so a future session
  doesn't re-flag it as an oversight.
- **Phase 8b verification pending, developer-run:** set real
  `location.latitude/longitude` in config.yaml, then
  `python -m agent.graph warning` (time out → call+SMS+station line+
  feedback row TIMEOUT/+1) and `python -m agent.graph critical` (reply
  CANCEL → feedback row CANCELLED/−1, no dispatch). Twilio is real-cost
  per run. Trial accounts: verified numbers only, trial-notice prefix.
- Timeout-reward verdict open: +1 shipped as instructed default, 0
  flagged as arguably better; `outcome` column keeps remapping lossless.
- Full-pipeline live test (uvicorn + edge/main.py + real flame) not yet
  run; hazard-to-phone-alert latency NOT MEASURED — Phase 11.
- TV/laptop-fire block-bar failure: documented limitation, rule-4
  mitigated — report as limitation, not fixed.
- Fire recall margin trend 1.11→0.88→0.41 pts on v1→v3 — **CLOSED,
  production v4 widened it to 0.75 pts.** Keep watching on any future
  retrain.
- Smoke recall below the 0.85 bar — **CLOSED 2026-09-05 by the v4
  promotion** (0.8511 at the 0.45 argmax-AND rule; v3 was 0.8284).
  Stays in the final report as history.
- **Smoke temporal-voter live re-check: DONE 2026-09-04, failure
  reproduced on v3** (smoke_votes saturated 8/8, WATCH locked) — voter
  and threshold were shown not to be the lever; the v4 retrain is the
  fix. Superseded by the v4 live re-check below.
- `edge/vision.py` 263 / `edge/main.py` 236 lines (soft cap ~200) —
  docstring growth; add no more logic to either.
- File-length soft cap elsewhere (unaffected by the graph.py review
  above): `edge/main.py` 212, `edge/sensors.py` 206 — don't grow either.
- **Phase 11 dashboard built, developer verification pending
  (2026-09-03):** run `uvicorn dashboard.backend.main:app --port 8001`
  and `cd dashboard/frontend && npm run dev`, then view in a browser —
  see logs.md Phase 11 "How to verify" for exact expected behavior per
  tab. Neither service has been started yet.
- **SAFETY-CRITICAL re-verification REQUIRED (2026-09-03, extended
  2026-09-04 — edge/main.py touched twice for the live log):** developer
  must personally confirm (1) FPS still 29.5-30 via main.py's
  rolling-FPS line, (2) WARNING/CRITICAL test still sounds the buzzer
  with no added delay, (3) `/api/live-sensors` returns real advancing
  data **including the new `level` field per sample**, (4) S3-archive
  and fire-station endpoints now work. The 2026-09-04 touch is
  mechanically small (one extra `level.name` string argument passed
  into `live_log.record()`, already an unconditional per-frame call),
  but per this project's own rule any edge-loop touch needs a live
  re-check, not just a syntax check — until then this change is NOT
  safe to build on. See logs.md Phase 11 addendum and "Phase 11 live
  fusion-level feed" entry.
- `edge/main.py` now ~225 lines (soft cap ~200) — do not grow further;
  new live-log logic deliberately lives in `edge/livelog.py` (~120).
- **Phase 11 frontend design pass done, visual review pending
  (2026-09-03, extended 2026-09-04):** run
  `uvicorn dashboard.backend.main:app --port 8001` and
  `cd dashboard/frontend && npm run dev`, open the Vite URL in a
  browser — see logs.md "How to verify" for what to expect per tab
  (glass cards, gradient borders, live sensor chart, feed-style
  incidents, compact fire-station card on Overview) and the 2026-09-04
  entry's "How to verify" for the accessibility/card-variety pass
  specifically (arrow-key tab navigation, keyboard-operable incident
  cards, icon-backed hazard badges, priority/quiet metric-card weight,
  horizontal panel rows, cool-tint Fire Station accent).
- **Phase 11 evaluation trials — NEXT PRIORITY (promotion settled):**
  info.md 4.4's ≥20 hazard + ≥20 non-hazard trials, latency per trial,
  `eval/results.csv` — the logging helper (`eval/run_trial.py`) is
  built and ready (`python eval/run_trial.py --label <name> --expected
  <LEVEL>`). All trials run on production v4. Do the live wall re-check
  first since it uses the same `edge/main.py` session setup.
- Optional seeded `device_02/` fleet-monitoring demo (carried forward
  from Phase 10 close-out) not acted on — `/api/s3-archive` already
  groups by any `device_XX/` prefix present, so it's ready whenever/if
  the developer seeds one. MUST be disclosed as synthetic if done
  (info.md 2.4).
- Use an activated shell, not `conda run`, for live edge-loop testing.
- **v4 PROMOTED 2026-09-05 — retraining detour closed except for the
  live wall re-check (developer-run, PENDING):** `python edge/main.py`
  in an activated shell, same wall / same bright ceiling light as the
  2026-09-04 failure; one background-only pass + one in-frame pass,
  ≥90 s each (Arduino unplugged is fine). Pass = SAFE throughout, or an
  isolated self-clearing WATCH with `smoke_votes` never reaching 5;
  FPS still 29.5-30.5. v3 showed p_smoke 0.44-0.66, `smoke_votes` 8/8,
  WATCH locked. If WATCH still locks on v4, record it as a new open
  item (keep v4 on its val/adversarial merits; do not tune thresholds
  on the spot). Paste observed values for a short follow-up addendum.
- **Final-report disclosure (from the v4 detour):** bright-wall webcam
  hard negatives (60 frames) and the held-out clip include the
  developer and 1-3 other people in frame — kept by developer
  decision, never to be described as "clean"/"controlled"; the 98%→0%
  result is on that clip, not a background-only test. Also report:
  steam sustained smoke-WATCH (v3 21 / v4 5 events), TV-fire unchanged
  limitation, candle expected-to-alarm.
- Leakage guard CLOSED 2026-09-04 (`train/check_leakage.py`, run by
  `prepare_data.py`). Scrape scripts still have no cross-category dedupe.
- MQ-135 weak real-CO2 sensitivity; adversarial clip durations deviate
  from the 30s assumption — report notes.
- Personal stove-flame photos uncollected. `location.address` "NOT SET".
  `.env` AWS keys empty. Twilio real-cost — flag in cost docs (done in
  plan.md/logs.md; repeat in final report).
- `setup.sh`/`setup.ps1` only syntax-checked; stray `anthropic` package
  in conda env (harmless).
- **Phase 13 two-board sensor build (2026-09-16) — three items flagged
  for the next session, none decided yet:** (1) burn-in on the new
  plain ESP32 DevKit is in progress, not confirmed stable — do not
  calibrate against the ~100-190 raw readings observed this session;
  (2) plan.md §5.5's baseline+0.30/0.60 calibration formula was written
  for the Arduino Uno's 10-bit ADC (0-1023) — this hardware is 12-bit
  (0-4095); needs a developer decision on fresh-12-bit-numbers vs.
  re-derive; (3) a real, repeatable airflow/disturbance-triggered
  reading increase (~105→~170-185, both sensors together) was found —
  a genuine false-positive risk for threshold-based alerting; needs
  either a sustained-duration gas check (N-of-M, mirroring the existing
  vision TemporalVoter) or a wider baseline margin, decided with
  `edge/`/`fusion.py` actually open next session, not blind. See
  logs.md "Phase 13 — architecture change: two-board split, MB-shield
  sensor wiring abandoned".
- **Phase 13a JPEG-vs-RGB565 decision — RESOLVED 2026-09-16, capture
  sketch still unwritten:** root-caused via a diagnostic PID read —
  this module's sensor is a GalaxyCore GC2145 (`PID 0x2145`), not an
  OV2640, and has no on-chip JPEG encoder; the "JPEG format is not
  supported" error is a genuine capability limitation, not a config or
  PSRAM-wiring bug (`psramFound()==1` confirmed). Decision: keep
  RGB565 capture (the only format this sensor supports) and JPEG-
  encode on-device in software via `frame2jpg()` before frames reach
  WiFi/Lambda, preserving plan.md §10.2/10.3/10.6/10.7's JPEG-based
  architecture rather than redesigning around raw RGB565 streaming.
  **Sketch written and flashed** (`arduino/cam_node/cam_node.ino`).
  **FPS measured 2026-09-16, target CLEARED — QVGA adopted:** VGA
  frame2jpg() ~480-500ms/frame (~2fps, below plan.md §10.3's 5fps
  target); QVGA (320x240) frame2jpg() ~97-109ms/frame (~10fps),
  exceeding the 5fps target and comfortably inside the ~4s
  TemporalVoter fill-window reasoned from info.md §4.3's real 10s/30s
  alert-latency budget (the 5fps figure itself was never load-bearing
  — see the latency-budget analysis this session). **plan.md §10.3
  still needs updating** to record QVGA + ~10fps as the real
  configuration, replacing the stale VGA/5fps assumption — flagged as
  the next documentation step, not yet done.
  **Narrow-FOV bug — root-caused AND FIXED, developer-confirmed live
  2026-09-16:** `/stream`/`/capture` showed a tight crop (a few inches
  of a door's surface at normal distance) that did NOT widen with
  camera distance, ruling out a lens characteristic. Root-caused
  against the actual `espressif/esp32-camera` driver source
  (`sensors/gc2145.c::set_framesize()`, subsample-mode path — confirmed
  this toolchain's sdkconfig compiles `CONFIG_GC_SENSOR_SUBSAMPLE_MODE=y`):
  the ratio-selection loop unconditionally does
  `if (framesize >= FRAMESIZE_QVGA) i = 1;`, skipping the widest
  available subsample ratio (1/3) for every framesize at or above
  QVGA. At QVGA this lands the loop on the 1/2 ratio, giving a sensor
  read-out window of only 640x480 out of the full 1600x1200 UXGA array
  (~40%) before subsampling 2:1 to the output frame — a genuine driver
  ratio-selection default (not a GC2145-vs-OV2640 register mismatch;
  the subsample path is sensor-agnostic), matching the
  distance-independent symptom exactly.
  **Fixed via Option B (developer-chosen, tried first per instruction):
  a runtime register poke** in `cam_node.ino`'s new `widen_fov_qvga()`,
  called right after `esp_camera_init()` succeeds — replays the
  register writes `set_framesize()` would have issued for the skipped
  1/3 ratio (widening the sensor window to 960x720, 60% of UXGA),
  reached entirely through the driver's own public
  `sensor_t->set_reg()` API (`esp_camera_sensor_get()`) — no forked or
  in-place-edited library copy; the fix lives only in the sketch.
  Maintenance risk explicitly flagged in the sketch's comments: this
  depends on this exact driver version's register map and
  `subsample_cfgs` table, and a future toolchain update could silently
  change or fix the underlying `i=1` skip. **Live-confirmed clean**
  (no reset/brownout after the register writes, normal WiFi connect)
  **and FOV-confirmed by the developer via the same distance-test
  method**: "not as wide as mac camera but good enough" — a real
  improvement over the pre-fix crop, accepted as sufficient, narrower
  than the MacBook webcam used through Phases 0-11. Option A (patched
  local driver copy) was never needed. `frame2jpg()` re-measured
  post-fix at 103ms/frame — unchanged from the pre-fix ~97-109ms range,
  since it encodes the final 320x240 output buffer, not the raw sensor
  window. See logs.md "Phase 13a — FPS measured, narrow-FOV bug
  root-caused and fixed".
- **Phase 13a low-light note — flagged for later, NOT an active task
  (2026-09-16):** live QVGA testing in a dim/dark room showed a dark,
  visibly grainy/noisy image on the ESP32-CAM stream. Plausibly normal
  cheap-CMOS low-light behavior, not confirmed broken or confirmed
  fine either way — no investigation done, none requested yet.
  Relevant prior finding, NOT to be assumed identical or unrelated:
  Phase 11 trial 12 (webcam path) already found total darkness
  producing a false vision-only WARNING (`p_fire` climbing to 0.96,
  `gas_high=False` throughout) — a separate, still-unresolved,
  disclosed limitation. Deliberately deferred until (a) the FOV bug
  above is fixed and (b) normal-lighting QVGA image quality is
  confirmed acceptable, so low-light testing doesn't conflate three
  unknowns at once. When it is picked up, check specifically: (1)
  whether v4 produces sane/stable `p_fire` on this sensor's low-light
  noise profile, not just whether the image looks acceptable, and (2)
  whether this is a new ESP32-CAM-specific weakness or a restatement
  of the Phase 11 trial 12 finding.

---

For full detail, reason, and history, read plan.md, info.md, and logs.md — this file is a summary only and may be stale.
