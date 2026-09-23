// FireWatch Phase 13b — plain ESP32 DevKit V1 sensor board firmware
// (MQ-2 / MQ-135 / buzzer), plan.md §10.0a.
//
// *** MEASUREMENT FOUNDATION FIXED, NOT YET CALIBRATED. ***
// This build incorporates tonight's ADC attenuation fix (see below)
// and is confirmed live-tested (stove-gas and hand-sanitizer stimulus
// tests, both sensors responded correctly -- see logs.md 2026-09-17).
// It is the version to burn-in and calibrate from. Do not treat any
// threshold/baseline/delta constant below as real — every one is a
// clearly marked placeholder pending Phase 13b (post-burn-in
// calibration, to be run against THIS corrected configuration) and
// 13c (N-of-M window decision). See the PLACEHOLDER blocks below.
//
// *** PHASE 13b REDESIGN (2026-09-20): relative (per-boot) baselines,
// not fixed absolute ones. *** Multi-day burn-in evidence (see
// logs.md 2026-09-20) shows clean-air MQ readings are stable WITHIN
// one power-up but the level shifts BETWEEN boots -- MQ-2 clean-air
// has started at ~90, ~120, ~180, ~200 (raw 12-bit ADC counts) across
// different power cycles/positions. This is normal MQ behavior
// (heater thermal state, ambient temperature/humidity, airflow over
// the element at power-up), not a fault. A single fixed
// baseline/threshold captured once during calibration would
// false-alarm on high-baseline boots and under-alarm (miss real
// smoke) on low-baseline boots. So this version captures a fresh
// baseline every boot and stores a CALIBRATED per-sensor DELTA
// (peak-minus-baseline magnitude from a real stimulus test) rather
// than an absolute threshold; WARN/DANGER are computed at runtime as
// this boot's baseline plus 0.30/0.60 of that delta -- same formula
// convention as before, now relative instead of absolute. See the
// safety-tradeoff discussion in the BASELINE TRACKING SAFETY GUARDS
// block below: an adaptive baseline can in principle "learn away" a
// slow-onset hazard as the new normal, which is why guards 2-4 there
// exist and must not be removed or loosened without equal care.
//
// Hardware (confirmed, plan.md §10.0a; divider/topology UPDATED
// 2026-09-17, TWICE, CONFIRMED WORKING as of the second change --
// see plan.md §10.0a and logs.md's ADC floor investigation for full
// reasoning):
//   MQ-2    -> GPIO34 (ADC1, input-only) via 22k(top)/10k(bottom) ohm
//              (x0.3125 scaling, ~1.56V max for a 5V sensor output)
//              divider, breadboard-based (was 10k/15k, was 270/270
//              ohm 1:1 direct jumpers before that, in that order).
//   MQ-135  -> GPIO35 (ADC1, input-only) via 22k(top)/10k(bottom) ohm
//              (x0.3125 scaling) divider, same topology as MQ-2.
//   This divider is CONFIRMED, not to be changed -- the near-zero
//   MQ-135 readings previously suspected as a divider-margin problem
//   were root-caused instead to ADC attenuation mismatch (see
//   analogSetAttenuation() call and comment in setup() below).
//   Buzzer  -> GPIO33 (digital out) -- NOTE: this wire was physically
//              disconnected during burn-in to stop repeated beeping.
//              Firmware cannot fix a disconnected wire -- reconnect it
//              before any buzzer-dependent test.
//   D0 on both sensors is intentionally unwired (analog-only design).
//   ADC is 12-bit (0-4095) on this board -- NEW vs. the retired
//   Arduino Uno's 10-bit ADC. No numeric constant from the old
//   arduino/sensor_node.ino is reused here; only its general structure
//   (periodic analogRead loop) carries over.
//   NOTE: the divider ratio lives entirely in physical hardware --
//   this sketch reads raw 12-bit analogRead() values regardless of
//   what divider produced them, and no divider/resistor value is
//   hardcoded in the sample/vote/threshold logic below. HOWEVER, the
//   divider DOES change what ADC attenuation setting is correct (see
//   setup()) -- a narrower divider output range needs a narrower
//   attenuation window to use the ADC's resolution well, which is
//   exactly tonight's fix. "No firmware change needed" was true for
//   the control-flow logic but not for attenuation; corrected here.
//   All raw readings logged before either 2026-09-17 rewire remain
//   void for calibration purposes -- see logs.md/context.md.
//
// WiFi: connects AND transmits since Stage 3 (2026-09-23). Reuses
// arduino/cam_node.ino's HOME-network pattern/style for consistency
// (credentials + WiFi.begin() + Serial IP printout) and its
// non-blocking ensureWifi() reconnect discipline.
//
// TRANSPORT DECISION (resolves plan.md §10.6 / Phase 13f): a plain
// 1 Hz HTTP POST of one JSON reading to the machine running
// edge/main.py. NOT MQTT -- no broker to run or depend on, and the
// consumer is a single known host. The endpoint lives inside the EDGE
// LOOP, not the dashboard backend, so the detector never depends on an
// optional dev-time process (see edge/wifi_source.py's docstring).
//
// Serial output is UNCHANGED and remains the primary/fallback path:
// eval/verify_live.py, tools/calibrate_sensors.py and edge/sensors.py
// all parse those exact lines. WiFi is an ADDITION, not a replacement,
// at the firmware level -- the host chooses which one it reads via
// config.yaml sensors.transport.
//
// Buzzer path is local-only and WiFi-independent (plan.md §10.5's
// no-WiFi gas-only fallback, info.md's local-alarm-before-network
// principle): it must keep working whether WiFi is mid-connect,
// dropped, or never configured. It is never gated on WiFi.status().
// Stage 3 preserves this absolutely: the POST happens at the very END
// of loop(), strictly AFTER the buzzer write, with a short timeout and
// no retry, and its return value is never consulted by any control
// flow. A dead network costs this board nothing but a logged warning.

#include <WiFi.h>
#include <HTTPClient.h>
#include <ESPmDNS.h>

// ---------------------------------------------------------------------
// Pin map
// ---------------------------------------------------------------------
static const int MQ2_PIN    = 34;  // ADC1_CH6, input-only
static const int MQ135_PIN  = 35;  // ADC1_CH7, input-only
static const int BUZZER_PIN = 33;  // digital out

// ---------------------------------------------------------------------
// Timing
// ---------------------------------------------------------------------
// Polling cadence: the retired Arduino sketch (arduino/sensor_node.ino)
// used a 1 Hz (1000ms) sample loop structurally; reused here as the
// cadence, since nothing about the ADC bit-depth change affects timing.
static const unsigned long SAMPLE_INTERVAL_MS = 1000;

// ---------------------------------------------------------------------
// Stage 3 WiFi transport (2026-09-23)
//
// Every number here is bounded so the POST can never threaten the 1 Hz
// sample cadence or the buzzer. Worst case per loop() iteration is
// HTTP_TIMEOUT_MS, which is deliberately well under SAMPLE_INTERVAL_MS:
// even a totally unresponsive host costs at most 400ms of a 1000ms
// budget, so sampling stays on time and the buzzer (written earlier in
// the same iteration) is already latched before any of this runs.
// ---------------------------------------------------------------------
static const unsigned long HTTP_TIMEOUT_MS = 400;          // hard cap on one POST; << SAMPLE_INTERVAL_MS by design
static const unsigned long WIFI_RETRY_INTERVAL_MS = 5000;  // backoff between reconnect attempts (matches cam_node.ino)
static const unsigned long POST_FAIL_LOG_INTERVAL_MS = 30000;
static const unsigned long WIFI_PER_NETWORK_TIMEOUT_MS = 15000;  // per-network wait in setup(); total boot delay is bounded by this * WIFI_SETUP_ATTEMPTS
static const int WIFI_SETUP_ATTEMPTS = 3;
static const int SUBNET_SCAN_MAX = 20;              // how many host addresses to probe; a hotspot rarely has more than a handful of clients
static const int SUBNET_SCAN_TIMEOUT_MS = 120;      // per-host TCP connect timeout; 20 * 120ms = 2.4s worst case, paid once at connect, never per POST                       // connect tries at boot before giving up and running gas-only (loop() keeps retrying forever)  // rate-limit failure logging so a long outage cannot flood serial at 1Hz

bool wifiWasConnected = false;
unsigned long lastWifiRetryMs = 0;
int wifiNetworkIndex = 0;

// Forward declarations: setup() calls both of these, and it appears
// earlier in this file than their definitions. The Arduino IDE
// auto-generates prototypes, but arduino-cli/PlatformIO builds and any
// plain C++ toolchain do not reliably, so they are explicit here.
static void beginNextWifiNetwork();
static void resolveIngestUrl();          // which entry of WIFI_NETWORKS we are trying
// Resolved ingest base URL ("http://host:port/path"). Built once per
// connection rather than per POST: mDNS resolution is a network round
// trip and doing it at 1Hz would be wasteful and slow.
String ingestUrl = "";
unsigned long lastPostFailLogMs = 0;
unsigned long postFailCount = 0;

