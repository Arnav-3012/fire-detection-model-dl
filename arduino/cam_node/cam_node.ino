// FireWatch Phase 13a — ESP32-CAM capture sketch (camera board only,
// no sensor wiring on this board — see the plain ESP32 DevKit sensor
// node for MQ-2/MQ-135/buzzer).
//
// Hardware: AI-Thinker ESP32-CAM on an ESP32-CAM-MB (HW-381) USB
// programmer shield. Confirmed board/camera identity this session:
// the on-board sensor is NOT the genuine OV2640 the AI-Thinker profile
// assumes — a diagnostic PID read returned 0x2145 (GC2145_PID in the
// espressif/esp32-camera driver's sensor.h), i.e. this specific module
// has a GalaxyCore GC2145 sensor, a known OV2640-clone substitution on
// cheap AI-Thinker-compatible boards. The driver's own sensor table
// marks GC2145 jpeg_support=false (OV2640=true) — there is no on-chip
// JPEG encoder on this silicon, so PIXFORMAT_JPEG is permanently
// unavailable on this exact module. This is confirmed hardware
// capability, not a PSRAM/menuconfig/config mismatch (psramFound()==1
// was already confirmed during the smoke test).
//
// Because of this, this sketch captures in RGB565 (the sensor's real
// native format) and converts each frame to JPEG in software via the
// driver's own frame2jpg() before it reaches the network. This keeps
// the wire format JPEG — matching plan.md §10.2 (Lambda cost budget),
// §10.3 (bandwidth budget), §10.6 (data flow), and §10.7 (Live View
// dashboard tab) exactly as planned. Only the on-sensor capture format
// changed from the original OV2640-hardware-JPEG assumption; nothing
// downstream needs to change.
//
// COST NOT IN THE ORIGINAL PLAN: software JPEG encoding is CPU-bound
// on the ESP32's own core (no hardware encoder to offload to), adding
// real per-frame latency on top of capture + WiFi send. This was not
// budgeted in plan.md §10.3's "practical streaming target: 640x480 @
// 5fps" line, which assumed the OV2640's on-chip encoder doing this
// step for free.
//
// MEASURED 2026-09-16 (live device, FRAMESIZE_VGA): frame2jpg() takes
// ~480-500ms/frame, ~2fps from conversion alone, before capture time
// or WiFi overhead -- confirms 640x480@5fps does not hold on this
// sensor. Currently testing FRAMESIZE_QVGA (320x240) below to see
// whether a smaller source frame clears a reasoned fps target -- see
// plan.md §10.3 and context.md for the latency-budget reasoning that
// sets what "reasoned" means here (info.md §4.3's real 10s/30s alert
// budgets, not the 5fps figure itself).

#include "esp_camera.h"
#include "img_converters.h"
#include <WiFi.h>

// ---------------------------------------------------------------------
// AI-Thinker pin map (copied from the Arduino IDE's own
// CameraWebServer camera_pins.h AI_THINKER block, not re-derived —
// this board's wiring is standard AI-Thinker, only the sensor silicon
// behind those pins differs from the OV2640 the profile name implies).
// ---------------------------------------------------------------------
#define PWDN_GPIO_NUM  32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  0
#define SIOD_GPIO_NUM  26
#define SIOC_GPIO_NUM  27

#define Y9_GPIO_NUM    35
#define Y8_GPIO_NUM    34
#define Y7_GPIO_NUM    39
#define Y6_GPIO_NUM    36
#define Y5_GPIO_NUM    21
#define Y4_GPIO_NUM    19
#define Y3_GPIO_NUM    18
#define Y2_GPIO_NUM    5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM  23
#define PCLK_GPIO_NUM  22

#define LED_GPIO_NUM   4  // onboard flash LED

// ---------------------------------------------------------------------
// WiFi — HOME context only for this smoke-test-adjacent sketch.
// Two-context WiFiManager switching (plan.md §10.4) is a separate,
// not-yet-built piece of work — this sketch is deliberately minimal
// (hardcoded credentials) so the RGB565->JPEG path can be verified in
// isolation first.
// ---------------------------------------------------------------------
// Credentials live in secrets.h, which is gitignored and NOT committed.
// Copy secrets.example.h to secrets.h and fill in your own values before
// flashing. Do not put real credentials in this file -- it is tracked.
#include "secrets.h"

// JPEG quality passed to frame2jpg (0-63, lower = higher quality/larger
// file — matches the stock example's own working value for this frame
// size class, not re-tuned here).
static const int JPEG_QUALITY = 12;

