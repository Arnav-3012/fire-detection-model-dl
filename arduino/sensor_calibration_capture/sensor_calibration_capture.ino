// FireWatch Phase 13b — DATA-CAPTURE tool ONLY. Not production firmware.
//
// THREE uses now that sensor_esp32_node.ino has moved to per-boot
// relative baselines AND a slope-based (not fixed-duration) warmup
// gate (2026-09-20 redesigns, see that file's header for both):
//
//   1. CONTINUOUS WARM-UP CURVE LOG (used 2026-09-20 to derive the
//      slope threshold below) — flash this, then capture its raw
//      Serial output continuously (every line, WARMUP-tagged ones
//      included -- do NOT run this through tools/calibrate_sensors.py
//      for this use, it silently discards WARMUP lines) from a
//      genuinely cold boot, with NO power-cycling mid-run. Goal: see
//      the shape of the sensor's post-power-on convergence curve. See
//      logs.md "Phase 13b calibration — hardware session 1" and
//      "warmup gate calibrated from continuous log" for the real data
//      and derivation this sketch's own gate below is now based on.
//   2. **Stimulus-test capture (current use, 2026-09-20 on)** — run
//      during real stimulus tests (gas stove for MQ-2, whatever
//      stimulus is used for MQ-135) and watch its Serial output with
//      tools/calibrate_sensors.py, which computes CALIBRATED_DELTA
//      (peak - baseline, same session) instead of absolute thresholds.
//   3. Boot-baseline range capture — power-cycle 3+ separate times
//      (different times/positions, each with a FULL cold-boot rest
//      beforehand) and let calibrate_sensors.py record each boot's
//      clean-air baseline, to establish the plausible boot-baseline
//      sanity-bound range used by sensor_esp32_node.ino's guard 4.
//
// This sketch still computes NOTHING beyond the warmup gate itself --
// no baseline/peak tracking, no WARN/DANGER formula, no threshold
// logic, no N-of-M voting, no buzzer, no WiFi. All baseline/peak/delta
// computation happens downstream in tools/calibrate_sensors.py (uses
// 2-3) or by reading a raw continuous log directly (use 1).
//
// Completely separate from arduino/sensor_esp32_node/sensor_esp32_node.ino
// (production firmware) -- this task does not modify that file's own
// copy of this same gate logic, it duplicates the mechanism here.
//
// ---------------------------------------------------------------------
// WARMUP TAG — SLOPE-BASED, same mechanism as sensor_esp32_node.ino
// (changed 2026-09-20, developer-requested correction: this sketch
// previously kept a fixed 240s WARMUP/OK tag purely for output-format
// reasons, discarding genuinely stable, usable data between the real
// settle point (33-90s, confirmed live on this hardware) and 240s --
// unnecessarily conservative once the production firmware had already
// proven the sensor settles much faster. The tag now reflects the
// SAME real stability condition production alarming uses, not an
// arbitrary duration, so a human watching calibrate_sensors.py's
// min/max tracking (which skips WARMUP-tagged lines) isn't waiting on
// stale, over-cautious timing during calibration sessions.
//
// This is a DUPLICATE, SIMPLIFIED copy of sensor_esp32_node.ino's
// warmupElapsed()/rollingSlope()/rollingNetDrift() logic (same
// MQ2_MQ135_WARMUP_SLOPE_THRESHOLD, MQ2_MQ135_WARMUP_DRIFT_THRESHOLD,
// window, and hold constants) -- kept here rather than shared via a
// header, consistent with this sketch's existing "reused as-is, copied
// not imported" pattern for pin map/ADC config/readAveraged().
// UPDATED 2026-09-21: added the net-drift check (see
// sensor_esp32_node.ino's WARMUP GATE header comment for the full
// reasoning) -- jitter alone is sign-blind and let a slow steady
// cold-start decline through as "flat." If either constant is ever
// re-derived in sensor_esp32_node.ino, update the copy here too.
// ---------------------------------------------------------------------
//
// SERIAL OUTPUT FORMAT -- KEEP THIS EXACT. calibrate_sensors.py depends
// on this format not changing.
//
//   <millis_since_boot>,<mq2_avg>,<mq135_avg>,<WARMUP|OK>
//
// One line per sample cycle (1Hz). Example:
//   12345,102,48,WARMUP
//   45231,97,45,OK
//
// NOTE for use 1 (continuous warm-up log, if re-run in the future):
// capture and look at EVERY line regardless of this tag -- the tag
// now reflects THIS sketch's own live slope read, which is exactly
// what a future continuous-log run would be re-verifying, so relying
// on it to decide what to look at would be circular for that use.
// ---------------------------------------------------------------------
//
// Reused as-is from sensor_esp32_node.ino (same board, same divider,
// same reasoning -- see that file's header for full detail):
//   - Pin map: MQ-2 -> GPIO34, MQ-135 -> GPIO35 (ADC1, input-only)
//   - 12-bit ADC resolution, ADC_6db attenuation (matched to this
//     board's 22k/10k divider, ~1.56V ceiling)
//   - readAveraged(): 8 samples/2ms per sensor
//   - Slope-based warmup gate (see block above)