// ---------------------------------------------------------------------
// *** WARMUP GATE — SLOPE-BASED, not fixed wall-clock (changed
// 2026-09-20). ***
//
// The original fixed GAS_WARMUP_SECONDS=240 gate (reused as-is from
// config.yaml's gas_warmup_seconds, itself carried over from the
// retired Arduino-era sketch) is NOT long enough for this sensor class
// to reach a stable reading after a genuine power-on. This project's
// own prior calibration history required a full 1-HOUR re-warm window
// after just a power disconnect (logs.md, Phase 6 addendum "H4
// confirmed, re-warm interrupted", 2026-08-30) — a fixed 240s gate on
// THIS board was carried over from that era without re-deriving it,
// and multi-boot baseline captures this session (logs.md "Phase 13b
// calibration — hardware session 1") showed MQ-135 still visibly
// climbing well past 240s+60s post-power-on, consistent with sampling
// an unfinished re-warm transient rather than a stable reading.
//
// A FIXED gate cannot be correct in general regardless of which exact
// number is chosen: the sensor's starting thermal state at power-on
// isn't controllable in deployment (fresh cold boot vs. reboot minutes
// after a brief power blip both need to reach the SAME stable
// endpoint, but from different starting points, so they need different
// amounts of time). Gas-sensor resistance during a power-on transient
// is documented in the literature as following an exponential-decay-
// type curve -- fast initial change, decaying slope, flattening near a
// steady value (see logs.md's Level 2 research citations, 2026-09-20)
// -- so the right thing to gate on is THAT flattening, directly, not a
// guessed duration.
//
// Mechanism: TWO complementary stability checks over a rolling window
// (WARMUP_SLOPE_WINDOW samples), BOTH of which must pass on BOTH
// sensors for WARMUP_STABLE_HOLD_S consecutive seconds:
//
//   (a) JITTER -- mean per-sample |change| across the window.
//       Catches "is this bouncing around a lot."
//   (b) NET DRIFT -- |last sample - first sample| across the window.
//       Catches "is this still steadily heading somewhere."
//
// Check (b) was added 2026-09-21 to fix a real flaw found by replaying
// the recorded cold-start log. Jitter alone is SIGN-BLIND: it averages
// the magnitude of each step and throws away direction, so a slow
// steady decline looks identical to quiet noise. On the real long-rest
// cold start (eval/calibration/warmup_continuous_log_2026-09-20.csv,
// which begins at MQ-2 = 652 and decays), jitter fell to 11.9 -- under
// the threshold of 12 -- by t=25s while the reading was still falling
// from 263 toward its true settled value of ~158. The gate therefore
// cleared at t=55s with the reading at 176, capturing a boot baseline
// ~11% HIGH, mid-decay. Net drift closes that hole because a steady
// decline accumulates a large net change even when each individual
// step is small.
//
// A hard maximum timeout (WARMUP_MAX_SECONDS) remains a mandatory
// backstop -- if a sensor is genuinely faulty and never stabilises,
// the board must not hang in WARMUP forever; it proceeds anyway and
// logs a loud warning so this is visible, never silent.
// ---------------------------------------------------------------------
static const int WARMUP_SLOPE_WINDOW = 10;  // samples (~10s at 1Hz) both checks are computed over

// JITTER threshold. CALIBRATED 2026-09-20 from the continuous cold-boot
// log: once settled (t >= 90s), the jitter noise floor for both sensors
// stayed under ~9 (max observed 8.67, 95th pct ~7.3), while the genuine
// fast warm-up phase (first ~70s) showed 18-30+. 12 sits above settled
// noise (never falsely blocks) and below real warm-up movement.
static const float MQ2_MQ135_WARMUP_SLOPE_THRESHOLD = 12;

// NET-DRIFT threshold. CALIBRATED 2026-09-21 by replaying the same log.
// Constraint from BELOW: the settled tail's own net drift reaches 18
// (MQ-2) / 15 (MQ-135) purely from noise, so anything at or under ~18
// risks a genuinely settled sensor never qualifying -- which would drop
// every boot through to the 1-hour backstop. Constraint from ABOVE:
// larger values readmit the mid-decay capture this check exists to
// prevent. 22 is the smallest value comfortably clear of the measured
// 18 noise ceiling. Measured effect on the recorded cold start, at the
// 60s hold below: gate clears t=110s with MQ-2 at 167 vs. a true
// settled ~158 -- +5.7% error, down from +11% before this check existed.
static const float MQ2_MQ135_WARMUP_DRIFT_THRESHOLD = 22;

// Hold time. Raised 30s -> 60s 2026-09-21 as part of the same fix.
// Swept against the recorded cold start at drift<=22: 30s hold cleared
// at t=80s (+12.0% error), 60s at t=110s (+5.7%), 120s at t=170s
// (-1.3%). 60s is the knee -- it captures most of the accuracy gain
// while keeping total warmup near ~110s, which matters because this
// gate runs before every demo. Going to 120s would buy ~4% more
// accuracy for ~60s more waiting; revisit only if baseline accuracy
// turns out to matter more than startup time.
static const unsigned long WARMUP_STABLE_HOLD_S = 60;

static const unsigned long WARMUP_MAX_SECONDS = 3600;  // hard backstop (1 hour, matching this project's own prior post-disconnect re-warm figure) -- warmup ALWAYS clears by this point even if neither check ever passes, loudly logged as abnormal

float mq2SlopeBuffer[WARMUP_SLOPE_WINDOW];
float mq135SlopeBuffer[WARMUP_SLOPE_WINDOW];
int slopeBufferIndex = 0;
int slopeBufferFilled = 0;  // caps at WARMUP_SLOPE_WINDOW
unsigned long stableSinceMs = 0;  // 0 = not currently stable; set the moment both sensors first read as flat

unsigned long lastSampleMs = 0;
unsigned long bootMs = 0;
bool bootWarmupCleared = false;  // true once warmupElapsed() has returned true at least once this boot -- latches the gate open (see warmupElapsed()) and marks the sample where it cleared, for logging

// ---------------------------------------------------------------------
// Analog read averaging
// ---------------------------------------------------------------------
// Single-sample analogRead() on the ESP32 ADC is known to waver between
// adjacent codes read-to-read, independent of the sensors themselves
// (confirmed this session). Averaging multiple back-to-back samples
// reduces that noise before Phase 13b calibrates thresholds against it.
//
// ADC_SAMPLE_COUNT=8, ADC_SAMPLE_DELAY_MS=2: 8 samples * 2ms = 16ms per
// sensor, ~32ms total for both -- negligible against the 1000ms sample
// cadence (SAMPLE_INTERVAL_MS), so 1Hz reporting is unaffected. 8
// samples is enough to average out single-code ADC jitter without
// smearing across meaningfully different points in time; both are
// named constants here so they're easy to retune later if needed.
static const int ADC_SAMPLE_COUNT = 8;
static const int ADC_SAMPLE_DELAY_MS = 2;

// ---------------------------------------------------------------------
// *** PLACEHOLDER CALIBRATION VALUES — DO NOT TRUST ***
//
// CALIBRATED_DELTA is the ONLY per-sensor number this design still
// needs from a real stimulus test (peak-minus-baseline, measured in
// the SAME calibration session per tools/calibrate_sensors.py's
// updated output) -- there is deliberately no absolute
// baseline/threshold constant anymore; the baseline is captured fresh
// every boot (see BASELINE_CAPTURE_SECONDS below). Every value below
// MUST be replaced with real, measured 12-bit ADC deltas from THIS
// board after burn-in before this firmware is used for anything
// beyond a dry structural test. Do not derive these from the old
// 10-bit Arduino-era numbers -- the ADC range itself changed.
// ---------------------------------------------------------------------
static const int MQ2_CALIBRATED_DELTA_PLACEHOLDER   = 1121;  // gas-stove stimulus, 3 low-baseline runs 2026-09-23 (baseline 81-88, mean of 1089/1167/1108) -- supersedes the 2026-09-21 596 figure, which was measured from an elevated, not-fully-settled baseline (123-157) and understated the true delta; see logs.md
static const int MQ135_CALIBRATED_DELTA_PLACEHOLDER = 572;  // same 3 runs 2026-09-23, mean of 485/566/665 -- NOTE: this sequence is a monotonic upward trend across back-to-back runs (~15 min apart), not random scatter, suspected incomplete recovery between exposures; mean used as the working value but flagged unresolved -- see logs.md

// ---------------------------------------------------------------------
// *** PLACEHOLDER ABSOLUTE HARD CEILINGS — safety-critical, see guard
// 3 in the BASELINE TRACKING SAFETY GUARDS block below. ***
//
// These alarm regardless of whatever the tracked baseline has drifted
// to -- the one guarantee that a slow-onset hazard can never be
// entirely learned away as "normal" by the EMA baseline tracker.
// Must be filled from real calibration data (a level clearly above
// any legitimate baseline+stimulus reading this board has ever
// produced), not guessed.
// ---------------------------------------------------------------------
static const int MQ2_HARD_CEILING_PLACEHOLDER   = 1400;  // FINAL for this prototype (2026-09-23, developer decision): highest of 3 clean gas-stove delta runs (1177/1251/1189) + ~12% margin. None of the 3 runs reached a flat multi-second plateau before decaying, so this is not a confirmed true saturation point -- but a dedicated plateau-finding test was explicitly deferred (time constraint) and this value accepted as adequate for prototype purposes. Not to be re-flagged as an open item; revisit only if new evidence surfaces. See logs.md
static const int MQ135_HARD_CEILING_PLACEHOLDER = 750;   // FINAL for this prototype (2026-09-23, developer decision): highest of 3 clean runs (493/575/675) + ~11% margin, same reasoning and same deliberate deferral as MQ2 above. See logs.md