WiFiServer server(80);

// WiFi resilience (2026-09-23). Previously setup() blocked forever on
// WL_CONNECTED and loop() had no reconnect at all, so a router reboot
// or transient AP drop left the board serving nothing, indefinitely,
// with no indication -- edge/main.py's frame source would simply go
// dead. This project's stated preference is loud failure over silent
// degradation, so the wait is now bounded and reconnection is retried
// on a fixed interval with a serial line each time.
static const unsigned long WIFI_CONNECT_TIMEOUT_MS = 15000;  // matches sensor_esp32_node.ino
static const unsigned long WIFI_RETRY_INTERVAL_MS = 5000;    // between reconnect attempts in loop()
static const unsigned long REQUEST_READ_TIMEOUT_MS = 1000;   // cap on reading the HTTP request line
static const unsigned int MAX_REQUEST_LINE_LEN = 512;        // reject longer request lines outright
static unsigned long lastWifiRetryMs = 0;
static bool wifiWasConnected = false;

// Keeps WiFi up without ever blocking loop(). Returns true if currently
// connected. Logs each transition (down/restored) exactly once rather
// than every pass, so a long outage doesn't flood the serial line --
// which matters here because this board's USB-serial link has its own
// documented reliability problems (see logs.md).
static bool ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiWasConnected) {
      wifiWasConnected = true;
      Serial.print("[WIFI_RESTORED] reconnected, IP: ");
      Serial.println(WiFi.localIP());
    }
    return true;
  }

  if (wifiWasConnected) {
    wifiWasConnected = false;
    Serial.println("[WIFI_LOST] connection dropped -- retrying, no frames can be served until restored");
  }

  unsigned long now = millis();
  if (now - lastWifiRetryMs >= WIFI_RETRY_INTERVAL_MS) {
    lastWifiRetryMs = now;
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
  return false;
}