#include <Arduino.h>

// ---------------------------------------------------------------------
// Pin map (reused from sensor_esp32_node.ino)
// ---------------------------------------------------------------------
static const int MQ2_PIN   = 34;  // ADC1_CH6, input-only
static const int MQ135_PIN = 35;  // ADC1_CH7, input-only

// ---------------------------------------------------------------------
// Timing (reused from sensor_esp32_node.ino)
// ---------------------------------------------------------------------
static const unsigned long SAMPLE_INTERVAL_MS = 1000;

// ---------------------------------------------------------------------
// Analog read averaging (reused from sensor_esp32_node.ino)
// ---------------------------------------------------------------------
static const int ADC_SAMPLE_COUNT = 8;
static const int ADC_SAMPLE_DELAY_MS = 2;

// ---------------------------------------------------------------------
// Slope-based warmup gate (duplicated from sensor_esp32_node.ino, see
// header note above). Same calibrated value, same window/hold, same
// 1-hour backstop.
// ---------------------------------------------------------------------
static const int WARMUP_SLOPE_WINDOW = 10;
static const float MQ2_MQ135_WARMUP_SLOPE_THRESHOLD = 12;   // jitter: mean per-sample |change|
static const float MQ2_MQ135_WARMUP_DRIFT_THRESHOLD = 22;   // net drift: |newest - oldest| across window
static const unsigned long WARMUP_STABLE_HOLD_S = 60;
static const unsigned long WARMUP_MAX_SECONDS = 3600;

float mq2SlopeBuffer[WARMUP_SLOPE_WINDOW];
float mq135SlopeBuffer[WARMUP_SLOPE_WINDOW];
int slopeBufferIndex = 0;
int slopeBufferFilled = 0;
unsigned long stableSinceMs = 0;

unsigned long lastSampleMs = 0;
unsigned long bootMs = 0;
bool bootWarmupCleared = false;