// ---------------------------------------------------------------------
// *** BOOT-BASELINE PLAUSIBILITY BOUNDS — guard 4, REDESIGNED
// 2026-09-21 to a "trouble state" model. Read this whole block before
// changing any of it. ***
//
// WHAT CHANGED AND WHY (this is a safety-relevant behaviour change):
// guard 4 originally REJECTED an out-of-range boot baseline and
// SUBSTITUTED a stored default, continuing silently. That was wrong in
// a way that only became visible once real multi-location data existed:
//
//   Substituting a LOWER default when the room is genuinely higher
//   guarantees a permanently stuck alarm. Worked example with real
//   numbers from this project: fallback was 98; if a room's true
//   clean-air baseline is ~300 (well within what this hardware
//   demonstrably produces -- see the measured anomalies below), then
//   WARN = 98 + 0.30*delta while every actual reading sits near 300.
//   Every sample reads above WARN, N-of-M voting latches within
//   seconds of capture finishing, and the buzzer never releases. The
//   "safety" guard would itself be the failure.
//
// DIAGNOSIS THAT DROVE THIS (logs.md 2026-09-21): the two anomalous
// baselines recorded during calibration were confirmed to be NORMAL
// SENSOR BEHAVIOUR responding to genuinely different air -- NOT a
// sensor fault and NOT the known loose-wiring issue. Two independent
// lines of evidence:
//   1. Channel-divergence test. An electrical fault (supply sag, bad
//      ground, drifting divider) shifts both ADC channels by a similar
//      RATIO, since they share supply and topology. Measured instead:
//      dining-table anomaly moved MQ-2 5.4x / MQ-135 6.3x
//      (ratio-of-ratios 1.17), while the AC-on anomaly moved MQ-2 4.3x
//      / MQ-135 17.3x (ratio-of-ratios 4.01). A 4x divergence on one
//      occasion and near-parity on another cannot come from a shared
//      electrical fault, but follows directly from the two sensors'
//      different gas selectivity (MQ-135 is far more VOC/NH3/CO2
//      sensitive than MQ-2, so an AC unit's VOC load hits it ~4x
//      harder).
//   2. Within-run stability test. A friction-fit resistor or marginal
//      Dupont contact produces ERRATIC readings (intermittent contact
//      = jitter); the known movement-jump issue shows ~100-count
//      excursions on a ~100 baseline (~100%). The anomalies were the
//      OPPOSITE: spread of 3.7-4.9% (MQ-2) and 10.5-17.8% (MQ-135),
//      i.e. 5-10x TIGHTER than normal clean boots (22.6% / 122.6%). A
//      connection fault cannot make readings more stable. Elevated-
//      but-rock-steady is the signature of real sustained gas.
// Conclusion: the sensors and wiring are working correctly. The bug
// was guard 4 treating "different room" as "broken sensor."
//
// NEW BEHAVIOUR (matches commercial fire-detector practice): when a
// captured baseline falls outside the plausible range, the firmware
// now TRUSTS THE MEASUREMENT (keeps WARN/DANGER correctly scaled to
// the room actually present) and raises a persistent, audible TROUBLE
// state instead of silently substituting. This mirrors how addressable
// smoke detectors handle reaching their drift-compensation limit: they
// signal a trouble/maintenance condition rather than either disabling
// detection or quietly continuing to compensate (EN 54 requires
// compensation be bounded and not silently degrade sensitivity to
// slowly developing fires). The trouble tone is deliberately DISTINCT
// from the gas alarm -- it means "I am running, but my baseline was
// not what I expected; verify the environment," not "gas detected."
//
// The bounds below are therefore now a NOTIFICATION threshold, not a
// rejection threshold. They are set from real data but are no longer
// safety-critical in the way they were when they gated substitution:
// being outside them degrades nothing, it only raises the trouble
// signal. Guard 3 (absolute hard ceiling, independent of baseline)
// remains the real backstop against booting into genuinely hazardous
// air.
//
// Ranges from 6 clean boots at one location (baseline_history.json):
// MQ-2 [64,107], MQ-135 [5,27], widened by a +/-15 margin, then
// further widened on the high side to accommodate a legitimately
// different room -- the measured dining-table (MQ-2 ~460) and AC-on
// (MQ-2 ~370, MQ-135 ~278) states are both real clean-air conditions
// this exact hardware produces, so flagging them as trouble is
// appropriate but treating them as impossible is not.
// ---------------------------------------------------------------------
static const int MQ2_BASELINE_MIN_PLACEHOLDER   = 49;   // 64 - 15 margin
static const int MQ2_BASELINE_MAX_PLACEHOLDER   = 122;  // 107 + 15 margin
static const int MQ135_BASELINE_MIN_PLACEHOLDER = 0;    // 5 - 15 margin, floored at 0 (ADC counts can't be negative)
static const int MQ135_BASELINE_MAX_PLACEHOLDER = 75;   // widened 2026-09-23: a fresh boot this session
                                                           // captured a real MQ135 baseline of 56, above the prior
                                                           // 42 (27+15 margin from the original 6-boot table), and
                                                           // triggered BASELINE_TROUBLE. Per this block's own stated
                                                           // policy (a legitimately different but real clean-air
                                                           // room should be flagged, not treated as impossible),
                                                           // widened to 65 (56 + ~9 margin) rather than tightened
                                                           // around exactly today's reading. NOT re-derived from a
                                                           // fresh multi-boot table -- single new data point, low
                                                           // risk to widen since this bound is notification-only
                                                           // (see block above), not a rejection/substitution gate.
                                                           // See logs.md.

// Trouble-state buzzer pattern (see guard 4 above). Deliberately
// distinct from the solid-on gas alarm: a short double-chirp repeated
// every TROUBLE_BEEP_PERIOD_MS, so it is recognisable as "check the
// installation" rather than "evacuate." Never latches the alarm output
// and never suppresses a real gas alarm -- if gasHigh becomes true,
// the gas alarm takes over the buzzer completely (see loop()).
static const unsigned long TROUBLE_BEEP_PERIOD_MS = 10000;  // how often the trouble chirp repeats
static const unsigned long TROUBLE_BEEP_ON_MS = 80;         // length of each chirp
static const int TROUBLE_BEEP_COUNT = 2;                    // chirps per repetition

// Auto-clear (added 2026-09-21): the trouble state used to be a
// one-way latch -- once set at capture time, nothing ever cleared it,
// so a single implausible boot-baseline capture (e.g. AC transiently
// on during the 60s capture window) would chirp for the ENTIRE
// session even after conditions returned to normal, with no way to
// silence it short of a reboot. That's wrong for the same reason
// guard 4 itself was redesigned: a notification that can never go
// away stops being informative and just becomes noise a demo has to
// talk over. Fix: re-check the LIVE reading (not just the one-time
// captured baseline) against the same plausibility bounds every
// sample; TROUBLE_CLEAR_STREAK consecutic-in-range samples clears the
// flag. Deliberately requires several consecutive normal samples, not
// just one, so a single reading that happens to dip back in-range
// doesn't flap the trouble state on and off.
static const int TROUBLE_CLEAR_STREAK = 30;  // consecutive in-range samples (~30s at 1Hz) needed to auto-clear

bool baselineTroubleActive = false;   // true while the current live reading (or the original capture) is outside the plausible range
unsigned long lastTroubleBeepMs = 0;
int troubleClearStreakCount = 0;      // consecutive in-range samples seen since trouble was last raised

// ---------------------------------------------------------------------
// Boot baseline capture window: after the slope-based warmup gate
// elapses, collect this many more seconds of averaged readings and
// take the MEDIAN per sensor as this boot's baseline. No alarming
// (no threshold comparison, no voting, no buzzer) happens during this
// window -- only warmup and baseline capture are gating conditions on
// this board, and both must clear before any alarm logic runs.
// ---------------------------------------------------------------------
static const unsigned long BASELINE_CAPTURE_SECONDS = 60;
// Capacity for the capture window's sample buffer: one sample per
// SAMPLE_INTERVAL_MS (1Hz) for BASELINE_CAPTURE_SECONDS, plus a small
// margin so a slightly-late loop() iteration can't overflow it.
static const int BASELINE_CAPTURE_MAX_SAMPLES = 90;

// ---------------------------------------------------------------------
// *** BASELINE TRACKING SAFETY GUARDS — safety-critical, read fully
// before changing any of this. ***
//
// SAFETY TRADEOFF: an adaptive baseline that slowly tracks the
// sensor's current reading is exactly what lets a slow-onset hazard
// (e.g. a very gradual smoldering fire, or a slow leak) get "learned"
// as the new normal baseline instead of triggering an alarm -- the
// tracker would chase the rising reading upward and the WARN/DANGER
// thresholds (baseline + 0.30/0.60*delta) would rise right along with
// it, silently raising the bar for what counts as dangerous. That
// failure mode must never be silent, so three independent guards are
// layered on top of the tracker, and ALL THREE must hold for this
// design to be safe -- removing or weakening any one reintroduces the
// slow-onset blind spot:
//
//   1. EMA update runs ONLY when the current reading is below WARN
//      for that sensor (see loop()) -- baseline tracking FREEZES the
//      moment a reading looks even mildly elevated, so a genuine
//      ongoing event stops being absorbed into "normal" the instant
//      it's noticed, rather than continuing to be averaged in.
//   2. MQ2/MQ135_BASELINE_DRIFT_CAP_PER_HOUR_PLACEHOLDER bounds how far the
//      tracked baseline can move per hour even while guard 1 allows
//      updates -- so even a reading that stays just under WARN
//      (by design, or by bad luck) can only pull the baseline up
//      slowly, not jump it.
//   3. HARD_CEILING_PLACEHOLDER (absolute, per sensor, never a
//      function of the tracked baseline) alarms unconditionally once
//      crossed, regardless of what the baseline has drifted to. This
//      is the backstop: even if guards 1+2 are somehow defeated (e.g.
//      a slow-onset event that never crosses WARN before becoming
//      dangerous), the hard ceiling still fires. This is the ONE
//      guard that makes "fully learned away" impossible by
//      construction, so it must never be removed, and must never be
//      computed from the baseline.
//   4. Boot-baseline sanity bounds (MQ*_BASELINE_MIN/MAX_PLACEHOLDER)
//      catch the case where the FIRST value fed to the tracker (this
//      boot's captured baseline) is itself untrustworthy -- either a
//      sensor/wiring fault, or booting into a room that is already
//      contaminated, where "clean-air capture" silently captured a
//      contaminated baseline instead. Falls back to a stored default
//      rather than trusting an out-of-range capture.
//
// Together: guard 1+2 make the *tracked* baseline change slowly and
// only in the safe direction/condition; guard 3 makes the ultimate
// alarm ceiling independent of the tracker entirely; guard 4 makes
// the *starting point* of the tracker itself sanity-checked. No
// individual guard is sufficient alone -- e.g. guard 3 alone (no
// adaptive baseline at all) is exactly the fixed-threshold approach
// this redesign is moving away from, because it false-alarms/misses
// across the observed boot-to-boot baseline shift; guards 1+2 alone
// (no hard ceiling) reopen the "slow-onset learned away" hole this
// comment opened with.
// ---------------------------------------------------------------------
// Derived 2026-09-23 from a 64-min undisturbed indoor capture
// (eval/calibration/drift_20260923_015914.csv), NOT the full window --
// a split-half check (first 32min vs second 32min) showed the
// full-window rate is a still-settling warmup-convergence transient,
// not a stable linear drift (MQ2: -15.6/hr first half vs -5.0/hr
// second half; MQ135: -14.1/hr vs +1.3/hr, sign flip). Using the
// full-window rate would have meant multiplying a transient by a
// margin factor, which bounds nothing real. Basis is therefore the
// SECOND half only (closer to settled state), using max excursion
// from its start (not net drift, since the cap must bound the largest
// single-direction swing, not just start-to-end delta): MQ2 5.16/hr,
// MQ135 1.65/hr. Both x2 margin for single-half-window sampling
// uncertainty (still n=1, not a dedicated settled-state test) ->
// MQ2 ~10, MQ135 ~3, floored to 5 since MQ135's residual is small
// enough that quantization/sample noise likely dominates the raw
// figure. Recommend confirming with a dedicated settled-state
// (post-warmup, no stimulus, ideally 1hr+) capture during a future
// session -- these are a first real estimate, not a settled constant.
static const float MQ2_BASELINE_DRIFT_CAP_PER_HOUR_PLACEHOLDER   = 10;
static const float MQ135_BASELINE_DRIFT_CAP_PER_HOUR_PLACEHOLDER = 5;