// ---------------------------------------------------------------------
// Narrow-FOV fix (2026-09-16) — Option B: runtime register poke, not a
// forked driver copy.
//
// ROOT CAUSE (confirmed against the actual espressif/esp32-camera
// driver source, sensors/gc2145.c set_framesize(), subsample-mode path
// -- this toolchain compiles CONFIG_GC_SENSOR_SUBSAMPLE_MODE=y, not
// windowing mode): the ratio-selection loop does
// `if (framesize >= FRAMESIZE_QVGA) i = 1;`, unconditionally skipping
// subsample_cfgs[0] (the 1/3 ratio, 140/420 -- the widest available
// field of view) for every framesize at or above QVGA. At QVGA
// (320x240) this lands the loop on the 1/2 ratio instead, giving a
// sensor read-out window of only 640x480 out of the full 1600x1200
// UXGA array (~40% width/height) before the 2:1 subsample down to the
// output frame -- a real, fixed, sensor-pixel-space crop that does not
// widen with subject distance, matching the observed symptom exactly.
// This is a driver default, not a GC2145-vs-OV2640 mismatch: the
// subsample path is sensor-model-agnostic.
//
// FIX: after esp_camera_init() has already run set_framesize() once
// (installing the driver's own default 1/2-ratio registers), replay
// the same register sequence set_framesize() would have used had `i`
// started at 0 -- i.e. the 1/3 ratio (subsample_cfgs[0] in gc2145.c:
// {140, 420, 0x33, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00}).
// This widens the sensor window from 640x480 to 960x720 (60% of UXGA)
// before the 3:1 subsample to the same 320x240 QVGA output.
//
// Done via the public sensor_t->set_reg() API (esp_camera_sensor_get(),
// wired to the driver's own read-modify-write register function) --
// no forked/patched copy of the driver, no editing the installed
// library in place. gc2145_regs.h's register addresses are not a
// public esp32-camera header, so they are reproduced here as literals;
// each write below is commented with the symbolic name it corresponds
// to in that header for traceability.
//
// MAINTENANCE RISK: these are raw sensor register addresses/values
// specific to the GC2145 (this board's actual, clone, sensor -- see
// the JPEG-support root-cause finding earlier in this file) and to
// this exact esp32-camera driver version's subsample_cfgs table and
// write-order. A future arduino-esp32 / esp32-camera library update
// could change the ratio table, the register map, or fix the i=1 skip
// upstream -- any of which could silently make this poke redundant,
// wrong, or conflict with a new default. If FOV regresses or looks
// wrong after a toolchain update, re-verify this function against the
// then-current gc2145.c before assuming it still applies.
static void widen_fov_qvga() {
  sensor_t *sensor = esp_camera_sensor_get();
  if (!sensor) {
    Serial.println("widen_fov_qvga: esp_camera_sensor_get() returned null, skipping");
    return;
  }

  // page 0 select (RESET_RELATED / 0xfe, bits[2:0] = page)
  sensor->set_reg(sensor, 0xfe, 0xff, 0x00);

  // P0_CROP_ENABLE
  sensor->set_reg(sensor, 0x90, 0xff, 0x01);

  // P0_ROW_START_HIGH/LOW, P0_COL_START_HIGH/LOW -- row_s=240, col_s=320
  // (derived the same way set_framesize() derives them: centered in
  // the full UXGA 1600x1200 array around a 960x720 window)
  sensor->set_reg(sensor, 0x09, 0xff, 0x00);
  sensor->set_reg(sensor, 0x0a, 0xff, 0xf0);
  sensor->set_reg(sensor, 0x0b, 0xff, 0x01);
  sensor->set_reg(sensor, 0x0c, 0xff, 0x40);

  // P0_WIN_HEIGHT_HIGH/LOW, P0_WIN_WIDTH_HIGH/LOW -- win_h+8=728, win_w+16=976
  sensor->set_reg(sensor, 0x0d, 0xff, 0x02);
  sensor->set_reg(sensor, 0x0e, 0xff, 0xd8);
  sensor->set_reg(sensor, 0x0f, 0xff, 0x03);
  sensor->set_reg(sensor, 0x10, 0xff, 0xd0);

  // P0_SUBSAMPLE (0x99) + the 0x9b-0xa2 subsample tuning block --
  // subsample_cfgs[0] = {140, 420, reg0x99=0x33, rest all 0x00}
  sensor->set_reg(sensor, 0x99, 0xff, 0x33);
  sensor->set_reg(sensor, 0x9b, 0xff, 0x00);
  sensor->set_reg(sensor, 0x9c, 0xff, 0x00);
  sensor->set_reg(sensor, 0x9d, 0xff, 0x00);
  sensor->set_reg(sensor, 0x9e, 0xff, 0x00);
  sensor->set_reg(sensor, 0x9f, 0xff, 0x00);
  sensor->set_reg(sensor, 0xa0, 0xff, 0x00);
  sensor->set_reg(sensor, 0xa1, 0xff, 0x00);
  sensor->set_reg(sensor, 0xa2, 0xff, 0x00);

  // P0_OUT_WIN_HEIGHT_HIGH/LOW, P0_OUT_WIN_WIDTH_HIGH/LOW -- output
  // stays 320x240 (QVGA); only the sensor-side read window widened
  sensor->set_reg(sensor, 0x95, 0xff, 0x00);
  sensor->set_reg(sensor, 0x96, 0xff, 0xf0);
  sensor->set_reg(sensor, 0x97, 0xff, 0x01);
  sensor->set_reg(sensor, 0x98, 0xff, 0x40);

  Serial.println("widen_fov_qvga: applied 1/3 subsample ratio (960x720 sensor window, was 640x480)");
}

static bool camera_init() {
  // Zero-initialize: camera_config_t has fields this sketch does not
  // set (sccb_i2c_port, and conv_mode when CONFIG_CAMERA_CONVERTER_ENABLED
  // is on). Left as a bare declaration these hold stack garbage. It is
  // currently latent -- sccb_i2c_port is only read when pin_sccb_sda is
  // -1, which it isn't here -- but it is one config change or library
  // update away from passing junk to the driver with no compile error.
  // Espressif's own examples zero-init for exactly this reason.
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;

  // RGB565 is the only format this sensor (GC2145) actually supports
  // for capture — do not set PIXFORMAT_JPEG here, it will fail
  // esp_camera_init() on this specific module every time (confirmed
  // this session, root cause is a real hardware limitation, not a
  // config value to keep re-trying).
  config.pixel_format = PIXFORMAT_RGB565;

  // MEASURED 2026-09-16 (live device): frame2jpg() at FRAMESIZE_VGA
  // takes ~480-500ms/frame (~2fps from conversion alone), well under
  // plan.md §10.3's 640x480@5fps target. Testing QVGA (320x240) here to
  // measure whether frame2jpg() drops enough to clear a reasoned fps
  // target — model inference resizes to 224x224 either way
  // (edge/vision.py _preprocess), so source resolution is free at
  // inference time; this only affects capture/convert/WiFi cost and
  // whatever detail survives the downsample to 224. Flip back to
  // FRAMESIZE_VGA to re-measure the VGA baseline.
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = JPEG_QUALITY;  // unused by capture itself (not
                                        // PIXFORMAT_JPEG) but read by
                                        // frame2jpg() below
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.fb_count = 2;  // double-buffer: let capture and encode/send
                         // overlap rather than serialize on one buffer
  config.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed, error 0x%x\n", err);
    return false;
  }
  return true;
}