void setup() {
  Serial.begin(9600);

  analogReadResolution(12);
  analogSetAttenuation(ADC_6db);

  for (int i = 0; i < WARMUP_SLOPE_WINDOW; i++) {
    mq2SlopeBuffer[i] = 0;
    mq135SlopeBuffer[i] = 0;
  }

  bootMs = millis();

  Serial.println("# FireWatch Phase 13b sensor_calibration_capture -- DATA CAPTURE ONLY, computes nothing beyond the slope-based warmup tag");
  Serial.println("# format: <millis_since_boot>,<mq2_avg>,<mq135_avg>,<WARMUP|OK>");
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

void pushSlopeSample(float *buffer, int latestAvg) {
  buffer[slopeBufferIndex] = (float)latestAvg;
}

float rollingSlope(float *buffer, int filled) {
  if (filled < 2) return 1e9;
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

// Sign-aware companion to rollingSlope() -- see sensor_esp32_node.ino
// for the full reasoning and the measured cold-start case it fixes.
float rollingNetDrift(float *buffer, int filled) {
  if (filled < 2) return 1e9;
  int start = (filled < WARMUP_SLOPE_WINDOW) ? 0 : slopeBufferIndex;
  float oldest = buffer[start % WARMUP_SLOPE_WINDOW];
  float newest = buffer[(start + filled - 1) % WARMUP_SLOPE_WINDOW];
  float d = newest - oldest;
  return (d < 0) ? -d : d;
}

bool warmupElapsed() {
  // LATCH (added 2026-09-21): warmup is a one-way, per-boot transition.
  // Without this, the gate is a live re-evaluated condition, so any real
  // stimulus (the gas stove test that motivated this fix) spikes the
  // readings, blows through both the jitter and net-drift checks, and
  // drags the board BACK into WARMUP -- at which point
  // tools/calibrate_sensors.py silently discards every line and the
  // operator sees a frozen display during the exact window they are
  // trying to capture. Settling is a property of the sensor's heater
  // reaching equilibrium; it does not un-happen because gas arrived.
  if (bootWarmupCleared) return true;

  unsigned long elapsedMs = millis() - bootMs;
  if (elapsedMs >= (WARMUP_MAX_SECONDS * 1000UL)) return true;

  float mq2Slope = rollingSlope(mq2SlopeBuffer, slopeBufferFilled);
  float mq135Slope = rollingSlope(mq135SlopeBuffer, slopeBufferFilled);
  float mq2Drift = rollingNetDrift(mq2SlopeBuffer, slopeBufferFilled);
  float mq135Drift = rollingNetDrift(mq135SlopeBuffer, slopeBufferFilled);
  bool bothFlatNow = (mq2Slope <= MQ2_MQ135_WARMUP_SLOPE_THRESHOLD) &&
                      (mq135Slope <= MQ2_MQ135_WARMUP_SLOPE_THRESHOLD) &&
                      (mq2Drift <= MQ2_MQ135_WARMUP_DRIFT_THRESHOLD) &&
                      (mq135Drift <= MQ2_MQ135_WARMUP_DRIFT_THRESHOLD);

  if (!bothFlatNow) {
    stableSinceMs = 0;
    return false;
  }
  if (stableSinceMs == 0) {
    stableSinceMs = millis();
  }
  return (millis() - stableSinceMs) >= (WARMUP_STABLE_HOLD_S * 1000UL);
}

void loop() {
  unsigned long now = millis();
  if (now - lastSampleMs < SAMPLE_INTERVAL_MS) return;
  lastSampleMs = now;

  int mq2Avg = readAveraged(MQ2_PIN, ADC_SAMPLE_COUNT);
  int mq135Avg = readAveraged(MQ135_PIN, ADC_SAMPLE_COUNT);

  pushSlopeSample(mq2SlopeBuffer, mq2Avg);
  pushSlopeSample(mq135SlopeBuffer, mq135Avg);
  slopeBufferIndex = (slopeBufferIndex + 1) % WARMUP_SLOPE_WINDOW;
  if (slopeBufferFilled < WARMUP_SLOPE_WINDOW) slopeBufferFilled++;

  bool wasWarmupElapsedBeforeThisSample = bootWarmupCleared;
  bool warmupNowElapsed = warmupElapsed();
  if (!wasWarmupElapsedBeforeThisSample && warmupNowElapsed) {
    bootWarmupCleared = true;
    unsigned long elapsedS = (millis() - bootMs) / 1000UL;
    if (elapsedS >= WARMUP_MAX_SECONDS) {
      Serial.println("# [WARMUP_BACKSTOP] cleared via 1-hour timeout, NOT slope stability");
    } else {
      Serial.print("# [WARMUP_STABLE] cleared via slope stability after ");
      Serial.print(elapsedS);
      Serial.println("s");
    }
  }

  Serial.print(now);
  Serial.print(",");
  Serial.print(mq2Avg);
  Serial.print(",");
  Serial.print(mq135Avg);
  Serial.print(",");
  Serial.println(warmupNowElapsed ? "OK" : "WARMUP");
}
