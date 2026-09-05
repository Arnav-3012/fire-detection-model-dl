# FireWatch

IoT fire and gas hazard detection with local edge inference and agentic response.

A laptop-hosted edge node with a webcam and an Arduino sensor board detects
fire or smoke locally, cross-checks it against gas readings, and produces a
verified alert that reaches a real phone — with the internet disconnected.
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
9. [Safety and disclosures](#safety-and-disclosures)
10. [Known limitations](#known-limitations)
11. [Project docs](#project-docs)

---

## Architecture

```
 webcam ──► vision.py (ONNX MobileNetV3-Small) ──► TemporalVoter (N-of-M) ──┐
                                                                             │
 Arduino ──► sensors.py (MQ-2 / MQ-135, serial) ──► gas_high threshold ─────┼──► fusion.py
                                                                             │        │
                                                                     Level: SAFE/WATCH/WARNING/CRITICAL
                                                                             │
                                          ┌──────────────────────────────────┘
                                          ▼
                          1. Local buzzer + LED — fires unconditionally, before any network call
                          2. POST /incident (best-effort, 2s timeout, never blocks step 1)
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

**The core architectural claim:** local alarm (buzzer + LED) is driven
before the network is touched, and a network failure can never suppress it.
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
├── arduino/sensor_node/sensor_node.ino   # Arduino sketch: MQ-2/MQ-135 read + buzzer control
│
├── train/                 # dataset prep, training, ONNX export, leakage checks
├── models/                # gitignored — checkpoints and ONNX exports (see Model below)
│
├── edge/                  # the always-running local loop
│   ├── camera.py          #   webcam frame grabber
│   ├── vision.py          #   ONNX inference + TemporalVoter (N-of-M voting)
│   ├── sensors.py         #   threaded Arduino serial reader
│   ├── fusion.py          #   the SAFE/WATCH/WARNING/CRITICAL decision table
│   ├── livelog.py         #   1 Hz rolling snapshot for the dashboard's live chart
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
├── cloud/uploader.py       # S3 archive, CRITICAL incidents only
│
├── dashboard/
│   ├── backend/            # read-only FastAPI (port 8001)
│   └── frontend/           # Vite + React
│
├── eval/                  # adversarial videos, threshold sweeps, trial logging
├── scripts/                # data capture / scraping / review helpers
│
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

`config.yaml` needs your machine's Arduino serial port, your real (or
approximate) coordinates for the fire-station lookup, and an S3 bucket name
you own. `config.example.yaml` documents every key inline — read it before
editing, values are not arbitrary (thresholds are calibrated, not guessed).

For the dashboard frontend:

```bash
cd dashboard/frontend && npm install
```

---

## Running it

**Edge loop (detection + local alarm + agent notify), from the repo root:**

```bash
python edge/main.py
```

Prints rolling FPS and the current fusion level. The buzzer and LED respond
immediately and locally — no network dependency. WARNING/CRITICAL levels
also POST to the agent (best-effort, 2s timeout).

**Agent server** (separate terminal, only needed to receive `/incident` POSTs):

```bash
uvicorn agent.server:app --port 8000
```

**Dashboard** (separate terminals):

```bash
uvicorn dashboard.backend.main:app --port 8001
cd dashboard/frontend && npm run dev
```

**A single trial run**, logged to `eval/results.csv`:

```bash
python eval/run_trial.py --label <name> --expected <SAFE|WATCH|WARNING|CRITICAL>
```

Use an activated shell (`conda activate` / `source .venv/bin/activate`), not
`conda run` — the edge loop needs a real TTY for clean serial and camera
behavior.

---

## Hardware

| Component | Pin | Notes |
|---|---|---|
| MQ-2 (gas/smoke) | A0 | Analog only — never the module's D0 digital pin, which is a hand-tuned comparator useless for fusion |
| MQ-135 (air quality) | A1 | Second independent gas signal |
| Active buzzer | D8 | Local alarm — fires unconditionally |
| Webcam | USB | MacBook built-in used throughout; any `cv2`-compatible camera works |

DHT22 (temperature) was cut from the build — cost and availability — so
`temp_spiking()` is permanently stubbed `False`. This is a disclosed,
deliberate scope cut, not an oversight; see `plan.md` section 1, item 8, and
`logs.md` for the decision record.

Full pin map, build order (H1–H9), power budget, MQ sensor theory, and a
wiring troubleshooting table are in `plan.md` sections 5 and Appendix A/B —
read those before touching hardware if you have no prior electronics
experience; that's who they were written for.

**MQ sensor calibration is a burn-in-then-measure procedure, not a guess.**
Readings taken before 24–48 hours of continuous power are not valid — see
`plan.md` section 5.5 for the exact procedure and `config.example.yaml` for
what the calibrated values in this build measured.

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

`eval/results.csv` is the single source of truth for hazard/non-hazard trial
outcomes and latency — nothing in a report is typed by hand.

---

## Dashboard

Read-only FastAPI backend (port 8001) + Vite/React frontend. Five tabs:
Overview (live fusion status, sensor chart), Live Incidents, Historical
Archive (S3), Evaluation Trials, Nearest Fire Station. The backend never
writes to the edge loop's state — it only reads `dispatch_log.jsonl`,
`eval/alert_feedback.csv`, `eval/results.csv`, and the live sensor snapshot
edge/main.py writes each second.

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
| [`plan.md`](plan.md) | Full specification: architecture rationale, hardware BOM and pin map, data collection plan, day-by-day schedule, troubleshooting appendix |
| [`info.md`](info.md) | Operating rules: absolute safety constraints, code standards, quality bars, when to stop and ask |
| [`context.md`](context.md) | Fast-recovery summary of current state — read this first if picking the project back up |
| [`logs.md`](logs.md) | Append-only build log — every phase, every measured result, every decision and why, never overwritten |