static void send_jpeg_response(WiFiClient &client, uint8_t *jpg_buf, size_t jpg_len) {
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: image/jpeg");
  client.printf("Content-Length: %u\r\n", (unsigned)jpg_len);
  client.println("Connection: close");
  client.println();
  client.write(jpg_buf, jpg_len);
}

// Single-frame capture endpoint: GET /capture
// Mirrors the stock CameraWebServer's /capture route so this sketch
// is a drop-in-compatible single-shot source for anything built
// against that convention later (Phase 13c / edge ingestion).
static void handle_capture(WiFiClient &client) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    client.println("HTTP/1.1 500 Internal Server Error");
    client.println();
    return;
  }

  // ---- RGB565 -> JPEG software conversion happens here ----
  // This is the extra CPU/latency cost the original OV2640-based plan
  // did not budget for (that sensor would have produced JPEG directly
  // in hardware). Measure this on real hardware before assuming the
  // 640x480@5fps target in plan.md §10.3 still holds with this step
  // added — flagged, not silently absorbed.
  uint8_t *jpg_buf = nullptr;
  size_t jpg_len = 0;
  unsigned long convert_start_ms = millis();
  bool converted = frame2jpg(fb, JPEG_QUALITY, &jpg_buf, &jpg_len);
  unsigned long convert_ms = millis() - convert_start_ms;

  esp_camera_fb_return(fb);  // release the RGB565 buffer as soon as
                              // frame2jpg has copied out of it — don't
                              // hold it during the network write below

  if (!converted) {
    Serial.println("frame2jpg conversion failed");
    client.println("HTTP/1.1 500 Internal Server Error");
    client.println();
    return;
  }

  Serial.printf("RGB565->JPEG convert: %lums, %u bytes\n", convert_ms, (unsigned)jpg_len);
  send_jpeg_response(client, jpg_buf, jpg_len);
  free(jpg_buf);  // frame2jpg allocates this buffer with malloc; caller owns it
}

// MJPEG stream endpoint: GET /stream
// Same multipart/x-mixed-replace convention as the stock example, so
// existing MJPEG viewers/consumers work unmodified. Each iteration
// pays the same RGB565->JPEG conversion cost as handle_capture above.
static void handle_stream(WiFiClient &client) {
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: multipart/x-mixed-replace;boundary=frame");
  client.println();

  // NOTE (2026-09-23): this loop holds loop() for the entire life of the
  // connection, so this board serves exactly ONE stream client at a time
  // and cannot answer anything else -- including /capture or a health
  // check -- until that client disconnects. That is a real constraint on
  // how frames get fanned out to both edge/main.py and the planned Live
  // View dashboard tab; it is deliberately NOT solved here, because the
  // transport/fan-out design is an open decision (plan.md 10.6). Bounded
  // below only so a wedged or half-open client cannot spin forever.
  while (client.connected() && WiFi.status() == WL_CONNECTED) {
    unsigned long capture_start_ms = millis();
    camera_fb_t *fb = esp_camera_fb_get();
    unsigned long capture_ms = millis() - capture_start_ms;
    if (!fb) {
      Serial.println("Camera capture failed (stream)");
      break;
    }

    uint8_t *jpg_buf = nullptr;
    size_t jpg_len = 0;
    unsigned long convert_start_ms = millis();
    bool converted = frame2jpg(fb, JPEG_QUALITY, &jpg_buf, &jpg_len);
    unsigned long convert_ms = millis() - convert_start_ms;
    esp_camera_fb_return(fb);

    if (!converted) {
      Serial.println("frame2jpg conversion failed (stream)");
      break;
    }

    // Per-stage timing (2026-09-17, Phase 13a-2 FPS investigation):
    // handle_capture() already timed frame2jpg() alone, but that number
    // was measured at FRAMESIZE_VGA on the /capture endpoint, not
    // /stream at today's QVGA -- not safe to assume it explains the
    // 4.3-7.7fps measured on the actual edge/main.py hot path. Timing
    // capture/convert/send separately here before choosing a fix lever.
    unsigned long send_start_ms = millis();
    client.println("--frame");
    client.println("Content-Type: image/jpeg");
    client.printf("Content-Length: %u\r\n", (unsigned)jpg_len);
    client.println();
    size_t written = client.write(jpg_buf, jpg_len);
    client.println();
    unsigned long send_ms = millis() - send_start_ms;
    free(jpg_buf);

    Serial.printf("stream frame: capture=%lums convert=%lums send=%lums total=%lums\n",
                  capture_ms, convert_ms, send_ms, capture_ms + convert_ms + send_ms);

    // A short write means the peer is gone or the socket is half-open.
    // client.connected() alone does NOT catch half-open TCP (the local
    // side still believes it is connected), which would leave this loop
    // capturing and encoding frames forever into a dead socket, burning
    // CPU and blocking every other client.
    if (written != jpg_len) {
      Serial.printf("[STREAM_SHORT_WRITE] wrote %u of %u bytes -- client gone, closing stream\n",
                    (unsigned)written, (unsigned)jpg_len);
      break;
    }

    if (!client.connected()) break;
  }

  Serial.println("[STREAM_END] stream client disconnected, board free to accept new connections");
}

