# context.md — fast context recovery

This file is regenerated, not appended to. It is a summary only and may be
stale. **`logs.md` remains the source of truth.** Last regenerated
2026-09-24, at the close of Phase 13. The previous version, which carried
the full Phase 0–13 decision history, is in git history; every item it
summarised is in `logs.md`.

---

## 1. What FireWatch is

An IoT fire and gas hazard detector with local edge inference and agentic
response. A laptop runs the edge loop: it reads an **ESP32-CAM** video
stream (through a relay) into a local ONNX MobileNetV3-Small classifier,
fuses the result with the verdict of an **ESP32 gas-sensor board**
(MQ-2/MQ-135, both boards on WiFi), and produces SAFE / WATCH / WARNING /
CRITICAL. A LangGraph agent handles response only (Telegram, Twilio SMS,
display-only fire-station lookup, simulated dispatch). Detection works with
the internet disconnected, and the sensor board sounds its own buzzer with
no host at all.

---

## 2. Architecture (plan.md §1, as built)

1. Simulated dispatch, full payload logged but never transmitted
2. Model runs locally on the edge device (laptop). The cloud gives an
   **advisory** second opinion only and never feeds fusion
3. Camera **plus** gas sensors, fused
4. Laptop is the edge device
5. Fine-tuned pretrained MobileNetV3-Small (v4)
6. Agent handles **response only**, never detection
7. Threshold plus temporal smoothing (vision on the host; gas in firmware)
8. Hardcoded coordinates, no GPS

**DHT22 is cut** — `temp_spiking()` is permanently `False`.

**Gas verdict is owned by the sensor firmware** (Phase 13f): per-boot
baseline after a slope-based warm-up gate, ratio WARN/DANGER thresholds,
capped drift tracking, absolute hard ceilings, 3-of-5 vote, own buzzer.
The edge loop uses `gas_high = (state == "GAS_HIGH")`. config.yaml's gas
thresholds are a legacy-firmware fallback only.

**Start order:** dashboard backend (hosts the camera relay) → agent server
→ `edge/main.py` → frontend. The edge loop reads frames from
`http://127.0.0.1:8001/api/camera/stream`, so it fails to open its video
source if the backend isn't up.

---

## 3. Current phase and status

**Phases 0–13 complete (2026-09-24).** No build work is in flight.

- **Phase 13 (two-board migration)** closed: WiFi transport and camera
  relay (13f), cloud second-opinion Lambda (13g, Item B cut), dashboard
  threshold fix and live-first home page (13h), docs pass.
- **Developer-reported re-verification, 2026-09-24:** offline (WAN down,
  WiFi down), latency, TV/laptop re-test on the ESP32-CAM, evaluation
  trials on two-board hardware, Phase 8b drills, v4 wall re-check, airflow,
  dashboard in a browser — all reported passing. **No numbers supplied
  yet**; report.md §13.6 marks each "not yet recorded".
- **Remaining:** record those numbers (§7), the Phase 13h real-board check
  (§7), and the final commit/push (the developer does this).

---

## 4. Most recent key decisions (newest first)

1. **Dashboard thresholds ride on every live sample (13h).** The
   write-on-change sidecar was never cleared, so after a board reboot the
   chart drew the previous boot's thresholds, and during warm-up it drew
   config.yaml's 10-bit values. Now `livelog` stores `state` + `thr` per
   sample; thresholds are withheld during WARMUP/BASELINE_CAPTURE; the
   backend never sends config thresholds. Payload adds `threshold_source`,
   `board_state`, `camera`.
2. **Home page rebuilt live-first (13h).** Live View + Nearest Fire Station
   folded into Overview (6 tabs → 4); one `/ws/live` socket; hazard-index
   gas chart (baseline 0, warn 1, danger 2 per sensor) + raw lanes;
   relay-driven camera liveness overlay.
3. **Item B (S3 re-scoring) cut** — no real CRITICAL snapshots exist to
   re-score.
4. **Cloud second opinion is advisory, full-frame (13g).** The planned
   5-crop MAX rule was measured and rejected (neutral FP 0.000 → 0.180);
   crops kept as diagnostics. OpenCV kept in the Lambda (Pillow flipped 2%
   of verdicts). JPEG q95 (0.3% flips vs 1.0% at q80). Triggered on the
   GAS_HIGH rising edge; off by default; 60 s cooldown, 20 calls/session.
5. **Firmware owns the gas verdict (13f Stage 2).** Host config thresholds
   would have false-alarmed on MQ-2 and missed MQ-135 on the same board.
6. **Sensor ingest in the edge loop; camera relay in the backend (13f).**
   Detection must not depend on the optional dashboard; the dashboard's
   live camera must work when the edge loop is stopped.
7. **`votes_needed` 5 → 3 (13a-2)** for the ~7–8 fps ESP32-CAM stream
   (alarm/p_fire-hit ratio 0.13 → 1.09). TV/laptop re-test since reported
   passing.
