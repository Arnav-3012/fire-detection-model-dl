# FireWatch

IoT fire and gas hazard detection with local edge inference and agentic response.

A laptop-hosted edge node detects fire or smoke from an ESP32-CAM video
stream, cross-checks it against an ESP32 gas-sensor board (both over WiFi),
and produces a verified alert that reaches a real phone — with the internet
disconnected. The sensor board also sounds its own buzzer on its own gas
verdict, with no host involved.
Detection is fully deterministic and runs on-device; an LLM agent only
composes and delivers the alert afterward. Emergency dispatch is always
**simulated** — see [Safety and disclosures](#safety-and-disclosures) before
anything else.

---

## Table of contents

1. [Architecture](#architecture)
2. [Repository layout](#repository-layout)
3. [Setup](#setup)
4. [Running it](#running-it)
5. [Hardware](#hardware)
6. [Model](#model)
7. [Evaluation](#evaluation)
8. [Dashboard](#dashboard)
9. [Cloud second opinion](#cloud-second-opinion)
10. [Safety and disclosures](#safety-and-disclosures)
11. [Known limitations](#known-limitations)
12. [Project docs](#project-docs)

---

## Architecture

```
 ESP32-CAM ──WiFi──► camrelay.py ──► vision.py (ONNX MobileNetV3-Small)
   (MJPEG)       (dashboard backend:      ──► TemporalVoter (N-of-M) ──┐
                  one upstream conn,                                    │
                  many consumers)                                       │
                                                                        │
 ESP32 sensor ──WiFi POST──► wifi_source.py ──► gas_high = board's ─────┼──► fusion.py
  board (MQ-2/MQ-135  (1 Hz JSON)  (ingest inside   own GAS_HIGH state   │        │
  + buzzer)                         edge/main.py)                        │        │
       └─ buzzes AUTONOMOUSLY on its own verdict — no WiFi, no host needed        │
                                                                     Level: SAFE/WATCH/WARNING/CRITICAL
                                                                                  │
                                          ┌───────────────────────────────────────┘
                                          ▼
                          1. Local alarm — before any network call
                          2. POST /incident (best-effort, 2s timeout, never blocks step 1)
                          3. Cloud second opinion on a GAS_HIGH rising edge (advisory only,
                             background thread, result goes to the dashboard — never to fuse())
                                          │
                                          ▼
                           agent/graph.py (LangGraph state machine)
                    verify → locate (fire station, display-only) → compose (Groq LLM,
                    template fallback) → notify_owner (Telegram) → escalate (Twilio SMS)
                    → wait (cancel window) → {cancelled | simulate_dispatch}
                                          │
                                          ▼
                       dispatch_log.jsonl (SIMULATED: true) + S3 archive (CRITICAL only)
```

**Design principle:** deterministic detection, agentic response. The model
and threshold/vote logic decide whether something is a hazard. The LLM is
only ever asked to phrase a sentence about a decision that has already been
made — it never sees raw sensor values and never gates escalation. If the
LLM call fails, a deterministic template ships instead.

**The core architectural claim:** the local alarm is driven before the
network is touched, and a network failure can never suppress it. Since the
two-board migration this is stronger than before: the sensor board owns its
buzzer and sounds it on its own GAS_HIGH verdict, so a dead WiFi link, a
stopped edge loop or a crashed laptop costs telemetry and notifications —
never the gas alarm.
This is what makes the offline demo — disconnect the network mid-run, the
alarm still fires — meaningful rather than a demo trick.

Full rationale for every architectural choice (why a laptop instead of a
Raspberry Pi, why simulated dispatch instead of real dispatch, why fusion
instead of vision-only) is in [`plan.md`](plan.md) section 1.

---

## Repository layout

```
firewatch/
├── config.example.yaml   # tracked template — copy to config.yaml and fill in your own values
├── config.yaml            # gitignored — your real coordinates, serial port, S3 bucket
├── .env.example           # tracked — credential names only
├── .env                   # gitignored — real credentials
│
├── arduino/
│   ├── sensor_esp32_node/  # ESP32 DevKit firmware: MQ-2/MQ-135, per-boot baseline, ratio thresholds, own buzzer, WiFi POST
│   ├── cam_node/           # ESP32-CAM firmware: MJPEG /stream, multi-network WiFi
│   ├── sensor_calibration_capture/  # calibration logging sketch
│   └── sensor_node/        # RETIRED Arduino Uno sketch (pre-Phase 13), kept for history
│
├── train/                 # dataset prep, training, ONNX export, leakage checks
├── models/                # gitignored — checkpoints and ONNX exports (see Model below)
│
├── edge/                  # the always-running local loop
│   ├── camera.py          #   frame grabber (reads the camera relay's MJPEG stream)
│   ├── camrelay.py        #   ESP32-CAM relay: one upstream connection, many consumers
│   ├── vision.py          #   ONNX inference + TemporalVoter (N-of-M voting)
│   ├── wifi_source.py     #   WiFi ingest server for the sensor board (default transport)
│   ├── sensors.py         #   serial reader (fallback transport, same interface)
│   ├── fusion.py          #   the SAFE/WATCH/WARNING/CRITICAL decision table
│   ├── livelog.py         #   1 Hz rolling snapshot (readings, level, board state, thresholds) for the dashboard
│   └── main.py             #   entry point — the loop
│
├── agent/                 # response only, never detection
│   ├── graph.py            #   LangGraph state machine
│   ├── compose.py          #   Groq LLM alert text + deterministic fallback
│   ├── locate.py           #   Overpass nearest-fire-station lookup (display-only)
│   ├── escalate.py         #   Twilio SMS to the developer's own number
│   ├── feedback.py         #   append-only outcome log (data collection, no RL)
│   ├── tools.py             #   simulate_dispatch() — writes dispatch_log.jsonl
│   └── server.py           #   FastAPI POST /incident
│
├── cloud/
│   ├── uploader.py         # S3 archive, CRITICAL incidents only
│   ├── second_opinion.py   # advisory Lambda call on a GAS_HIGH rising edge (never reaches fusion)
│   └── lambda_infer/       # Lambda handler + preprocessing shared bit-for-bit with edge/vision.py
│
├── dashboard/
│   ├── backend/            # read-only FastAPI (port 8001) + camera relay + /ws/live
│   └── frontend/           # Vite + React
│
├── eval/                  # adversarial videos, threshold sweeps, trial logging
├── scripts/                # data capture / review helpers, deploy_lambda.py (deploy + --delete teardown)
├── logs/                   # gitignored — local hardware trial logs + archived/superseded snapshots
│
├── ARCHITECTURE.md          # system map + which doc/log/data file to use when
├── plan.md                 # full specification and rationale
├── info.md                 # operating rules (safety, quality bars, standards)
├── logs.md                 # append-only build log — every measured result, ever
└── context.md               # regenerated summary — current state, fast to read
```

---

## Setup

```bash
git clone <this-repo>
cd firewatch

# Python 3.11 (not 3.12 — some ML wheels lag behind)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env               # fill in your own credentials
cp config.example.yaml config.yaml # fill in your own coordinates / serial port / S3 bucket
```

`.env` needs:

```
GROQ_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
TWILIO_TO_NUMBER=
```

`config.yaml` needs the ESP32-CAM's stream URL (`camera.stream_url`), your
real (or approximate) coordinates for the fire-station lookup, and an S3
bucket name you own. The sensor board's WiFi networks go in
`arduino/sensor_esp32_node/secrets.h` (gitignored; copy `secrets.example.h`). `config.example.yaml` documents every key inline — read it before
editing, values are not arbitrary (thresholds are calibrated, not guessed).

For the dashboard frontend:

```bash
cd dashboard/frontend && npm install
```

---

## Running it

**Start order matters** since Phase 13f: the edge loop reads camera frames
through the dashboard backend's relay, so the backend comes first.

**1. Dashboard backend** (also hosts the camera relay):

```bash
uvicorn dashboard.backend.main:app --port 8001
```

**2. Agent server** (only needed to receive `/incident` POSTs and send alerts):

```bash
uvicorn agent.server:app --port 8000
```

**3. Edge loop (detection + local alarm + agent notify):**

```bash
python edge/main.py
```

Prints rolling FPS, the current fusion level, and — since Phase 13f — the
**video source it chose**, so a silent fall back to the laptop webcam is
impossible to miss. The buzzer responds immediately and locally; in fact
the sensor board buzzes on its *own* verdict with no host involvement at
all, so it keeps working even if this process is not running.

If the edge loop fails with `Could not open video stream at
'http://127.0.0.1:8001/api/camera/stream'`, the backend (step 1) is not
running. Check the camera separately with
`curl http://127.0.0.1:8001/api/camera/status` — it should report
`"live": true`.

**4. Frontend:**

```bash
cd dashboard/frontend && npm run dev
```

The home page shows the live camera, gas readings and system status — see
[Dashboard](#dashboard).

### Transport configuration

Both boards are WiFi. Relevant `config.yaml` keys:

| Key | Meaning |
|---|---|
| `sensors.transport` | `wifi` (board POSTs to the edge loop) or `serial` (USB fallback, still supported) |
| `sensors.ingest_port` | where the edge loop listens for board POSTs (default 8002) |
| `camera.stream_url` | the ESP32-CAM's MJPEG URL — **update after any network change**, the camera is a server and cannot be auto-discovered |
| `camera.edge_source` | where the edge loop reads frames; normally the relay, so it and the dashboard can both see the camera |

The sensor board finds this host by mDNS, then a bounded subnet scan, so
moving between home WiFi and a phone hotspot needs **no reflash**. Register
each network in `arduino/sensor_esp32_node/secrets.h` (gitignored).

**A single trial run**, logged to `eval/results.csv`:

```bash
python eval/run_trial.py --label <name> --expected <SAFE|WATCH|WARNING|CRITICAL>
```

Use an activated shell (`conda activate` / `source .venv/bin/activate`), not
`conda run` — the edge loop needs a real TTY for clean serial and camera
behavior.

---

## Hardware

Two boards since Phase 13 (the Arduino Uno is retired):

| Component | Pin | Notes |
|---|---|---|
| ESP32 DevKit (sensor board) | — | Runs `arduino/sensor_esp32_node`; WiFi POST at 1 Hz, own buzzer |
| MQ-2 (gas/smoke) | GPIO34 | Analog only, via a 22k/10k divider (5 V sensor → 3.3 V ADC). Never the module's D0 comparator pin |
| MQ-135 (air quality) | GPIO35 | Second independent gas signal, same divider |
| Active buzzer | GPIO33 | Driven by the board's own GAS_HIGH state — fires with no host involved |
| AI-Thinker ESP32-CAM (camera board) | — | Runs `arduino/cam_node`; MJPEG `/stream`, one client at a time (hence the relay). The module shipped with a GC2145 sensor, not the OV2640 the plan assumed — see `logs.md` Phase 13a-2 for the colour/driver consequences |

DHT22 (temperature) was cut from the build — cost and availability — so
`temp_spiking()` is permanently stubbed `False`. This is a disclosed,
deliberate scope cut, not an oversight; see `plan.md` section 1, item 8, and
`logs.md` for the decision record.

Full pin map, build order (H1–H9), power budget, MQ sensor theory, and a
wiring troubleshooting table are in `plan.md` sections 5 and Appendix A/B —
read those before touching hardware if you have no prior electronics
experience; that's who they were written for.

**Gas thresholds are computed by the firmware, per boot.** The sensor board
waits for a slope-based warm-up gate, captures a fresh baseline, then derives
WARN/DANGER from ratio thresholds and tracks slow baseline drift (capped per
hour, frozen during an alarm). Absolute hard ceilings back this up so a slow
leak can't be learned away. The board publishes its thresholds and state
with every reading; `config.yaml`'s gas values are a legacy fallback only.
The full calibration history is in `logs.md` Phase 13b.

---

## Model

Three-class classifier (`neutral` / `smoke` / `fire`), MobileNetV3-Small
fine-tuned from ImageNet weights, exported to ONNX for CPU inference at
3–5× the speed of raw PyTorch.

**Current production model: v4**, promoted 2026-09-05.

| Metric | Value | Block bar |
|---|---|---|
| Fire recall @ threshold 0.30 | 0.9575 | ≥ 0.95 |
| Fire precision @ threshold 0.30 | 0.8664 | ≥ 0.80 |
| Smoke recall @ 0.45 (argmax-AND rule) | 0.8511 | ≥ 0.85 |
| Validation accuracy | 0.9129 | ≥ 0.85 |
| Macro F1 | 0.9065 | ≥ 0.85 |
| ONNX export/PyTorch diff | 5.99e-05 | ≤ 1e-4 |

v4 is the first checkpoint to clear the 0.85 smoke-recall bar and the first
to widen the fire-recall margin after three successive retrains narrowed it
(1.11 → 0.88 → 0.41 → 0.75 points). Full training history, every prior
checkpoint (v1–v3, archived under `models/*_superseded.*`), and the reasoning
behind every threshold choice are in `logs.md`.

**Disclosure:** v4's hard negatives for a specific bright-light/textured-wall
false-positive scenario include 60 webcam frames and one held-out video clip
in which the developer, and in some frames one to three other people, are
visible. This data was kept as captured — not recaptured people-free — a
deliberate developer decision, disclosed here and in `logs.md` rather than
described as clean or background-only. The data never leaves the local
machine (`data/` is gitignored) and is not part of any uploaded corpus.

To retrain or re-export:

```bash
python train/prepare_data.py --clean --extra-fire-positive <dirs...>
python train/train_classifier.py --checkpoint models/fire_mnv3_vN.pt
python eval/threshold_sweep.py --checkpoint models/fire_mnv3_vN.pt
python eval/smoke_threshold_sweep.py --checkpoint models/fire_mnv3_vN.pt
python train/export_onnx.py --checkpoint models/fire_mnv3_vN.pt --output models/fire_mnv3_vN.onnx
```

`export_onnx.py` verifies its own output against real PyTorch inference on
32 validation images and exits non-zero if the diff exceeds 1e-4 — do not
promote a model without this check, regardless of how good the eval numbers
look.

---

## Evaluation

Adversarial false-positive testing against five self-recorded 30-second
clips plus a held-out scenario clip (videos are gitignored — up to ~290MB
each, over GitHub's file-size limit; re-record locally to reproduce):

| Scenario | Block bar | v4 result |
|---|---|---|
| Sunset through window | ≤ 1 alarm | 0 |
| Steam from kettle | ≤ 1 alarm | 0 fire alarms (5 smoke WATCH events — documented limitation) |
| Person in red clothing | 0 alarms | 0 |
| TV showing fire footage | ≤ 2 alarms | 6 — documented known limitation, mitigated at the fusion layer |
| Candle | expected to alarm | alarms, as required |

```bash
python eval/run_eval.py --model-path models/fire_mnv3.onnx --adversarial-dir eval/adversarial
python eval/run_trial.py --label <name> --expected <LEVEL>   # logs one row to eval/results.csv
```

These v4 results were measured on the laptop-webcam path. After the move to
the ESP32-CAM (and `votes_needed` 5 → 3), the TV/laptop test and the
evaluation trials were re-run by the developer on the two-board hardware and
reported passing; the per-run counts are recorded in `logs.md` once logged.

`eval/results.csv` is the single source of truth for hazard/non-hazard trial
outcomes and latency — nothing in a report is typed by hand.

---

## Dashboard

Read-only FastAPI backend (port 8001) + Vite/React frontend, four tabs. The
backend never writes to edge-loop or agent state; it reads
`dispatch_log.jsonl`, `eval/alert_feedback.csv`, `eval/results.csv`, the
live snapshot `edge/livelog.py` writes each second, and the second-opinion
sidecar. It also hosts the camera relay.

**Overview (home)** is live-first, fed by one 1 Hz WebSocket (`/ws/live`):

- **Status strip** — the live fused level plus edge-feed age, sensor-board
  state, camera liveness, threshold source and time since the last
  incident. At WARNING/CRITICAL the whole strip takes the level colour.
- **Live camera** — MJPEG via the relay, with a LIVE / SIGNAL LOST badge
  driven by the relay's own frame age (a frozen MJPEG image otherwise looks
  live), the level, a `p_fire` meter and fullscreen. Paused while the
  browser tab is hidden.
- **Right now** — one bullet bar per sensor (reading against the board's
  baseline / warn / danger, with headroom) and a 60 s `p_fire` sparkline.
- **Gas chart** — *Hazard index* view (each reading mapped onto its own
  sensor's thresholds at that second: baseline 0, warn 1, danger 2, so both
  sensors share one axis) or *Raw ADC* lanes with the thresholds drawn as
  step lines that follow the firmware's drift. 1 / 5 / 10 min windows.
  Warm-up periods are shaded; config.yaml values are never drawn.
- Nearest fire station (display-only), most recent event, cloud second
  opinion, incident counts and the fusion-level timeline.

**Live Incidents**, **Historical Archive** (S3) and **Evaluation Trials**
are unchanged.

---

## Cloud second opinion

On the rising edge of the board's GAS_HIGH, `cloud/second_opinion.py`
sends the current frame to an AWS Lambda running the **same v4 ONNX model
with bit-identical preprocessing**, and the dashboard shows LOCAL next to
CLOUD with an agree/disagree state. Disagreement is the signal worth a look.

It is **advisory only**: the call runs on a background thread after the
local alarm, its result goes to a sidecar file the dashboard reads, and
nothing flows back into `fuse()`. Off by default
(`aws.second_opinion.enabled`), capped per session, with a cooldown. Deploy
and tear down with `scripts/deploy_lambda.py` (`--delete` removes the
function, URL, role and staged build). The design, packaging constraints
and measured local-vs-cloud agreement are in `logs.md` Phase 13g.

---

## Safety and disclosures

- **Dispatch is always simulated.** `agent/tools.py`'s `simulate_dispatch()`
  writes a JSON packet to a local file — `dispatch_log.jsonl` — with
  `"SIMULATED": true` and an explicit note that no emergency service was
  contacted. The system never places a call, sends an SMS, or makes an API
  request to any real emergency service, fire department, or 101/112
  equivalent, under any code path.
- **Fire station lookups are display-only.** Overpass returns the nearest
  fire station's name and number so *you* can call it yourself if a real
  fire station number would help — the system never dials or messages that
  number itself, on any channel, under any condition.
- **The LLM never decides whether there is a fire.** Detection is
  model → threshold → temporal vote → fusion table, entirely deterministic.
  The LLM (Groq) is used in exactly one place: composing the human-readable
  alert sentence, with a deterministic template fallback if the API fails.
- **Twilio SMS is a real-cost service**, sent only to the developer's own
  verified number — never a broadcast, never an emergency contact.
- **Training data disclosure:** see [Model](#model) above — a specific hard-
  negative dataset includes people in frame, kept and disclosed rather than
  silently omitted or falsely described as clean.
- Full rules this project operates under are in `info.md` section 2
  ("Absolute rules — never violate these").

---

## Known limitations

- **TV/laptop screens showing fire footage** produce more alarms than the
  target bar (6, target ≤1). Vision alone cannot distinguish a screen from
  a real flame at the resolution used; mitigated by fusion's rule that
  vision-only detections cap at WARNING, never reach CRITICAL without gas
  corroboration.
- **Steam** is a sustained smoke-detector trigger (vision alone cannot
  separate water vapor from smoke). Same fusion-layer mitigation as above.
- **Smoke recall (0.8511)** clears the block bar but is well below the 0.92
  target — smoke-before-flame is the product's early-warning promise, and
  this remains the model's weakest class.
- **DHT22 (temperature) was cut** from the hardware — `temp_spiking()` is
  permanently `False`. One of fusion's five decision rules (rule 2:
  fire + rapid temperature rise → CRITICAL) can never fire as a result.
- **The ESP32-CAM's IP is hardcoded** in `camera.stream_url`. The camera is
  a server, so it can't use the sensor board's discovery; update the URL
  after changing networks.
- **The cloud second opinion needs internet.** It is advisory, so losing it
  never affects detection — it just shows no opinion.
- **GPS is not implemented** — coordinates in `config.yaml` are hardcoded,
  by design (a GPS module will not lock indoors, per `plan.md` section 1).

See `logs.md`'s "Open items" sections and `context.md` section 7 for the
complete, current list — this section only covers the ones a user of the
system should know before relying on it.

---

## Project docs

This README is a map, not the source of truth. For anything not covered
above:

| Document | What's in it |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System map + full guide to which doc/log/data file to use for a given task |
| [`plan.md`](plan.md) | Full specification: architecture rationale, hardware BOM and pin map, data collection plan, day-by-day schedule, troubleshooting appendix |
| [`info.md`](info.md) | Operating rules: absolute safety constraints, code standards, quality bars, when to stop and ask |
| [`context.md`](context.md) | Fast-recovery summary of current state — read this first if picking the project back up |
| [`logs.md`](logs.md) | Append-only build log — every phase, every measured result, every decision and why, never overwritten |