void setup() {
  Serial.begin(115200);
  Serial.println();

  if (!camera_init()) {
    Serial.println("FATAL: camera init failed, halting");
    while (true) delay(1000);
  }
  Serial.println("Camera init OK (RGB565 capture, GC2145 sensor)");

  widen_fov_qvga();

  // Red/pink color-cast investigation (2026-09-17, Phase 13a-2 accuracy
  // investigation) -- RULED OUT: tried jpgSetRgb565BE(false) on the theory
  // that frame2jpg()'s RGB565->RGB888 unpacking (conversions/to_jpg.cpp)
  // had the wrong byte-order default for this clone sensor. Live test
  // result: color went from a red/pink cast to fully scrambled rainbow
  // noise -- i.e. big_endian=true (the driver default, unchanged) is
  // actually correct for this hardware; flipping it broke decoding rather
  // than fixing white balance. Confirmed via the actual driver source
  // that GC2145's real AWB control functions (set_whitebal/set_wb_mode/
  // set_awb_gain) are all set_dummy in gc2145.c -- so the color cast is
  // not fixable via a runtime driver call either. Next suspect: the
  // on-chip AWB tuning table itself (gc2145_settings.h, loaded once via
  // reset()) may need real recalibration, which requires GC2145
  // datasheet-level register work, not a quick toggle -- do not
  // re-attempt jpgSetRgb565BE(false) without new evidence it was wrong to
  // rule out.

  // Bounded, not infinite. An unbounded wait here wedges the board
  // silently and forever if the AP is down at boot -- no frames, no
  // error, nothing but endless dots on a serial line nobody is
  // watching. Matches sensor_esp32_node.ino's 15s bound and its
  // explicit "say so and carry on" behaviour; ensureWifi() in loop()
  // keeps retrying, so a failure here is a delay, not a dead board.
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  unsigned long wifiStartMs = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStartMs < WIFI_CONNECT_TIMEOUT_MS) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Connected, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi NOT connected at boot -- will keep retrying in loop(); no frames can be served until it connects");
  }
  Serial.println("Endpoints: GET /capture (single JPEG), GET /stream (MJPEG)");

  server.begin();
}

void loop() {
  if (!ensureWifi()) {
    delay(50);  // nothing can be served while down; don't spin hot
    return;
  }

  WiFiClient client = server.available();
  if (!client) return;

  // Bound the request read. Without this, a client that connects and
  // sends nothing (port scanner, browser preconnect, half-open TCP)
  // stalls loop() for the full default Stream timeout on every such
  // connection, stealing time from the real frame consumer.
  client.setTimeout(REQUEST_READ_TIMEOUT_MS);
  String request_line = client.readStringUntil('\r');
  client.readStringUntil('\n');  // consume trailing \n after readStringUntil('\r')

  // A well-formed request line is short; anything longer is malformed
  // or hostile, and String growth is unbounded against limited heap.
  if (request_line.length() > MAX_REQUEST_LINE_LEN) {
    Serial.printf("[BAD_REQUEST] request line %u bytes, rejecting\n", (unsigned)request_line.length());
    client.println("HTTP/1.1 414 URI Too Long");
    client.println();
    client.stop();
    return;
  }

  if (request_line.indexOf("GET /capture") >= 0) {
    handle_capture(client);
  } else if (request_line.indexOf("GET /stream") >= 0) {
    handle_stream(client);
  } else {
    client.println("HTTP/1.1 404 Not Found");
    client.println();
  }

  client.stop();
}
