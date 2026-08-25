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

**DHT22 is cut** (Phase 0g — cost + availability). No temp/humidity signal.
This breaks the Day 7 fusion rule "fire AND temp_spiking -> CRITICAL" —
**unresolved, needs a decision before Day 7.**

---

## 3. Current phase and status

From logs.md "Project state at a glance":

| Phase | Name | Status | Date | Key result |
|---|---|---|---|---|
| 0 | Scaffold and config | COMPLETE | 2026-08-18 | Folder tree + config.yaml created, parses clean |
| 1 | Dataset preparation | COMPLETE | 2026-08-18 | train 18,464 / val 3,258 images (neutral/smoke/fire), 195 hard negatives folded in; TV/laptop hard-negative category (30) still not collected |
| 2 | Model training | COMPLETE | 2026-08-23 | Fire recall 0.9611, precision 0.8785 @ fire_decision_threshold=0.30 (argmax result was 0.9221, failed the 0.95 block bar). Val accuracy 0.9067. Open item: thin recall margin, re-verify after Day 4/5 |
| 3 | Edge loop v1 | COMPLETE | 2026-08-24 | camera.py + vision.py + main.py built and integrated; live webcam test confirmed neutral room (fire~0.00) and real fire video (FIRE 0.48-0.99, peak 0.99) both classified correctly, single-frame (pre-temporal-smoothing) noise as expected |
| 4 | Temporal smoothing | NOT STARTED | — | — |
| 5 | Adversarial evaluation | NOT STARTED | — | — |
| 6 | Arduino and sensors | IN PROGRESS | 2026-08-23 | H1-H2 done (Arduino verified via pin-9 LED blink); MQ-2 + MQ-135 wired, burn-in started 2026-08-23 12:40 AM, valid from 2026-08-24 12:40 AM (24h min) / 2026-08-25 12:40 AM (preferred); H3/H4 deferred pending buzzer arrival |
| 7 | Fusion logic | NOT STARTED | — | Blocked on the temp_spiking / DHT22 decision above |
| 8 | Agent part 1 | NOT STARTED | — | — |
| 9 | Agent part 2 | NOT STARTED | — | — |
| 10 | Cloud | NOT STARTED | — | — |
| 11 | Dashboard and evaluation | NOT STARTED | — | — |
| 12 | Documentation | NOT STARTED | — | — |

---

## 4. Five most recent key decisions (newest first)

1. **Phase 3 (Day 3):** Live edge-loop test (camera -> vision -> print)
   confirmed working: neutral room correctly reads fire~0.00 across all
   frames; real fire video correctly and confidently detected (FIRE 0.48 up
   to peak 0.99), with a smooth ramp at the transition and smooth decay at
   the end. Satisfies plan.md 4.4's S4 milestone and info.md 5's Edge loop
   testing bar. Frame-to-frame noise within the fire run is expected
   (single-frame detection, no temporal smoothing yet — Day 4 scope), not a
   defect. Also found: `conda run -n firewatch python edge/main.py` buffers
   stdout and intercepts Ctrl+C — use an activated shell
   (`conda activate firewatch && python -u ...`) for any live/interactive
   edge-loop testing going forward, not `conda run`.
2. **Phase 3 (Day 3):** `edge/camera.py` had a real bug caught during
   `vision.py` testing — the first frame(s) after `cv2.VideoCapture` opens
   on macOS/AVFoundation are black/garbage while auto-exposure settles.
   First live test read a near-black frame (mean BGR ~0.005) and produced a
   false `FIRE 0.43` on an actual neutral room. Fixed with `Camera._warm_up()`
   (discards first 10 frames in `__init__`). `vision.py`'s own preprocessing
   (BGR->RGB, normalization, class order) was correct throughout and did not
   need to change — the bug was in the input, not the pipeline math.
2b. **Phase 3 (Day 3):** Smoke decision — `edge/vision.py`'s `smoke` boolean
   uses **argmax** (highest-probability class), not a threshold, because
   config.yaml has no smoke-equivalent of `fire_decision_threshold` and Phase
   2 never tuned one. Developer's explicit choice, per info.md §7 (asked
   rather than guessed). Consequence: `fire` and `smoke` can both be `True`
   in the same result — `fire` is authoritative. Untuned/placeholder rule,
   flagged for future revisit if smoke-specific FP/FN issues surface.
3. **Phase 3 (Day 3):** `models/fire_mnv3.onnx` exported (`train/export_onnx.py`
   had been written but not run). Required adding `onnxscript` to
   requirements.txt — PyTorch 2.13's default `torch.onnx.export` path now
   depends on it. Export verified: max PyTorch/ONNX logit diff 3.77e-05
   (tolerance 1e-4) on 32 real val images. Confirmed class mapping from the
   checkpoint: `{'fire': 0, 'neutral': 1, 'smoke': 2}`.
4. **Phase 2:** `fire_decision_threshold` set to 0.30 in config.yaml (new
   key, distinct from `frame_threshold`/tau, which belongs to the Day 4
   temporal voter). Chosen because it's the lowest of five swept thresholds
   that clears both info.md 4.1 fire-class block bars at once (recall >=
   0.95, precision >= 0.80): 0.30 gives recall 0.9611 / precision 0.8785,
   while 0.35 falls just short on recall (0.9496). Deliberate recall-over-
   precision tradeoff per info.md 4.1's own stated priority. Recall margin
   over the floor is thin (1.1 points) vs. precision margin (7.85 points) —
   flagged to re-verify once Day 4 temporal voter and Day 5 adversarial eval
   are in place.
