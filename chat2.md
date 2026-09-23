---
name: chat2
description: FireWatch Phase 13 (ESP32-CAM migration) planning session — full context for continuing hardware wiring in a fresh chat
---

# FireWatch — Phase 13 (ESP32-CAM) Session Context

## Status
Documentation finalized in plan.md §10 and context.md via Claude Code —
confirmed zero code files touched, only plan.md/context.md edited.
Hardware physically in hand, identified from photos this session.
Wiring NOT yet started — this is the next concrete step.

## Hardware confirmed in-hand (verified from photos this session)
- **AI-Thinker ESP32-CAM** — confirmed via board silkscreen "ESP32-CAM"
  and back-side chip label "ESP32-S325, WiFi+BT SoC Inside"
- **OV2640 camera module** — separate ribbon-cable piece, labeled
  "RHYX M21-45", plugs into the ESP32-CAM's ribbon connector
- **FTDI/USB-to-serial programmer**, labeled "HW-417C", USB-C port.
  Pin labels: DCD, DSR, GND, RI, RXD, VCC, RTS, DTR/TXD on one row;
  PWRENTEN, SLEEP, CTS, 3.3V, 5V, RXL, TXL on the other.
  CONFIRMED supports 3.3V logic level (has a separate 3.3V pin from
  5V) — safe for the ESP32-CAM's 3.3V-only GPIO pins.
- **Existing MQ-2 and MQ-135 sensors** (Flying-Fish brand modules),
  already breadboard-mounted from the original Arduino build —
  reusable, wiring needs to be redone to ESP32-CAM pins instead of
  Arduino's.
- Breadboard and F-F jumper wires — reusable from original build.
  Pin-spacing compatibility with ESP32-CAM's header not yet explicitly
  re-verified (was fine on Arduino, likely fine here given standard
  2.54mm/0.1" pitch — worth a visual check when wiring starts).

## Why this migration is happening
Faculty saw the completed, presented v4 prototype (Arduino Uno + laptop
webcam + fusion + Telegram/Twilio/dashboard/S3, all working) and
suggested this ESP32-CAM wireless migration as an "advancement toward
final prototype" — this is a NEXT ITERATION, not a fix to the graded
submission. The current Arduino-based v4 system remains intact,
working, and unaffected by this planning.

## Finalized architecture decisions (already written into plan.md §10)

1. **Inference location**: runs in AWS Lambda (cloud), using the
   EXISTING v4 ONNX model, UNMODIFIED. Explicitly NOT on-device TinyML.
   Reasoning (researched in depth this session): MobileNetV3-Small,
   even INT8-quantized, exceeds the ESP32's realistic memory/compute
   budget for real-time inference. Genuine on-device TinyML would
   require an entirely new, much smaller architecture (tens of
   thousands of parameters, not millions; likely 96x96 or 128x128
   input instead of current resolution) trained from scratch via
   TensorFlow Lite Micro (not ONNX — no ESP32-compatible ONNX runtime
   exists), with an honest expected accuracy drop below v4's proven
   numbers (fire recall 0.9575, smoke recall 0.8511). This mirrors real
   production patterns (Ring/Wyze-style cameras relay to cloud/hub
   compute rather than running detection on the camera's own tiny
   chip) — MobileNet-class models are designed for phone/edge-device-
   class hardware, not bare microcontrollers.

2. **Cost**: calculated as genuinely $0 for realistic trial/demo usage
   (~15hrs total estimated, not continuous 24/7), at 640x480@5fps:
   ~270,000 requests (27% of AWS Lambda's permanent 1M free-tier
   requests/month) and ~81,000 GB-seconds (20% of the 400,000 free
   GB-seconds/month) — real math against real, current AWS pricing,
   not an estimate.

3. **Camera target**: 640x480 @ 5fps. OV2640's real proven capability
   is 25-30fps at VGA with on-chip JPEG compression (~12-28KB/frame),
   but 5fps is the practical target to balance real-time feel against
   WiFi/Lambda overhead.

4. **Connectivity — two switchable network contexts via WiFiManager**:
   - HOME: ESP32 connects directly to home WiFi (simple WPA2-Personal).
   - COLLEGE: college WiFi requires SAP ID + password via a CAPTIVE
     PORTAL (confirmed — not WPA2-Enterprise). A captive portal cannot
     be handled by ESP32 firmware directly (no browser/portal
     interaction capability on a microcontroller). SOLUTION: the
     developer's laptop authenticates on college WiFi normally
     (logging into the portal as usual), then shares that connection
     via macOS Internet Sharing as a new, simple WPA2-Personal hotspot.
     The ESP32 connects to THAT shared hotspot, never touching the
     college network/portal directly.
   - WiFiManager handles switching between these two saved-network
     contexts via a reset-and-reconfigure flow (temporary setup
     hotspot, web-based credential entry) — no reflashing needed when
     moving between home and college.
   - Rejected alternatives, with reasoning: mobile hotspot (viable
     fallback, but laptop-sharing preferred since it uses the real
     institutional network at college); WPA2-Enterprise direct
     connection (not actually the problem — it's a captive portal, not
     enterprise auth); IT-side MAC whitelisting (not pursued, uncertain
     approval timeline).

5. **No-WiFi fallback**: a total WiFi outage means NO vision-based
   detection at all — this is an explicit, disclosed architectural
   trade-off of cloud inference, not hidden. Mitigation: the ESP32
   monitors MQ-2/MQ-135 readings locally, against hardcoded threshold
   values mirroring fusion.py's calibrated warn/danger thresholds, and
   drives the buzzer DIRECTLY from its own GPIO — entirely independent
   of WiFi/cloud. System degrades gracefully from "vision+gas fusion,
   cloud-verified" to "gas-only, local-only" rather than going fully
   silent.

6. **Data flow, full pipeline**:
   ESP32-CAM (camera + MQ-2 + MQ-135) --WiFi--> AWS Lambda (runs v4
   ONNX model on each frame, computes gas_high using fusion.py's
   existing logic reused/ported, not reimplemented) --> fusion result
   relayed to FastAPI backend's NEW WebSocket endpoint (does not exist
   yet) --> broadcast to connected React dashboard clients --> rendered
   on a NEW "Live View" dashboard tab.