8. **Location redacted from public git history (2026-09-24)** with
   `git filter-repo`, force-pushed. Never write coordinates, area names or
   the nearest-station name into tracked files.

---

## 5. Real measured values

| Value | Current |
|---|---|
| Production model | **v4** since 2026-09-05 (`models/fire_mnv3.onnx` == `fire_mnv3_v4.onnx`, sha `36de3559…`, weights in sidecar `fire_mnv3_v4.onnx.data`). val acc 0.9129; fire recall 0.9575 / precision 0.8664 @ 0.30; smoke recall 0.8511 @ 0.45 argmax-AND; macro F1 0.9065; ONNX diff 5.99e-05 |
| Vision config | `fire_decision_threshold` 0.30, tau 0.70, window 8, `votes_needed` **3**, `smoke_votes_needed` 5, `smoke_decision_threshold` 0.45 |
| Adversarial (v4, webcam path) | sunset / steam / red clothing 0 fire alarms; TV fire 6 (bar ≤ 2, rule-4 mitigated); candle alarms; steam 5 smoke-WATCH; bright-wall clip 0 WATCH |
| Frame rate | 6.5 fps at 320×240 through the relay (ESP32-CAM native rate); was 29.5–30.5 on the webcam |
| Relay fan-out | 3 viewers × 27 identical frames from 1 upstream connection |
| Local vs Lambda `p_fire` | 0.998336017131805 both (bit-identical); Lambda 722 ms cold, ~23 ms warm locally; package 236.9 MB / 250 MB |
| Sensor board thresholds | Computed per boot by firmware — no fixed values. Ratio-formula match verified live (13f) |
| Phase 11 trials | 12 run, 11 PASS; total-darkness false WARNING (open limitation) |
| Two-board re-verification | Reported pass, numbers not yet recorded (§3) |

---

## 6. Hardware status

| Item | Status |
|---|---|
| ESP32 DevKit sensor board | Working on WiFi (home + phone hotspot), USB-free operation verified; `arduino/sensor_esp32_node` |
| MQ-2 GPIO34 / MQ-135 GPIO35 | 22k/10k dividers (final); per-boot thresholds |
| Buzzer GPIO33 | Board-driven on its own GAS_HIGH; verified sounding with WiFi down |
| AI-Thinker ESP32-CAM | Working through the relay; **GC2145** sensor (not OV2640), RGB565 + software JPEG, QVGA, FOV widened by `widen_fov_qvga()` register poke |
| Arduino Uno, webcam | Retired (Phase 13) |
| DHT22 | Cut |

---

## 7. Standing open items

**To finish before calling it done**
- **Record the re-verification numbers** in logs.md and report.md §13.6
  (offline, latency, TV/laptop alarm count, trial results, 8b drills, wall
  re-check, airflow). info.md 2.4: no metric is written until supplied.
- **Phase 13h real-board check:** reboot the sensor board mid-session;
  the chart should show warm-up shading, then new lines, never the
  previous boot's. Also unplug the ESP32-CAM and confirm SIGNAL LOST.
  Samples written before an edge restart carry no `thr`.
- **Commit/push** — developer only.

**Housekeeping**
- `data/live_sensors_thresholds.json` is unused since 13h; safe to delete.
- `config.yaml` has `gas_warmup_seconds: 60` while its comment says it was
  restored to 240. Only the legacy fallback path reads it now, but the two
  disagree.
- `location.address` is still `"NOT SET"` (appears in alert text).
  `temp_rise_rate` is a placeholder, moot while DHT22 is cut.
- After the demo: `python scripts/deploy_lambda.py --delete`, and set
  `aws.second_opinion.enabled: false`.
- Optional: a GitHub sensitive-data request purges the pre-redaction head
  `2cbc4ff` sooner than garbage collection.

**Known limitations (documented, not bugs to chase)**
- TV/laptop fire footage → vision-only WARNING, capped by fusion rule 4.
- Total darkness → false vision-only WARNING (Phase 11 trial 12), cause
  unconfirmed. ESP32-CAM low-light behaviour not separately tested.
- Steam → smoke-WATCH events.
- ESP32-CAM IP hardcoded in `camera.stream_url`; update after network
  changes.
- Sensor board is movement-sensitive (cause unconfirmed); mount it fixed.
- MQ-135 calibration delta runs trended upward (485 → 566 → 665),
  flagged unresolved in firmware.
- Firmware is never compile-checked on this machine (`arduino-cli`
  missing); first compile happens at flash time.
- `widen_fov_qvga()` depends on this exact camera-driver version.

**Code size (soft cap ~200 lines; don't grow these)**
- `edge/main.py` 432, `edge/sensors.py` 350, `edge/wifi_source.py` 295,
  `edge/vision.py` 263. `agent/graph.py` 325 is a reviewed, deliberate
  exception.

---

For full detail, reason, and history, read plan.md, info.md, and logs.md —
this file is a summary only and may be stale.