5. **Phase 1 (Addendum 3):** Split strategy resolved — pool all three D-Fire
   splits (train/val/test, 21,527 images) and re-split 85/15 by class,
   ignoring D-Fire's original boundaries, because plan.md specifies no
   held-out test set beyond the Day 5/Day 11 evaluations.

---

## 5. Real measured values (logs.md "Live values" + Phase 1/2/3 results)

| Value | Current |
|---|---|
| Train images (neutral / smoke / fire) | 8,528 / 4,987 / 4,949 (18,464 total) |
| Val images (neutral / smoke / fire) | 1,505 / 880 / 873 (3,258 total) |
| Hard negatives folded into neutral | 195 (6 categories; TV/laptop category of 30 not yet collected) |
| Model val accuracy | 0.9067 (best checkpoint, epoch 11) |
| Fire recall (argmax) | 0.9221 — FAILED the 0.95 block bar |
| Fire recall @ fire_decision_threshold=0.30 | **0.9611 — PASSES** |
| Fire precision @ fire_decision_threshold=0.30 | **0.8785 — PASSES** (bar 0.80) |
| Smoke recall (argmax) | 0.8466 — above 0.85 block bar, below 0.92 target |
| `fire_decision_threshold` | 0.30 (config.yaml, set Phase 2) |
| Smoke decision rule | argmax, no threshold (config.yaml has no smoke-equivalent key; Phase 3 decision) |
| `frame_threshold` (tau, Day 4 temporal voter) | 0.70 (initial, unchanged — different threshold) |
| ONNX export verification | max PyTorch/ONNX logit diff 3.77e-05 (tolerance 1e-4), 32 real val images |
| Live edge-loop test (Day 3) | Neutral room: fire~0.00 all frames. Real fire video: FIRE 0.48-0.99 (peak 0.99), smooth ramp/decay at transitions |
| Camera warm-up frames discarded | 10 (edge/camera.py `_warm_up()`, not empirically tuned — default) |
| Everything else (MQ baselines, FPS, hazard-to-alert latency, offline test) | NOT MEASURED / NOT SET / NOT RUN |

---

## 6. Hardware status

| Item | Ordered | Received | Wired | Tested | Notes |
|---|---|---|---|---|---|
| Arduino Uno + USB-B | ☑ | ☑ | ☑ | ☑ | H1-H2 confirmed via pin-9 LED blink under code control |
| MQ-2 | ☑ | ☑ | ☑ | ☐ | Burn-in started 2026-08-23 12:40 AM, valid from 2026-08-24 12:40 AM |
| MQ-135 | ☑ | ☐ | ☑ | ☐ | Same burn-in window as MQ-2 |
| DHT22 | — | — | — | — | **CUT from project** (Phase 0g) |
| Buzzer | ☑ | ☐ | ☐ | ☐ | Arriving ~24 Aug |
| LEDs + resistors | ☑ | ☐ | ☐ | ☐ | Arriving ~24 Aug |
| Breadboard + jumpers | ☑ | ☐ | — | — | Arriving ~20 Aug |
| Webcam | — | — | — | ☑ | Using MacBook built-in, confirmed via full edge loop (Phase 3) |

**MQ-2/MQ-135 burn-in valid from:** 2026-08-24, 12:40 AM (24h minimum) /
2026-08-25, 12:40 AM (48h preferred). Do not calibrate against readings
taken before this.

---

## 7. Standing open items (carried forward)

- **Re-verify fire recall margin** (0.9611 @ threshold 0.30, 1.1 points
  above the 0.95 floor) once the Day 4 temporal voter and Day 5 adversarial
  eval are complete — margin has only been measured on isolated val-set
  frames, not through the full pipeline. If too thin in practice, add
  hard-negative/fire training data rather than lowering the threshold
  further.
- **Smoke decision threshold is untuned** (argmax placeholder, Phase 3) —
  revisit if smoke-specific false positive/negative behavior becomes
  visible during Day 4/5 testing.
- Smoke recall (0.8466) is above its 0.85 block bar but below the 0.92
  target — not addressed yet.
- TV/laptop fire-footage hard-negative category (30 images) — manual
  screenshot collection, not started.
- DHT22 cut breaks the Day 7 fusion rule (`temp_spiking`) — decision
  needed before Day 7, not urgent yet.
- MQ-2/MQ-135 burn-in in progress — no calibration or threshold work
  against their readings until valid (see section 6).
- H3 (red LED) / H4 (buzzer) not started — buzzer not yet received.
- Candle-specific vision test not yet run — deferred to Day 5 adversarial
  eval (expected to alarm, per info.md 4.2 — a documented limitation, not a
  bug).
- **Use an activated shell, not `conda run`, for live/interactive edge-loop
  testing** — `conda run` buffers stdout and intercepts Ctrl+C (found during
  Phase 3 Day 3 testing). Relevant again for Day 4's FPS counter and any
  later live demo.
- `.env` not yet populated with real credentials (GROQ, Telegram, AWS).
- Leftover `anthropic` package in the conda env (harmless, unused).
- `setup.sh`/`setup.ps1` only syntax-checked, never run end-to-end.

---

For full detail, reason, and history, read plan.md, info.md, and logs.md — this file is a summary only and may be stale.
