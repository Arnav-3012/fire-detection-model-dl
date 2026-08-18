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
| 2 | Model training | UNBLOCKED — ready to start | — | Unblocked by Phase 1 completion; `data/train/`, `data/val/` ready as input |
| 3 | Edge loop v1 | NOT STARTED | — | — |
| 4 | Temporal smoothing | NOT STARTED | — | — |
| 5 | Adversarial evaluation | NOT STARTED | — | — |
| 6 | Arduino and sensors | NOT STARTED | — | DHT22 out of scope for the Arduino sketch (cut, Phase 0g) |
| 7 | Fusion logic | NOT STARTED | — | Blocked on the temp_spiking / DHT22 decision above |
| 8 | Agent part 1 | NOT STARTED | — | — |
| 9 | Agent part 2 | NOT STARTED | — | — |
| 10 | Cloud | NOT STARTED | — | — |
| 11 | Dashboard and evaluation | NOT STARTED | — | — |
| 12 | Documentation | NOT STARTED | — | — |

---

## 4. Five most recent key decisions (newest first)

1. **Phase 1 (Addendum 3):** Split strategy resolved — pool all three
   D-Fire splits (train/val/test, 21,527 images) and re-split 85/15 by
   class, ignoring D-Fire's original boundaries, because plan.md specifies
   no held-out test set beyond the Day 5/Day 11 evaluations. Also fixed a
   reproducibility bug during `long-story-short` review: the filename-
   collision fallback used Python's randomized-per-process `hash()`;
   replaced with `hashlib.md5` for a stable digest.
2. **Phase 1 (Addendum 2):** Manual hard-negative review completed. Final
   kept count: 195 across 6 categories (steam and red_orange_objects
   retried after high reject rates). A filename-collision bug in
   `fetch_hard_negatives.py` destroyed 3 already-approved `steam` images
   before being caught and fixed (`next_free_index()`).
3. **Phase 1:** D-Fire obtained via Kaggle mirror
   (`sayedgamal99/smoke-fire-detection-yolo`), not the OneDrive links in
   the original README — scriptable via Kaggle CLI. Class mapping
   confirmed from `data.yaml`: 0=smoke, 1=fire.
4. **Phase 0g:** DHT22 cut from the project (cost + availability). Creates
   an unresolved Day 7 fusion-rule gap — see section 2 above.
5. **Phase 0b:** Switched the compose-node LLM from Claude/`anthropic` SDK
   to Groq/`llama-3.1-8b-instant` — free tier sufficient for expected call
   volume, and speed matters for the verify → compose → notify chain.

---

## 5. Real measured values (logs.md "Live values" + Phase 1 results)

| Value | Current |
|---|---|
| Train images (neutral / smoke / fire) | 8,528 / 4,987 / 4,949 (18,464 total) |
| Val images (neutral / smoke / fire) | 1,505 / 880 / 873 (3,258 total) |
| Hard negatives folded into neutral | 195 (6 categories; TV/laptop category of 30 not yet collected) |
| Everything else (MQ baselines, model accuracy, FPS, latency, offline test) | NOT MEASURED / NOT SET / NOT RUN |

---

## 6. Hardware status

| Item | Ordered | Received | Wired | Tested | Notes |
|---|---|---|---|---|---|
| Arduino Uno + USB-B | ☑ | ☑ | ☐ | ☐ | Not yet wired or blink-tested |
| MQ-2 | ☑ | ☑ | ☐ | ☐ | In hand, burn-in not started |
| MQ-135 | ☑ | ☐ | ☐ | ☐ | Arriving ~20 Aug |
| DHT22 | — | — | — | — | **CUT from project** (Phase 0g) |
| Buzzer | ☑ | ☐ | ☐ | ☐ | Arriving ~24 Aug |
| LEDs + resistors | ☑ | ☐ | ☐ | ☐ | Arriving ~24 Aug |
| Breadboard + jumpers | ☑ | ☐ | — | — | Arriving ~20 Aug |
| Webcam | — | — | — | ☑ | Using MacBook built-in |

**MQ-2 burn-in started:** NOT STARTED — still the critical path item.

---

## 7. Standing open items (carried forward)

- TV/laptop fire-footage hard-negative category (30 images) — manual
  screenshot collection, not started.
- DHT22 cut breaks the Day 7 fusion rule (`temp_spiking`) — decision
  needed before Day 7, not urgent yet.
- `.env` not yet populated with real credentials (GROQ, Telegram, AWS).
- Leftover `anthropic` package in the conda env (harmless, unused).
- `setup.sh`/`setup.ps1` only syntax-checked, never run end-to-end.

---

For full detail, reason, and history, read plan.md, info.md, and logs.md — this file is a summary only and may be stale.