// ---------------------------------------------------------------------
// *** RATIO-BASED WARN/DANGER THRESHOLDS (2026-09-23) -- replaces the
// previous absolute "baseline + 0.30/0.50 * CALIBRATED_DELTA" form. ***
//
// WHY THIS CHANGED. The old form added a FIXED ADC-count offset to the
// tracked baseline. That is not physically constant: this sensor's raw
// ADC value is a nonlinear function of sensor resistance Rs (voltage
// divider, ADC = ADC_MAX * RL/(RL+Rs)), and Rs vs gas concentration is
// itself a power law (the MQ datasheets' own ppm curves are log-log in
// Rs/R0). So a fixed +336 ADC delta demands a 71.8% drop in Rs at a
// clean baseline (ADC 150) but only a 66.8% drop at an elevated one
// (ADC 192) -- i.e. the "same" threshold meant different amounts of
// gas depending on the room. Observed live 2026-09-23: a boot into a
// not-yet-cleared room captured baseline 192, which pushed WARN to 528,
// and a real gas exposure peaking at 475 never tripped WARN at all.
//
// Expressing the threshold as a RATIO OF Rs TO THE BASELINE'S Rs is the
// standard approach for MOS sensors (the Rs/R0 normalization the MQ
// datasheets themselves use) and makes the threshold mean the same
// physical thing regardless of what the room's baseline happens to be.
//
// HOW THESE VALUES WERE CHOSEN. Swept against real data rather than
// picked by feel; a LOWER ratio means a LARGER required Rs drop, i.e.
// a HIGHER ADC threshold and LESS sensitivity. At 0.50/0.37:
//   - The 2026-09-23 failed run (baseline 192, peak 475) crosses WARN.
//   - The clean run (baseline 160.5, peak 1041) crosses both.
//   - 0 false positives across all 3853 clean-air samples of the
//     overnight drift log (eval/calibration/drift_20260923_015914.csv),
//     with ~91 counts (MQ2) / ~20 counts (MQ135) of margin above the
//     highest clean-air reading actually observed.
//   - DANGER/WARN gap ratio works out to 1.659 (MQ2) / 1.685 (MQ135),
//     preserving the 1.667 relationship the old 0.30/0.50 span form
//     had, so the WARN->DANGER spacing is unchanged in spirit.
// Deliberately backed off from the raw n=1 derivation (0.7359/0.5598,
// which would have set WARN at only ~215 on a clean baseline) to leave
// real headroom over sensor noise -- developer decision, tuned for
// "flexible, neither twitchy nor harsh" rather than for maximum
// sensitivity.
//
// NOT YET LIVE-VALIDATED against a real stimulus with this formula in
// place, and derived from a single clean calibration run plus the
// overnight clean-air log. MQ2/MQ135_CALIBRATED_DELTA_PLACEHOLDER are
// now UNUSED by the threshold path (kept for reference//documentation
// of what a full stimulus produced). See logs.md.
// ---------------------------------------------------------------------
static const float ADC_MAX = 4095.0;      // 12-bit ADC full scale (analogReadResolution(12) in setup())
static const float WARN_RS_RATIO = 0.50;   // Rs must fall to <=50% of baseline Rs to WARN
static const float DANGER_RS_RATIO = 0.37; // Rs must fall to <=37% of baseline Rs to DANGER

// Converts a tracked baseline (in ADC counts) plus a target Rs ratio
// into the ADC reading at which that ratio is reached. Higher ADC =
// lower Rs = more gas, so a ratio < 1 yields a threshold ADC above the
// baseline. Returns -1 for a non-positive/na baseline so callers can
// treat the threshold as disabled rather than acting on a bogus value.
float ratioThreshold(float baselineAdc, float rsRatio) {
  if (baselineAdc <= 0 || baselineAdc >= ADC_MAX) return -1;
  float rsBase = ADC_MAX / baselineAdc - 1.0;
  return ADC_MAX / (1.0 + rsRatio * rsBase);
}

// Very slow EMA smoothing factor for baseline tracking (0 < alpha <= 1,
// smaller = slower/more inertia). Kept as a separate named constant
// from the drift cap above so cadence and maximum extent can be tuned
// independently; deliberately not a placeholder needing calibration
// data -- this is a smoothing-rate choice, not a measured sensor
// property, so a conservative default (very slow) is set now rather
// than left blank. Revisit if real drift-tracking data suggests it is
// too slow/fast relative to the cap.
static const float BASELINE_EMA_ALPHA = 0.001;

// ---------------------------------------------------------------------
// *** PLACEHOLDER N-of-M sustained-duration window ***
//
// Mirrors edge/vision.py's TemporalVoter pattern: alarm only if N of
// the last M readings exceed threshold, to reject transient airflow/
// disturbance spikes rather than alarming on a single high reading.
// N and M below are NOT decided -- that is Phase 13c's open item, to
// be settled against fusion.py's real logic per the standing project
// rule (no invented numbers ahead of that decision). Kept as named
// constants, not hardcoded into control flow, so they're a one-line
// change once 13c decides.
// ---------------------------------------------------------------------
static const int VOTE_WINDOW_M_PLACEHOLDER = 5;  // CONFIRMED 2026-09-23 by analysis: settled noise floor (+/-27 counts) is far below WARN margin, so this filters the airflow/movement-jump artifact, not ambient jitter -- see logs.md
static const int VOTE_THRESHOLD_N_PLACEHOLDER = 3;  // CONFIRMED 2026-09-23: real gas exposure sustains 39+ consecutive samples above WARN, so 3-of-5 adds negligible detection latency while still requiring more than one hit to pass a brief disturbance -- see logs.md

bool mq2ExceedBuffer[VOTE_WINDOW_M_PLACEHOLDER];
bool mq135ExceedBuffer[VOTE_WINDOW_M_PLACEHOLDER];
int voteBufferIndex = 0;
int voteBufferFilled = 0;  // caps at VOTE_WINDOW_M_PLACEHOLDER

// ---------------------------------------------------------------------
// *** STOPGAP: movement/connection-glitch jump flagging ***
//
// UNRESOLVED (see logs.md "UNRESOLVED: board-movement causes reading
// jumps"): physically moving/bumping this board causes readAveraged()
// output to jump ~100+ counts even with wiring that looks seated.
// Candidate causes, none confirmed: (a) marginal Dupont connections
// under movement, (b) friction-fit (unsoldered) divider resistors,
// (c) residual genuine airflow response the mesh caps diffuse but
// don't eliminate. The user cannot solder/rewire or do a final fixed
// mount right now, so this is a FIRMWARE STOPGAP, not a fix -- the
// real fix is still physical: reseat/replace the Dupont connections,
// push every connector fully home, and avoid touching/bumping the
// board or its surface. This block does NOT solve the problem; it
// only makes glitch events visible in the Serial log instead of
// silently blending into the average, so a human reviewing logs can
// tell "this reading moved because someone bumped the desk" from
// "this reading moved because gas is present." It intentionally does
// NOT feed into mq2Exceeded/mq135Exceeded or the vote buffer above --
// those stay Phase 13b/13c-owned. A real gas event can also look like
// a jump; we choose to flag+log rather than suppress so a genuine
// fast-onset event is never silently thrown away by a filter tuned
// for a wiring glitch.
// ---------------------------------------------------------------------
static const int JUMP_HISTORY_LEN = 5;  // recent accepted averages kept per sensor, for comparison only
static const int JUMP_FLAG_DELTA_PLACEHOLDER = -1;  // TODO(13b-adjacent): ADC-count deviation from recent history that counts as "suspect"; -1 = flagging disabled until a real noise floor is measured (do not guess a number ahead of that)

int mq2History[JUMP_HISTORY_LEN];
int mq135History[JUMP_HISTORY_LEN];
int historyIndex = 0;
int historyFilled = 0;  // caps at JUMP_HISTORY_LEN

// ---------------------------------------------------------------------
// Boot baseline capture state (see BASELINE_CAPTURE_SECONDS above).
// Fills during the capture window right after warmup, then collapses
// to a single per-sensor MEDIAN baseline once and never refills.
// ---------------------------------------------------------------------
int mq2CaptureBuffer[BASELINE_CAPTURE_MAX_SAMPLES];
int mq135CaptureBuffer[BASELINE_CAPTURE_MAX_SAMPLES];
int captureCount = 0;              // samples collected so far this boot
bool baselineCaptured = false;     // true once the median has been taken
unsigned long baselineCaptureStartMs = 0;  // set the moment warmup clears

// Tracked (slowly-adapting) baseline per sensor -- starts at the boot
// median (post sanity-bound check) and creeps per guards 1+2 in the
// BASELINE TRACKING SAFETY GUARDS block above. This is what
// WARN/DANGER are computed relative to at runtime, NOT the original
// boot capture directly, so long-running uptime can track slow,
// legitimate environmental drift within the guarded limits.
float mq2TrackedBaseline = 0;
float mq135TrackedBaseline = 0;
unsigned long lastDriftCapCheckMs = 0;  // last time the per-hour drift cap was reset

// Baseline value the per-hour drift cap measures movement from --
// reset to the tracked baseline's value once per hour (see
// applyBaselineDriftCap()).
float mq2DriftCapAnchor = 0;
float mq135DriftCapAnchor = 0;

// ---------------------------------------------------------------------
// WiFi — HOME context only, same pattern as arduino/cam_node.ino.
// Connect + confirm over Serial only. No MQTT/publish logic: the data
// transport for this board's readings is Phase 13f's open decision
// (plan.md §10.6), not made here.
// ---------------------------------------------------------------------
// Credentials live in secrets.h, which is gitignored and NOT committed.
// Copy secrets.example.h to secrets.h and fill in your own values before
// flashing. Do not put real credentials in this file -- it is tracked.
#include "secrets.h"