7. **Live View feature** (new dashboard tab, not yet built): real-time
   camera feed via WebSocket, AI classification badge overlaid
   (SAFE/WATCH/WARNING/CRITICAL, existing fusion-level color language
   already established in the dashboard), PLUS a live-updating p_fire
   confidence value/indicator shown alongside the feed so a viewer can
   watch confidence build toward an alarm in real time.

8. **Remote access**: noted as a natural consequence once the
   dashboard backend is actually DEPLOYED (not just localhost) —
   contingent on completing that separate, previously-discussed-but-
   not-yet-executed deployment step (Vercel/Render).

9. **Arduino Uno + arduino/sensor_node.ino**: FULLY RETIRED by this
   migration — the ESP32-CAM replaces the Arduino's role entirely
   (camera + sensors + now also networking), not supplementing it.

10. **OPEN DESIGN QUESTION, explicitly flagged, NOT yet resolved**: how
    info.md 2.2's "local alarm before any network attempt" principle
    applies now that VISION inference is inherently cloud-dependent.
    The gas-only local fallback (#5) is the current answer for
    connectivity loss specifically, but this deserves explicit
    discussion/confirmation before implementation begins, not quiet
    assumption that it's fully resolved.

11. **STATUS**: still NOT STARTED for actual implementation. This
    session finalized the PLAN and confirmed hardware in-hand; no
    wiring, firmware, Lambda function, WebSocket endpoint, or dashboard
    code has been built yet.

## Language/toolchain decision
ESP32 firmware: **C++ via Arduino IDE** (ESP32 Arduino core). NOT
ESP-IDF (unnecessary added complexity for this scope). NOT ONNX (that
remains laptop/cloud-side only, via the existing v4 pipeline).

## Explicitly NOT pursuing (discussed in depth, deliberately parked)
- **On-device TinyML / quantized MobileNetV3 on the ESP32 itself** —
  researched thoroughly this session (dynamic vs static quantization,
  quantization-aware training, TensorFlow Lite Micro toolchain, real
  memory/compute math). Rejected due to real hardware limits and
  unacceptable accuracy-risk given another demo is coming soon.
- **Federated Learning simulation** (single-board "rotational client"
  architecture simulating multiple FL clients on one ESP32) — this was
  raised ONLY as a hypothetical/example idea by the user during this
  session, explicitly marked as NOT a real plan and NOT to be carried
  into future work or treated as project scope.

## Next actual step (not started yet)
Physical wiring walkthrough: MQ-2, MQ-135, and buzzer onto the
ESP32-CAM's GPIO pins (exact pin assignments TBD — need to consult the
AI-Thinker ESP32-CAM pinout reference at the start of the next
session), one component at a time, same incremental "wire it, test it,
confirm before moving on" discipline used for the original Arduino
build (info.md's hardware-beginner-friendly approach). FTDI programmer
wiring to the ESP32-CAM for flashing also not yet done — requires
specific GPIO0-to-GND-during-flash-mode handling, a known fiddly step
on this board worth extra care and patience.