void setup() {
  Serial.begin(9600);

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);  // boot silent

  // ADC1 pins (34/35) default to 12-bit width on this core; explicit
  // for clarity given this is a new-to-this-board ADC bit depth.
  analogReadResolution(12);

  // Attenuation: confirmed root cause (2026-09-17) of MQ-135's
  // compressed near-zero readings during WARMUP. The ESP32 core
  // defaults ADC1 to ADC_ATTEN_DB_11 (accurate range ~150-2450mV),
  // but this board's confirmed 22k(top)/10k(bottom) divider only ever
  // produces ~0-1.56V (0.3125x of a 5V sensor output) -- so DB_11
  // wastes most of its accurate window on voltages this divider will
  // never generate, compressing our actual signal into a small,
  // low-resolution slice near the bottom. ADC_6db's accurate range
  // (~150-1750mV) is a much closer match to this divider's real
  // ~0-1.56V output, using the ADC's 12-bit resolution far more
  // effectively across the values we actually see. Live-tested
  // tonight: MQ-2 and MQ-135 both showed clean, correct
  // response-and-decay curves under this setting (see logs.md). If
  // the divider ratio is ever changed again, this setting must be
  // revisited too -- it is matched to 22k/10k's ~1.56V ceiling, not a
  // general-purpose choice.
  analogSetAttenuation(ADC_6db);

  for (int i = 0; i < VOTE_WINDOW_M_PLACEHOLDER; i++) {
    mq2ExceedBuffer[i] = false;
    mq135ExceedBuffer[i] = false;
  }

  for (int i = 0; i < JUMP_HISTORY_LEN; i++) {
    mq2History[i] = 0;
    mq135History[i] = 0;
  }

  for (int i = 0; i < WARMUP_SLOPE_WINDOW; i++) {
    mq2SlopeBuffer[i] = 0;
    mq135SlopeBuffer[i] = 0;
  }

  bootMs = millis();

  Serial.println("FireWatch Phase 13b sensor board -- MEASUREMENT FOUNDATION FIXED, PENDING CALIBRATION (relative per-boot baseline design)");
  Serial.println("NOTE: slope-based warmup gate calibrated 2026-09-20 (MQ2_MQ135_WARMUP_SLOPE_THRESHOLD=12) -- warmup should typically clear well under the 1-hour backstop; see [WARMUP_STABLE]/[WARMUP_BACKSTOP] log line for which path fired this boot.");

  // WiFi: connect + confirm only. This never blocks or gates the buzzer
  // logic in loop() below -- the buzzer safety path does not depend on
  // this succeeding (plan.md 10.5's no-WiFi gas-only fallback).
  //
  // Tries each registered network in turn, up to WIFI_SETUP_ATTEMPTS
  // cycles. A board carried to a venue where the home network is absent
  // must still reach the phone hotspot without a reflash -- that is the
  // entire reason WIFI_NETWORKS is a list.
  Serial.print("Connecting to WiFi (");
  Serial.print(WIFI_NETWORK_COUNT);
  Serial.println(" network(s) registered)");
  // Try each network and KEEP GOING until one both connects AND has the
  // ingest host on it. Connecting is not success: the board will happily
  // join home WiFi while the laptop is on a phone hotspot, and then no
  // POST can ever land. Observed exactly that on 2026-09-23 -- the board
  // sat on Airtel_BeOnMind (192.168.1.11) while the host was on
  // 172.20.10.2. So the host being FINDABLE is the real success test.
  for (int attempt = 0; attempt < WIFI_SETUP_ATTEMPTS * WIFI_NETWORK_COUNT; attempt++) {
    beginNextWifiNetwork();
    unsigned long wifiStartMs = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - wifiStartMs < WIFI_PER_NETWORK_TIMEOUT_MS) {
      delay(500);
      Serial.print(".");
    }
    Serial.println();
    if (WiFi.status() != WL_CONNECTED) continue;

    Serial.print("Connected to ");
    Serial.print(WiFi.SSID());
    Serial.print(", IP: ");
    Serial.println(WiFi.localIP());
    MDNS.begin("firewatch-sensor");
    resolveIngestUrl();
    if (ingestUrl.length() > 0) break;   // host found on this network: done

    Serial.print("[WIFI_NO_HOST] ingest host not found on ");
    Serial.print(WiFi.SSID());
    Serial.println(" -- trying the next registered network");
    WiFi.disconnect();
  }

  if (WiFi.status() == WL_CONNECTED) {
    if (ingestUrl.length() > 0) {
      Serial.println("Transport: 1Hz JSON POST (serial output below is UNCHANGED and remains the fallback path -- the host picks a transport via config.yaml sensors.transport)");
    } else {
      Serial.println("[TRANSPORT_OFF] connected, but no ingest host found on any registered network -- serial only. Detection and buzzer fully functional.");
    }
  } else {
    Serial.println("WiFi not connected -- continuing gas-only/local-only (plan.md 10.5). Detection and buzzer are FULLY functional; only telemetry is affected.");
  }
  wifiWasConnected = (WiFi.status() == WL_CONNECTED);
}

// Takes `samples` consecutive analogRead()s on `pin`, spaced
// ADC_SAMPLE_DELAY_MS apart, and returns their mean as a plain int on
// the same 0-4095 12-bit scale (no normalization/scaling applied).
int readAveraged(int pin, int samples) {
  long total = 0;
  for (int i = 0; i < samples; i++) {
    total += analogRead(pin);
    if (i < samples - 1) delay(ADC_SAMPLE_DELAY_MS);
  }
  return (int)(total / samples);
}

// Compares `latestAvg` against the mean of up to JUMP_HISTORY_LEN prior
// accepted averages for this sensor. Returns true ("suspect") only when
// JUMP_FLAG_DELTA_PLACEHOLDER is a real (non-negative) value AND the
// deviation exceeds it -- mirrors the same -1-disables-comparison guard
// used for MQ2_WARN_THRESHOLD_PLACEHOLDER above, so this cannot
// accidentally fire while still a placeholder. Pure flag -- does not
// modify history or the reading itself.
bool isSuspectJump(int latestAvg, int *history, int filled) {
  if (JUMP_FLAG_DELTA_PLACEHOLDER < 0 || filled == 0) return false;
  long sum = 0;
  for (int i = 0; i < filled; i++) sum += history[i];
  int recentMean = (int)(sum / filled);
  int delta = latestAvg - recentMean;
  if (delta < 0) delta = -delta;
  return delta >= JUMP_FLAG_DELTA_PLACEHOLDER;
}

// Pushes `latestAvg` into `history` at the shared historyIndex. Caller
// must call isSuspectJump() for BOTH sensors before pushing either, so
// a jump is compared against what came before it, not against itself.
void pushHistory(int *history, int latestAvg) {
  history[historyIndex] = latestAvg;
}

// Pushes `latestAvg` into a sensor's slope ring buffer (shared index
// with the other sensor's buffer -- caller pushes both per sample, same
// pattern as pushHistory()/historyIndex above).
void pushSlopeSample(float *buffer, int latestAvg) {
  buffer[slopeBufferIndex] = (float)latestAvg;
}

// Mean of |consecutive differences| across the filled portion of
// `buffer` -- a simple, cheap rolling-slope estimate (average per-
// sample rate of change), not a true derivative/regression fit. Good
// enough to distinguish "still visibly moving" from "flat" without
// floating-point regression math on a microcontroller loop. Returns a
// large sentinel (never counted as flat) until the window has at least
// 2 samples, so the gate can never falsely clear before there's enough
// data to judge.
float rollingSlope(float *buffer, int filled) {
  if (filled < 2) return 1e9;
  // Reconstruct chronological order from the ring buffer starting at
  // the oldest filled slot, since slopeBufferIndex marks the next
  // write position (== oldest entry once the buffer has wrapped).
  int start = (filled < WARMUP_SLOPE_WINDOW) ? 0 : slopeBufferIndex;
  float sumAbsDelta = 0;
  for (int i = 1; i < filled; i++) {
    float prev = buffer[(start + i - 1) % WARMUP_SLOPE_WINDOW];
    float cur = buffer[(start + i) % WARMUP_SLOPE_WINDOW];
    float d = cur - prev;
    if (d < 0) d = -d;
    sumAbsDelta += d;
  }
  return sumAbsDelta / (filled - 1);
}

// |newest - oldest| across the filled window -- the SIGN-AWARE
// companion to rollingSlope(). Where rollingSlope() sums step
// magnitudes and so cannot tell a slow steady decline from quiet
// noise, this cancels opposing steps against each other: pure noise
// wanders back and forth and nets out small, while a sustained
// one-way drift accumulates. See the WARMUP GATE block for the
// measured cold-start case this exists to catch. Same large sentinel
// as rollingSlope() until the window has enough samples to judge.
float rollingNetDrift(float *buffer, int filled) {
  if (filled < 2) return 1e9;
  int start = (filled < WARMUP_SLOPE_WINDOW) ? 0 : slopeBufferIndex;
  float oldest = buffer[start % WARMUP_SLOPE_WINDOW];
  float newest = buffer[(start + filled - 1) % WARMUP_SLOPE_WINDOW];
  float d = newest - oldest;
  return (d < 0) ? -d : d;
}

// Stability-based warmup gate (see WARMUP GATE block above for full
// reasoning and the measured data behind both thresholds). Returns
// true once EITHER (a) BOTH sensors pass BOTH stability checks --
// jitter below MQ2_MQ135_WARMUP_SLOPE_THRESHOLD *and* net drift below
// MQ2_MQ135_WARMUP_DRIFT_THRESHOLD -- continuously for
// WARMUP_STABLE_HOLD_S seconds, or (b) WARMUP_MAX_SECONDS has elapsed
// since boot regardless (mandatory backstop -- logged loudly by the
// caller when this path is the one that fired, since it means a sensor
// never actually stabilised).
//
// Both checks are required because they fail in opposite directions:
// jitter alone passes a slow steady decline (sign-blind), net drift
// alone passes a violently oscillating signal that happens to start
// and end at the same value. Requiring both means the reading must be
// simultaneously quiet AND going nowhere.
bool warmupElapsed() {
  // LATCH (added 2026-09-21, SAFETY-CRITICAL): warmup is a one-way,
  // per-boot transition. Without this the gate is a live re-evaluated
  // condition, so a genuine rising gas event blows through both the
  // jitter and net-drift checks and drags the board BACK into warmup --
  // which suppresses alarming at precisely the moment the alarm is
  // needed. Found 2026-09-21 when a gas-stove stimulus test re-tagged
  // every line WARMUP mid-exposure (see logs.md). Settling is the
  // heater reaching thermal equilibrium; it does not un-happen because
  // gas arrived.
  if (bootWarmupCleared) return true;

  unsigned long elapsedMs = millis() - bootMs;
  if (elapsedMs >= (WARMUP_MAX_SECONDS * 1000UL)) return true;

  float mq2Slope = rollingSlope(mq2SlopeBuffer, slopeBufferFilled);
  float mq135Slope = rollingSlope(mq135SlopeBuffer, slopeBufferFilled);
  float mq2Drift = rollingNetDrift(mq2SlopeBuffer, slopeBufferFilled);
  float mq135Drift = rollingNetDrift(mq135SlopeBuffer, slopeBufferFilled);

  bool bothStableNow = (mq2Slope <= MQ2_MQ135_WARMUP_SLOPE_THRESHOLD) &&
                       (mq135Slope <= MQ2_MQ135_WARMUP_SLOPE_THRESHOLD) &&
                       (mq2Drift <= MQ2_MQ135_WARMUP_DRIFT_THRESHOLD) &&
                       (mq135Drift <= MQ2_MQ135_WARMUP_DRIFT_THRESHOLD);

  if (!bothStableNow) {
    stableSinceMs = 0;  // any unstable sample resets the hold timer
    return false;
  }
  if (stableSinceMs == 0) {
    stableSinceMs = millis();  // just became stable -- start the hold timer
  }
  return (millis() - stableSinceMs) >= (WARMUP_STABLE_HOLD_S * 1000UL);
}

// Returns true once BASELINE_CAPTURE_SECONDS have elapsed since the
// capture window started (called only after warmupElapsed() is true).
bool baselineCaptureElapsed() {
  return (millis() - baselineCaptureStartMs) >= (BASELINE_CAPTURE_SECONDS * 1000UL);
}

// In-place insertion sort + median of the first `count` entries of
// `buffer`. count is small (<= BASELINE_CAPTURE_MAX_SAMPLES, ~90), so
// O(n^2) sort is not a performance concern here; this runs exactly
// once per boot. Median, not mean, so a handful of samples corrupted
// by e.g. a movement glitch (see JUMP_FLAG block) during capture don't
// skew the baseline the way a single large outlier would skew a mean.
int medianOf(int *buffer, int count) {
  for (int i = 1; i < count; i++) {
    int key = buffer[i];
    int j = i - 1;
    while (j >= 0 && buffer[j] > key) {
      buffer[j + 1] = buffer[j];
      j--;
    }
    buffer[j + 1] = key;
  }
  if (count % 2 == 1) return buffer[count / 2];
  return (buffer[count / 2 - 1] + buffer[count / 2]) / 2;
}

// Guard 4 (see BASELINE TRACKING SAFETY GUARDS): checks a freshly
// captured boot baseline against the plausible clean-air range for
// this sensor. Returns true (sane) if the bound pair is still a
// placeholder (min or max < 0) -- mirrors the same -1-disables-check
// convention used elsewhere, so this cannot silently reject every
// boot before real calibration data exists, but also does not enforce
// anything until it does.
bool baselineWithinSanityBounds(int baseline, int minBound, int maxBound) {
  if (minBound < 0 || maxBound < 0) return true;
  return baseline >= minBound && baseline <= maxBound;
}

// Guard 2 (see BASELINE TRACKING SAFETY GUARDS): caps how far
// *tracked (float `baseline`) can move away from *anchor per rolling
// hour. Resets the anchor to the current tracked value once
// BASELINE_DRIFT_CAP_PER_HOUR_PLACEHOLDER's hour window elapses (via
// `anchorSetMs`, updated by the caller). No-op (returns baseline
// unchanged) while the cap is still a placeholder (< 0), same
// disables-until-real-value convention as the rest of this file.
float applyBaselineDriftCap(float baseline, float anchor, float capPerHour) {
  if (capPerHour < 0) return baseline;
  float drift = baseline - anchor;
  if (drift > capPerHour) {
    return anchor + capPerHour;
  }
  if (drift < -capPerHour) {
    return anchor - capPerHour;
  }
  return baseline;
}

// Emits the guard-4 trouble pattern: TROUBLE_BEEP_COUNT short chirps,
// at most once per TROUBLE_BEEP_PERIOD_MS, leaving the buzzer LOW
// afterwards. Called ONLY when there is no active gas alarm (see
// loop()), so it can never mask a real alarm.
//
// The chirps use short blocking delay()s totalling
// TROUBLE_BEEP_COUNT * 2 * TROUBLE_BEEP_ON_MS (= 320ms at the current
// constants). That is deliberate and safe here: it happens at most
// once per 10s, and the sample loop's own budget is 1000ms of which
// readAveraged() already uses ~32ms, so a 320ms occasional excursion
// cannot push a sample past its 1Hz slot. If TROUBLE_BEEP_COUNT or
// TROUBLE_BEEP_ON_MS are raised substantially, re-check that sum
// against SAMPLE_INTERVAL_MS before shipping.
void emitTroubleChirp() {
  if (millis() - lastTroubleBeepMs < TROUBLE_BEEP_PERIOD_MS) {
    digitalWrite(BUZZER_PIN, LOW);
    return;
  }
  lastTroubleBeepMs = millis();
  for (int i = 0; i < TROUBLE_BEEP_COUNT; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(TROUBLE_BEEP_ON_MS);
    digitalWrite(BUZZER_PIN, LOW);
    delay(TROUBLE_BEEP_ON_MS);
  }
}

// Pushes this sample's threshold-exceed bits into the rolling N-of-M
// buffers and returns whether N of the last M readings exceeded
// WARN threshold for each sensor.
void recordVoteAndCheck(bool mq2Exceeded, bool mq135Exceeded,
                         bool *mq2Alarm, bool *mq135Alarm) {
  mq2ExceedBuffer[voteBufferIndex] = mq2Exceeded;
  mq135ExceedBuffer[voteBufferIndex] = mq135Exceeded;
  voteBufferIndex = (voteBufferIndex + 1) % VOTE_WINDOW_M_PLACEHOLDER;
  if (voteBufferFilled < VOTE_WINDOW_M_PLACEHOLDER) voteBufferFilled++;

  int mq2Votes = 0, mq135Votes = 0;
  for (int i = 0; i < voteBufferFilled; i++) {
    if (mq2ExceedBuffer[i]) mq2Votes++;
    if (mq135ExceedBuffer[i]) mq135Votes++;
  }

  *mq2Alarm = (mq2Votes >= VOTE_THRESHOLD_N_PLACEHOLDER);
  *mq135Alarm = (mq135Votes >= VOTE_THRESHOLD_N_PLACEHOLDER);
}

// ---------------------------------------------------------------------
// Try ONE network from WIFI_NETWORKS, advancing the index each call.
//
// Round-robin rather than "always retry [0]": if the home network is out
// of range (a demo venue), insisting on it forever would never reach the
// hotspot entry. Each call advances, so a full cycle covers every
// registered network.
// ---------------------------------------------------------------------
static void beginNextWifiNetwork() {
  if (WIFI_NETWORK_COUNT <= 0) return;
  const WifiNetwork &net = WIFI_NETWORKS[wifiNetworkIndex];
  Serial.print("[WIFI_TRY] ");
  Serial.println(net.ssid);
  WiFi.disconnect();
  WiFi.begin(net.ssid, net.password);
  wifiNetworkIndex = (wifiNetworkIndex + 1) % WIFI_NETWORK_COUNT;
}

// ---------------------------------------------------------------------
// Resolve the ingest endpoint ONCE per connection.
//
// Tries INGEST_HOST (an mDNS ".local" name) first, because a hostname
// survives the laptop having a different IP on every network -- which is
// the whole reason this exists: switching between home WiFi and a phone
// hotspot must not require a reflash. Falls back to
// INGEST_FALLBACK_IP if mDNS does not resolve (some hotspots do not
// forward it).
// ---------------------------------------------------------------------
static void resolveIngestUrl() {
  ingestUrl = "";
  if (INGEST_HOST != NULL && strlen(INGEST_HOST) > 0) {
    // MDNS.queryHost() wants the bare name, without the ".local" suffix.
    String host(INGEST_HOST);
    int dot = host.indexOf(".local");
    String bare = (dot > 0) ? host.substring(0, dot) : host;
    IPAddress resolved = MDNS.queryHost(bare.c_str(), 2000);
    if (resolved != IPAddress((uint32_t)0)) {
      ingestUrl = "http://" + resolved.toString() + ":" + String(INGEST_PORT) + String(INGEST_PATH);
      Serial.print("[INGEST_RESOLVED] ");
      Serial.print(INGEST_HOST);
      Serial.print(" -> ");
      Serial.println(ingestUrl);
      return;
    }
    Serial.print("[INGEST_MDNS_FAIL] could not resolve ");
    Serial.println(INGEST_HOST);
  }
  // Fallback 1: a literal IP, if one is configured AND it is on the
  // subnet we actually joined. A hardcoded IP from a different network
  // (e.g. the home 192.168.1.x while connected to a 172.20.10.x phone
  // hotspot) is worse than useless -- it guarantees every POST fails --
  // so it is only used when the first three octets match ours.
  if (INGEST_FALLBACK_IP != NULL && strlen(INGEST_FALLBACK_IP) > 0) {
    IPAddress fb;
    if (fb.fromString(INGEST_FALLBACK_IP)) {
      IPAddress me = WiFi.localIP();
      if (fb[0] == me[0] && fb[1] == me[1] && fb[2] == me[2]) {
        ingestUrl = "http://" + fb.toString() + ":" + String(INGEST_PORT) + String(INGEST_PATH);
        Serial.print("[INGEST_FALLBACK] using configured IP ");
        Serial.println(ingestUrl);
        return;
      }
      Serial.print("[INGEST_FALLBACK_SKIP] configured IP ");
      Serial.print(INGEST_FALLBACK_IP);
      Serial.print(" is not on this subnet (we are ");
      Serial.print(me);
      Serial.println(") -- trying gateway scan instead");
    }
  }

  // Fallback 2: SCAN THE SUBNET for a host answering on INGEST_PORT.
  //
  // This is what makes a phone hotspot work with no reflash. On a
  // hotspot the laptop's IP is assigned by the phone and differs every
  // session (iOS hands out 172.20.10.x), so neither a hardcoded IP nor
  // -- on many Android/iOS builds, which do not forward mDNS -- a
  // hostname can find it. A hotspot subnet is tiny and the laptop is
  // almost always the first client, so a bounded scan finds it in well
  // under a second.
  //
  // Bounded deliberately: SUBNET_SCAN_MAX hosts, SUBNET_SCAN_TIMEOUT_MS
  // each, and ONLY at (re)connect time -- never per-POST. Worst case is
  // a one-off delay at connection, not a per-loop cost.
  {
    IPAddress me = WiFi.localIP();
    IPAddress gw = WiFi.gatewayIP();
    Serial.print("[INGEST_SCAN] searching ");
    Serial.print(me[0]); Serial.print("."); Serial.print(me[1]); Serial.print(".");
    Serial.print(me[2]); Serial.print(".1-"); Serial.print(SUBNET_SCAN_MAX);
    Serial.print(" for a host on port "); Serial.println(INGEST_PORT);
    for (int host = 1; host <= SUBNET_SCAN_MAX; host++) {
      if (host == me[3]) continue;                 // that's us
      if (host == gw[3]) continue;                 // that's the router/phone
      IPAddress cand(me[0], me[1], me[2], host);
      WiFiClient probe;
      if (probe.connect(cand, INGEST_PORT, SUBNET_SCAN_TIMEOUT_MS)) {
        probe.stop();
        ingestUrl = "http://" + cand.toString() + ":" + String(INGEST_PORT) + String(INGEST_PATH);
        Serial.print("[INGEST_FOUND] ");
        Serial.println(ingestUrl);
        return;
      }
      probe.stop();
    }
    Serial.println("[INGEST_SCAN_FAIL] no host answering on this subnet -- is edge/main.py running with sensors.transport: wifi, and is the laptop on THIS network?");
  }

  Serial.println("[INGEST_DISABLED] endpoint unresolved -- telemetry off, gas detection and buzzer unaffected");
}

// ---------------------------------------------------------------------
// Non-blocking WiFi keepalive. Copied in spirit from cam_node.ino:111 --
// same board family, same network, same failure modes, so the same
// pattern rather than a second invented one.
//
// NEVER blocks: a disconnected board retries at most once per
// WIFI_RETRY_INTERVAL_MS and returns false immediately the rest of the
// time. loop() therefore runs at full 1 Hz whether WiFi is up or not.
// ---------------------------------------------------------------------
static bool ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiWasConnected) {
      wifiWasConnected = true;
      Serial.print("[WIFI_RESTORED] reconnected, SSID: ");
      Serial.print(WiFi.SSID());
      Serial.print(", IP: ");
      Serial.println(WiFi.localIP());
      // A new connection may be a DIFFERENT network with a different
      // laptop IP, so the endpoint is re-resolved rather than reused.
      MDNS.begin("firewatch-sensor");
      resolveIngestUrl();
    }
    return true;
  }

  if (wifiWasConnected) {
    wifiWasConnected = false;
    Serial.println("[WIFI_LOST] connection dropped -- retrying. Gas detection and buzzer are UNAFFECTED (local-only); only telemetry to the edge loop stops.");
  }

  unsigned long now = millis();
  if (now - lastWifiRetryMs >= WIFI_RETRY_INTERVAL_MS) {
    lastWifiRetryMs = now;
    beginNextWifiNetwork();  // cycles through every registered network
  }
  return false;
}

// ---------------------------------------------------------------------
// POST one reading as JSON to the edge loop. Fire-and-forget.
//
// SAFETY CONTRACT -- this function may not affect anything else:
//   * called at the very END of loop(), after the buzzer is already set
//   * bounded by HTTP_TIMEOUT_MS (<< SAMPLE_INTERVAL_MS)
//   * no retry (the next reading is 1s away and more current anyway --
//     retrying stale data would be worse than dropping it)
//   * return value deliberately ignored by the caller
//   * failures are rate-limited to one log per POST_FAIL_LOG_INTERVAL_MS
//     so a long outage cannot flood the serial line that
//     eval/verify_live.py and edge/sensors.py are parsing
//
// `state` is the same string the serial line prints, and the six
// threshold fields are the same values -- one source of truth for both
// transports. warn/danger arrive as PARAMETERS because they are locals
// computed inside loop() (not globals like the tracked baselines), so
// they must be passed in rather than reached for. Sending -1 baselines pre-capture is avoided by simply
// omitting thresholds when they are not yet valid: edge/wifi_source.py
// ignores a partial threshold set rather than half-applying it.
// ---------------------------------------------------------------------
static void postReading(int mq2Raw, int mq135Raw, const char *state,
                        bool includeThresholds,
                        float warnMq2, float dangerMq2,
                        float warnMq135, float dangerMq135) {
  if (!ensureWifi()) return;              // no link; nothing to do
  if (ingestUrl.length() == 0) return;    // endpoint unresolved/disabled

  char body[320];
  if (includeThresholds) {
    snprintf(body, sizeof(body),
             "{\"mq2\":%d,\"mq135\":%d,\"state\":\"%s\","
             "\"baseline_mq2\":%.2f,\"warn_mq2\":%.2f,\"danger_mq2\":%.2f,"
             "\"baseline_mq135\":%.2f,\"warn_mq135\":%.2f,\"danger_mq135\":%.2f}",
             mq2Raw, mq135Raw, state,
             mq2TrackedBaseline, warnMq2, dangerMq2,
             mq135TrackedBaseline, warnMq135, dangerMq135);
  } else {
    snprintf(body, sizeof(body), "{\"mq2\":%d,\"mq135\":%d,\"state\":\"%s\"}",
             mq2Raw, mq135Raw, state);
  }

  HTTPClient http;
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(ingestUrl)) {
    http.end();
    return;
  }
  http.addHeader("Content-Type", "application/json");
  int code = http.POST((uint8_t *)body, strlen(body));
  http.end();

  if (code != 200) {
    postFailCount++;
    unsigned long now = millis();
    if (now - lastPostFailLogMs >= POST_FAIL_LOG_INTERVAL_MS || lastPostFailLogMs == 0) {
      lastPostFailLogMs = now;
      Serial.print("[POST_FAIL] ingest POST failing (HTTP ");
      Serial.print(code);
      Serial.print(", ");
      Serial.print(postFailCount);
      Serial.println(" total) -- gas detection and buzzer UNAFFECTED; check that edge/main.py runs with sensors.transport: wifi, and that the laptop is on THIS network (campus WiFi often blocks device-to-device traffic -- use a phone hotspot)");
    }
  } else if (postFailCount > 0) {
    Serial.print("[POST_OK] ingest POST recovered after ");
    Serial.print(postFailCount);
    Serial.println(" failures");
    postFailCount = 0;
  }
}

void loop() {
  unsigned long now = millis();
  if (now - lastSampleMs < SAMPLE_INTERVAL_MS) return;
  lastSampleMs = now;

  int mq2Raw = readAveraged(MQ2_PIN, ADC_SAMPLE_COUNT);
  int mq135Raw = readAveraged(MQ135_PIN, ADC_SAMPLE_COUNT);

  // Stopgap movement/glitch flagging -- see comment block near
  // JUMP_FLAG_DELTA_PLACEHOLDER above. Flags only; never suppresses a
  // reading, so a real gas event can never be silently filtered out.
  bool mq2Suspect = isSuspectJump(mq2Raw, mq2History, historyFilled);
  bool mq135Suspect = isSuspectJump(mq135Raw, mq135History, historyFilled);
  if (mq2Suspect || mq135Suspect) {
    Serial.print("[SUSPECT_JUMP] mq2=");
    Serial.print(mq2Raw);
    Serial.print(mq2Suspect ? "(flagged)" : "");
    Serial.print(" mq135=");
    Serial.print(mq135Raw);
    Serial.println(mq135Suspect ? "(flagged)" : "");
  }
  pushHistory(mq2History, mq2Raw);
  pushHistory(mq135History, mq135Raw);
  historyIndex = (historyIndex + 1) % JUMP_HISTORY_LEN;
  if (historyFilled < JUMP_HISTORY_LEN) historyFilled++;

  Serial.print(mq2Raw);
  Serial.print(",");
  Serial.print(mq135Raw);

  // Feed the slope-based warmup gate's rolling window BEFORE checking
  // warmupElapsed(), so this sample counts toward the slope estimate
  // even on the very call that clears the gate -- and so slope tracking
  // still runs (harmlessly) after warmup clears too, since the buffers
  // are small and cheap to keep updating.
  bool wasWarmupElapsedBeforeThisSample = (bootWarmupCleared);
  pushSlopeSample(mq2SlopeBuffer, mq2Raw);
  pushSlopeSample(mq135SlopeBuffer, mq135Raw);
  slopeBufferIndex = (slopeBufferIndex + 1) % WARMUP_SLOPE_WINDOW;
  if (slopeBufferFilled < WARMUP_SLOPE_WINDOW) slopeBufferFilled++;

  bool warmupNowElapsed = warmupElapsed();
  if (!wasWarmupElapsedBeforeThisSample && warmupNowElapsed) {
    bootWarmupCleared = true;
    unsigned long elapsedS = (millis() - bootMs) / 1000UL;
    if (elapsedS >= WARMUP_MAX_SECONDS) {
      // Cleared via the hard backstop, not the slope condition -- this
      // means a sensor never visibly flattened within WARMUP_MAX_SECONDS,
      // which is abnormal and must be loud, not silently accepted.
      Serial.println("[WARMUP_BACKSTOP] warmup gate cleared via WARMUP_MAX_SECONDS timeout, NOT slope stability -- a sensor may not be reaching a stable reading; treat this boot's calibration data with extra caution");
    } else {
      Serial.print("[WARMUP_STABLE] warmup gate cleared via slope stability after ");
      Serial.print(elapsedS);
      Serial.println("s");
    }
  }

  if (!warmupNowElapsed) {
    Serial.println(",WARMUP");
    // Telemetry during warmup too: the host shows "board warming up"
    // rather than "no sensor" (edge/main.py surfaces WARMUP as GATED).
    // No thresholds yet -- none exist before baseline capture.
    postReading(mq2Raw, mq135Raw, "WARMUP", false, 0, 0, 0, 0);
    return;  // readings not trusted yet -- no capture, no voting, no buzzer during warmup
  }

  if (!baselineCaptured) {
    if (baselineCaptureStartMs == 0) {
      baselineCaptureStartMs = millis();  // capture window starts the instant warmup clears
    }
    if (captureCount < BASELINE_CAPTURE_MAX_SAMPLES) {
      mq2CaptureBuffer[captureCount] = mq2Raw;
      mq135CaptureBuffer[captureCount] = mq135Raw;
      captureCount++;
    }
    Serial.println(",BASELINE_CAPTURE");
    postReading(mq2Raw, mq135Raw, "BASELINE_CAPTURE", false, 0, 0, 0, 0);

    if (baselineCaptureElapsed() && captureCount > 0) {
      int mq2Median = medianOf(mq2CaptureBuffer, captureCount);
      int mq135Median = medianOf(mq135CaptureBuffer, captureCount);

      // Guard 4 (redesigned 2026-09-21 -- see the BOOT-BASELINE
      // PLAUSIBILITY BOUNDS block above for the full reasoning and the
      // diagnostic evidence behind the change): an implausible boot
      // baseline raises a persistent audible TROUBLE state but the
      // measured value is STILL USED. Substituting a stored default
      // here was the previous behaviour and was actively dangerous --
      // a lower substituted baseline in a genuinely higher-baseline
      // room guarantees a permanently stuck alarm. Trusting the
      // measurement keeps WARN/DANGER correctly scaled to the room
      // that is actually present; guard 3's absolute hard ceiling
      // remains the backstop for genuinely hazardous boot-time air.
      bool mq2Sane = baselineWithinSanityBounds(mq2Median, MQ2_BASELINE_MIN_PLACEHOLDER, MQ2_BASELINE_MAX_PLACEHOLDER);
      bool mq135Sane = baselineWithinSanityBounds(mq135Median, MQ135_BASELINE_MIN_PLACEHOLDER, MQ135_BASELINE_MAX_PLACEHOLDER);

      if (!mq2Sane || !mq135Sane) {
        baselineTroubleActive = true;
        Serial.print("[BASELINE_TROUBLE] captured baseline outside expected range -- USING IT ANYWAY (not substituting), raising trouble signal. mq2=");
        Serial.print(mq2Median);
        Serial.print(" expected[");
        Serial.print(MQ2_BASELINE_MIN_PLACEHOLDER);
        Serial.print(",");
        Serial.print(MQ2_BASELINE_MAX_PLACEHOLDER);
        Serial.print("] mq135=");
        Serial.print(mq135Median);
        Serial.print(" expected[");
        Serial.print(MQ135_BASELINE_MIN_PLACEHOLDER);
        Serial.print(",");
        Serial.print(MQ135_BASELINE_MAX_PLACEHOLDER);
        Serial.println("] -- verify the environment (different room, HVAC state, or real contamination at boot).");
      }

      mq2TrackedBaseline = (float)mq2Median;
      mq135TrackedBaseline = (float)mq135Median;
      mq2DriftCapAnchor = mq2TrackedBaseline;
      mq135DriftCapAnchor = mq135TrackedBaseline;
      lastDriftCapCheckMs = millis();
      baselineCaptured = true;

      Serial.print("BASELINE_CAPTURE done: mq2=");
      Serial.print(mq2TrackedBaseline);
      Serial.print(" mq135=");
      Serial.println(mq135TrackedBaseline);
    }
    return;  // no alarming until baseline capture completes
  }

  // Trouble auto-clear (see TROUBLE_CLEAR_STREAK above): re-check the
  // TRACKED baseline (the EMA-smoothed quantity, not a single noisy
  // raw sample -- the correct like-for-like comparison against the
  // originally-flagged capture, which was also a smoothed median, not
  // a raw reading) against the same plausibility bounds every sample.
  // Only runs while trouble is active, so it costs nothing otherwise.
  if (baselineTroubleActive) {
    bool mq2NowSane = baselineWithinSanityBounds((int)mq2TrackedBaseline, MQ2_BASELINE_MIN_PLACEHOLDER, MQ2_BASELINE_MAX_PLACEHOLDER);
    bool mq135NowSane = baselineWithinSanityBounds((int)mq135TrackedBaseline, MQ135_BASELINE_MIN_PLACEHOLDER, MQ135_BASELINE_MAX_PLACEHOLDER);
    if (mq2NowSane && mq135NowSane) {
      troubleClearStreakCount++;
      if (troubleClearStreakCount >= TROUBLE_CLEAR_STREAK) {
        baselineTroubleActive = false;
        troubleClearStreakCount = 0;
        Serial.println("[BASELINE_TROUBLE_CLEARED] tracked baseline back within expected range for a sustained period.");
      }
    } else {
      troubleClearStreakCount = 0;  // any out-of-range sample resets the clear streak
    }
  }

  // Relative thresholds: WARN/DANGER computed from THIS boot's
  // tracked baseline plus 0.30/0.50 of the calibrated stimulus delta
  // -- same formula convention as the retired absolute design, now
  // relative. Disabled (never exceeded) while CALIBRATED_DELTA is
  // still a placeholder, same -1-disables convention used throughout.
  //
  // DANGER multiplier changed 0.60 -> 0.50 (2026-09-23, deliberate,
  // developer decision): prioritizes catching a real fire sooner over
  // minimizing false alarms -- this is a real tradeoff, not a free
  // improvement. Industry LEL gas-detector convention places the high
  // alarm at 50-60% of a reference span (60% is the conservative end),
  // so 50% is a deliberate, sensitivity-favoring choice, not a
  // correction of an error. Compounds with two other known open risks
  // in the SAME direction (more sensitive, more false-alarm-prone):
  // the hard ceiling guard is still unset (MQ2/MQ135_HARD_CEILING_
  // PLACEHOLDER = -1) and MQ135's calibrated delta is itself still
  // trending (see its PLACEHOLDER comment above) -- re-review this
  // multiplier once both of those are resolved. See logs.md.
  float mq2Warn = ratioThreshold(mq2TrackedBaseline, WARN_RS_RATIO);
  float mq2Danger = ratioThreshold(mq2TrackedBaseline, DANGER_RS_RATIO);
  float mq135Warn = ratioThreshold(mq135TrackedBaseline, WARN_RS_RATIO);
  float mq135Danger = ratioThreshold(mq135TrackedBaseline, DANGER_RS_RATIO);

  bool mq2Exceeded = (mq2Warn > 0) && (mq2Raw >= mq2Warn);
  bool mq135Exceeded = (mq135Warn > 0) && (mq135Raw >= mq135Warn);

  // Guard 3: absolute hard ceiling, independent of the tracked
  // baseline -- alarms unconditionally so a slow-onset hazard can
  // never be fully learned away by the EMA tracker below. Disabled
  // (never fires) while still a placeholder.
  bool mq2HardCeiling = (MQ2_HARD_CEILING_PLACEHOLDER >= 0) && (mq2Raw >= MQ2_HARD_CEILING_PLACEHOLDER);
  bool mq135HardCeiling = (MQ135_HARD_CEILING_PLACEHOLDER >= 0) && (mq135Raw >= MQ135_HARD_CEILING_PLACEHOLDER);

  // Guard 1: EMA baseline update runs ONLY when the reading is below
  // WARN -- freezes baseline tracking the moment a reading looks even
  // mildly elevated, so an ongoing event can't be averaged into
  // "normal" once noticed.
  if (!mq2Exceeded) {
    mq2TrackedBaseline = (1.0 - BASELINE_EMA_ALPHA) * mq2TrackedBaseline + BASELINE_EMA_ALPHA * mq2Raw;
  }
  if (!mq135Exceeded) {
    mq135TrackedBaseline = (1.0 - BASELINE_EMA_ALPHA) * mq135TrackedBaseline + BASELINE_EMA_ALPHA * mq135Raw;
  }

  // Guard 2: per-hour drift cap, re-anchored once per rolling hour.
  if (millis() - lastDriftCapCheckMs >= 3600000UL) {
    mq2DriftCapAnchor = mq2TrackedBaseline;
    mq135DriftCapAnchor = mq135TrackedBaseline;
    lastDriftCapCheckMs = millis();
  }
  mq2TrackedBaseline = applyBaselineDriftCap(mq2TrackedBaseline, mq2DriftCapAnchor, MQ2_BASELINE_DRIFT_CAP_PER_HOUR_PLACEHOLDER);
  mq135TrackedBaseline = applyBaselineDriftCap(mq135TrackedBaseline, mq135DriftCapAnchor, MQ135_BASELINE_DRIFT_CAP_PER_HOUR_PLACEHOLDER);

  bool mq2Alarm = false, mq135Alarm = false;
  recordVoteAndCheck(mq2Exceeded || mq2HardCeiling, mq135Exceeded || mq135HardCeiling, &mq2Alarm, &mq135Alarm);

  bool gasHigh = mq2Alarm || mq135Alarm;

  // Buzzer: local-only, direct GPIO write. No WiFi dependency of any
  // kind -- must trigger correctly even if WiFi never connected above.
  //
  // Precedence is deliberate and must not be reordered: a real gas
  // alarm ALWAYS wins over the trouble chirp. The trouble pattern only
  // runs when gasHigh is false, so the guard-4 notification can never
  // mask, interrupt, or be confused with an actual gas alarm.
  if (gasHigh) {
    digitalWrite(BUZZER_PIN, HIGH);
  } else if (baselineTroubleActive) {
    emitTroubleChirp();
  } else {
    digitalWrite(BUZZER_PIN, LOW);
  }

  Serial.print(",");
  Serial.print(gasHigh ? "GAS_HIGH" : (baselineTroubleActive ? "ok(BASELINE_TROUBLE)" : "ok"));
  Serial.print(",baseline_mq2=");
  Serial.print(mq2TrackedBaseline);
  Serial.print(",warn_mq2=");
  Serial.print(mq2Warn);
  Serial.print(",danger_mq2=");
  Serial.print(mq2Danger);
  Serial.print(",baseline_mq135=");
  Serial.print(mq135TrackedBaseline);
  Serial.print(",warn_mq135=");
  Serial.print(mq135Warn);
  Serial.print(",danger_mq135=");
  Serial.println(mq135Danger);

  // --- Stage 3 transport: LAST thing in loop(), after the buzzer -----
  // Everything above (sampling, voting, baseline tracking, buzzer) has
  // already happened and is unaffected by whatever occurs here. This is
  // the literal embodiment of info.md's local-alarm-before-network
  // principle at the firmware level.
  const char *stateStr = gasHigh ? "GAS_HIGH"
                                 : (baselineTroubleActive ? "ok(BASELINE_TROUBLE)" : "ok");
  postReading(mq2Raw, mq135Raw, stateStr, true,
              mq2Warn, mq2Danger, mq135Warn, mq135Danger);
}
