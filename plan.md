# FireWatch — Project Plan

**IoT fire and gas hazard detection with edge inference and agentic response**

| | |
|---|---|
| **Owner** | Solo build |
| **Start** | 18 August 2026 |
| **Deadline** | 30 August 2026 |
| **Working days** | 12 |
| **Coding** | Claude Code in VS Code |
| **Planning** | Claude chat |

---

## Table of contents

1. [What changed from the original idea](#1-what-changed-from-the-original-idea)
2. [What we are actually building](#2-what-we-are-actually-building)
3. [Immediate action list](#3-immediate-action-list)
4. [Track A — Software](#4-track-a--software)
5. [Track B — Hardware](#5-track-b--hardware)
6. [Data collection plan](#6-data-collection-plan)
7. [Day-by-day schedule](#7-day-by-day-schedule)
8. [Claude Code prompts per phase](#8-claude-code-prompts-per-phase)
9. [Cut list](#9-cut-list)
10. [Phase 13 — ESP32-CAM migration (finalized plan, NOT STARTED)](#10-phase-13--esp32-cam-migration-finalized-plan-not-started)
11. [Appendix A — Hardware primer](#appendix-a--hardware-primer)
12. [Appendix B — Troubleshooting](#appendix-b--troubleshooting)
13. [Appendix C — Report checklist](#appendix-c--report-checklist)

---

## 1. What changed from the original idea

| # | Original plan | Revised plan | Reason |
|---|---|---|---|
| 1 | Auto-dial emergency services | Simulated dispatch, full payload logged but never transmitted | False emergency reporting is a criminal offence (BNS §217). No public dispatch API is available. Real products (Nest, ADT) verify with a human before dispatch anyway |
| 2 | Camera → cloud → model decides | Model runs locally on the edge device. Cloud logs and retrains only | A fire destroys the router. Detection must survive network loss. Cloud inference per frame also destroys the cost argument |
| 3 | Camera only | Camera **plus** gas sensors, fused | Camera alone false-triggers on sunsets, steam, TVs, red objects. Camera also cannot see a gas leak with no flame — the original report's primary scenario |
| 4 | Raspberry Pi as edge device | **Laptop is the edge device.** Pi is optional stretch | Pi setup (OS flash, camera enable, ARM builds) costs 2 days minimum and can fail. Laptop has Python, USB, and a camera already |
| 5 | Train CNN/DNN from scratch | Fine-tune pretrained MobileNetV3-Small | No time to collect and label a fire dataset. Transfer learning reaches 90%+ in one session |
| 6 | Agent decides if there is a fire | Agent handles **response only**, never detection | LLMs are non-deterministic. Never place one in a safety-critical detection path |
| 7 | 1D CNN on sensor time-series | Threshold plus temporal smoothing | Not enough time to collect labelled sensor sequences. Listed as future work — honest, not a failure |
| 8 | GPS module for location | Hardcoded coordinates, GPS optional | NEO-6M gets no satellite lock indoors. The original report already noted this |

**Design principle carried throughout:** deterministic detection, agentic response.

---

## 2. What we are actually building

### Core deliverable

> A laptop-hosted edge node with a webcam and an Arduino sensor board detects fire or smoke locally, cross-checks it against gas and temperature readings, and within 10 seconds produces a verified alert that reaches a real phone and a logged simulated dispatch packet — **with the internet disconnected.**

### The demo moment

Mid-demo, disconnect the network. The buzzer still fires, the LED still turns red, the local decision still happens. Then reconnect and show the queued alert arriving on the phone. This single action is the strongest argument for the architecture.

### Explicitly out of scope

- Real emergency service integration
- Mobile app (Streamlit dashboard instead)
- Over-the-air model updates
- Multi-device fleet management
- Training a model from scratch
- Enclosure, PCB, or product design
- Raspberry Pi port

---

## 3. Immediate action list

### Do today, 18 August

- [ ] Submit hardware borrow request to the college lab
- [ ] Place online order for anything the lab cannot supply
- [ ] `git init firewatch`, push folder skeleton
- [ ] Write `config.yaml` in full before writing any code
- [ ] Start the D-Fire dataset download
- [ ] Create the Telegram bot (`@BotFather`) and note the token and chat ID

### The moment the MQ sensors arrive

- [ ] Connect VCC to 5V and GND to GND. **Nothing else.** Leave powered for 24–48h
- [ ] Sensors will get warm. This is correct
- [ ] After 24h, verify readings are stable within ±20 over 15 minutes

### Order list

**Tier 1 — required, must arrive by 23 August**

| Item | Qty | ~₹ | Notes |
|---|---|---|---|
| Arduino Uno R3 + USB-B cable | 1 | 500–700 | Clone acceptable. Verify cable included — square printer-style connector |
| MQ-2 gas/smoke **module** | 2 | 80 ea | Buy the module (blue PCB), not the bare sensor. Spare because these fail |
| MQ-135 air quality **module** | 1 | 100 | |
| DHT22 (AM2302) | 1 | 150 | DHT11 acceptable at ~₹60, less accurate |
| Breadboard 830pt | 1 | 80 | |
| Jumper wires M-M | 20 | 60 | |
| Jumper wires **M-F** | 20 | 60 | Required — sensor modules have male pins |
| Active buzzer 5V | 1 | 20 | **Active**, not passive |
| LEDs red + green 5mm | 2 ea | 10 | |
| Resistors 220Ω ×4, 10kΩ ×2 | — | 20 | Assortment pack is fine |

**Total ≈ ₹1,200–1,400**

**Tier 2 — optional**

| Item | ~₹ | Why |
|---|---|---|
| USB webcam 720p | 600–1000 | Laptop cam works, but an aimable USB cam is far better for demo |
| 5V 2A adapter + barrel jack | 150 | Insurance against USB power shortfall |
| NEO-6M GPS | 350 | Will not lock indoors |

**Suppliers:** Robu.in, Quartz Components (fastest in India). Amazon 2–3 days. College lab is fastest — request first, buy only the gaps.

---

## 4. Track A — Software

### 4.1 Environment

```
Python 3.10 or 3.11    # NOT 3.12 — some ML wheels lag behind
```

`requirements.txt`:

```
torch
torchvision
onnx
onnxruntime
opencv-python
numpy
pandas
pyserial
fastapi
uvicorn
langgraph
langchain-core
groq
boto3
paho-mqtt
streamlit
python-dotenv
pyyaml
requests
```

`.env` (gitignored):

```
GROQ_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=ap-south-1
```

### 4.2 Repository structure

```
firewatch/
├── config.yaml                 # every threshold lives here
├── .env                        # secrets, gitignored
├── .gitignore
├── requirements.txt
├── README.md
├── plan.md                     # this file
│
├── arduino/
│   └── sensor_node.ino
│
├── train/
│   ├── prepare_data.py         # dataset → train/val folders
│   ├── train_classifier.py     # run on Colab
│   └── export_onnx.py
│
├── models/
│   └── fire_mnv3.onnx
│
├── edge/
│   ├── camera.py               # frame grabber
│   ├── vision.py               # ONNX inference + TemporalVoter
│   ├── sensors.py              # threaded Arduino serial reader
│   ├── fusion.py               # the 4-state decision table
│   └── main.py                 # entry point — the loop
│
├── agent/
│   ├── graph.py                # LangGraph state machine
│   ├── tools.py                # overpass, telegram, dispatch_sim
│   └── server.py               # FastAPI POST /incident
│
├── cloud/
│   └── uploader.py             # S3, optional IoT Core
│
├── dashboard/
│   └── app.py                  # streamlit
│
└── eval/
    ├── adversarial/            # test videos
    ├── calibration/            # MQ baseline logs
    └── run_eval.py             # produces the metrics table
```

### 4.3 Tool choices

| Job | Tool | Why for a 12-day build |
|---|---|---|
| Training compute | Google Colab free T4 | Laptop takes hours, Colab takes ~15 min |
| Model | MobileNetV3-Small, 3-class classifier | Tiny, fast on CPU, transfer-learns in minutes. **Not YOLO** — bounding boxes are out of scope |
| Inference | ONNX Runtime | 3–5× faster than raw PyTorch on CPU. No GPU needed at demo time |
| Agent | LangGraph | State machine with fixed edges. Guarantees "notify owner" can never be skipped |
| LLM in agent | Groq (llama-3.1-8b-instant) via `groq` SDK | Message composition only. Never detection |
| Fire station lookup | OSM Overpass API | Free, no key, no signup |
| Alerts | Telegram Bot API | Free, instant, sends images. Twilio trial is restrictive |
| Cloud | AWS S3 (+ IoT Core if time) | Free tier, ~20 lines of boto3 |
| Dashboard | Streamlit | Demo-able UI in ~80 lines |

### 4.4 Software milestones

| ID | Milestone | Done when |
|---|---|---|
| S1 | Repo and config | Skeleton pushed, `config.yaml` complete, deps installed |
| S2 | Dataset ready | 3-class split, hard negatives added, class balance plotted |
| S3 | Model trained | Val accuracy + confusion matrix recorded, `fire_mnv3.onnx` exported |
| S4 | Edge loop v1 | `webcam → onnx → prints FIRE 0.94` on laptop |
| S5 | Temporal smoothing | N-of-M voting live, FPS measured |
| S6 | Adversarial eval | False-positive rate measured on 5 scenario videos |
| S7 | Agent | FastAPI + LangGraph + Overpass + Telegram all firing |
| S8 | Cloud | Incident snapshots and JSONL landing in S3 |
| S9 | Dashboard | Live feed, sensor gauges, incident log with replay |

---

## 5. Track B — Hardware

### 5.1 Bill of materials with roles

| Part | Qty | Role | Priority |
|---|---|---|---|
| Arduino Uno | 1 | Sensor node — reads analog pins, prints CSV over USB serial | Critical |
| USB-B cable | 1 | Power **and** data. The only link to the laptop | Critical |
| MQ-2 module | 1–2 | LPG, methane, propane, smoke. Primary hazard sensor | Critical |
| MQ-135 module | 1 | CO₂, ammonia, benzene. Second independent gas signal | Important |
| DHT22 | 1 | Temp + humidity. Corrects MQ drift, and rate-of-temperature-rise is a third fire signal | Important |
| Active buzzer 5V | 1 | Local alarm. Fires with no internet — this **is** the offline demo | Critical |
| LED red + green | 2 | Status: green monitoring, red hazard | Critical |
| Resistor 220Ω | 2 | LED current limiting | Critical |
| Resistor 10kΩ | 1 | DHT22 data line pull-up | Critical |
| Breadboard | 1 | | Critical |
| Jumper M-M and M-F | ~30 | M-F needed for sensor module pins | Critical |
| USB webcam | 1 | The eye. Laptop cam is fallback | Critical |
| 5V 2A adapter | 1 | If USB cannot supply both MQ heaters plus buzzer | Contingency |
| NEO-6M GPS | 1 | Coordinates in alert | Optional |

### 5.2 Pin map

**Arduino Uno**

| Component | Component pin | → Arduino pin | Notes |
|---|---|---|---|
| MQ-2 | VCC | 5V | heater ~150mA |
| | GND | GND | |
| | A0 | **A0** | analog out — **use A0, never D0** |
| MQ-135 | VCC | 5V | another ~150mA |
| | GND | GND | |
| | A0 | **A1** | |
| Active buzzer | + | **D8** | |
| | − | GND | |
| Red LED | anode (long leg) | **D9** via 220Ω | |
| | cathode (short leg) | GND | |
| Green LED | anode | **D10** via 220Ω | |
| | cathode | GND | |
| NEO-6M *(optional)* | VCC | 5V | onboard regulator |
| | GND | GND | |
| | TX | **D4** | GPS TX → Arduino RX |
| | RX | **D3** | SoftwareSerial |
| Arduino | USB-B | laptop USB | power + serial |
| Webcam | USB | laptop USB | |

DHT22 cut (cost + availability) — see logs.md for the open fusion-rule item this creates, to be resolved before Day 7.

### 5.3 Build order

Build incrementally and test after **every** step. Do not wire everything then power on.

| Step | Wire this | Test |
|---|---|---|
| H1 | 5V and GND rails from Arduino to breadboard | Multimeter or just proceed carefully |
| H2 | Green LED + 220Ω on D10 | Blink sketch — LED blinks |
| H3 | Red LED + 220Ω on D9 | Blink sketch on D9 |
| H4 | Active buzzer on D8 | Blink sketch on D8 — buzzer beeps |
| H5 | MQ-2 VCC/GND/A0 | `analogRead(A0)` printed to Serial Monitor — number appears, rises near a lighter |
| H6 | MQ-135 on A1 | Same test on A1 |
| H7 | DHT22 + 10kΩ pull-up on D2 | DHT library example — temp and humidity, not NaN |
| H8 | Full `sensor_node.ino` | CSV line every second in Serial Monitor |
| H9 | Python `sensors.py` reads the port | Same CSV appearing in Python |

If any step fails, stop and fix before continuing. Debugging one new component is easy. Debugging eight at once is not.

### 5.4 Power budget

| Load | Current |
|---|---|
| MQ-2 heater | ~150 mA |
| MQ-135 heater | ~150 mA |
| Arduino Uno | ~50 mA |
| Buzzer | ~30 mA |
| 2 LEDs | ~20 mA |
| **Total** | **~400 mA** |
| USB 2.0 supply | 500 mA |

Margin is thin. **Symptom of exceeding it: the Arduino resets or the Serial Monitor disconnects when the buzzer fires.** That is a power fault, not a code bug. Fix by connecting the 5V 2A adapter to the barrel jack.

### 5.5 MQ calibration procedure

Run on the day the sensors are burnt in. Takes about one hour. Do not guess these numbers — they are a strong point in the report.

1. With sensors burnt in and in a normal room, log raw ADC values for 15 minutes. Record mean and max → this is **baseline**.
2. Hold an **unlit** lighter with the gas released, ~20 cm from the MQ-2, for 5 seconds. Record the **peak**.
3. Compute:
   - `mq2_warn   = baseline + 0.30 × (peak − baseline)`
   - `mq2_danger = baseline + 0.60 × (peak − baseline)`
4. Write the actual values into `config.yaml`.
5. Record baseline, peak, and derived thresholds in the report.

**Safety:** small amount of butane, ventilated room, no ignition source nearby, ideally another person present. Do not test with open fire indoors. Use a controlled candle at a safe distance for the vision side, gas-only for the sensor side.

---

## 6. Data collection plan

### 6.1 Images or video?

**Train on images. Infer on frames. Decide over a window.**

A video is a sequence of still frames. The model never sees "a video" — it sees one frame at a time, exactly like a photo. So training data is images.

But video provides something images do not: **time**. A sunset glint may fool one frame; it will not persistently fool eight consecutive frames the way a real fire does. So the temporal dimension is used for **filtering**, not training.

**Temporal smoothing rule:**

```
alarm  ⟺  Σ(last M frames where p_fire > τ)  ≥  N
```

| Symbol | Meaning | Start value |
|---|---|---|
| `p_fire` | model's fire probability for one frame | — |
| `τ` | per-frame confidence threshold | 0.70 |
| `M` | rolling window size in frames | 8 (≈1s at 8 FPS) |
| `N` | votes required within the window | 5 |

At `N=1` you are trusting a single frame — maximum jitter. At `N=M=30` you need a full second of unanimity — very few false alarms but a second of latency, and one occluded frame breaks the chain. `N/M ≈ 0.6` is the usual sweet spot. Tune on the adversarial videos.

### 6.2 Training datasets (images)

| Dataset | Size | Use |
|---|---|---|
| **D-Fire** (Gaia-UFMG, GitHub) | ~21k labelled fire + smoke images | Primary source. Ignore bounding boxes, use folder labels |
| **FIRE Dataset** (Kaggle, `phylake1337`) | ~1k images | Quick baseline while D-Fire downloads |
| **BoWFire** | ~466 images with tricky negatives | Extra hard negatives |

### 6.3 Class design — 3 classes

```
0: neutral    ~8000    normal rooms, kitchens, outdoors
1: smoke      ~5000    smoke present, no visible flame
2: fire       ~5000    visible flame
```

Three classes rather than two because **smoke-before-flame is the early-warning promise** of the product.

### 6.4 Hard negatives — do not skip

Public datasets contain almost no tricky negatives. This is exactly why student fire detectors false-alarm constantly. Shoot ~300 photos personally, all labelled `neutral`:

| Scenario | Count |
|---|---|
| Sunset / sunrise through a window | 50 |
| Orange and red clothing, bags, cushions | 40 |
| Incandescent bulbs, fairy lights, candles | 50 |
| Steam from kettle, boiling pan, bathroom | 50 |
| TV or laptop screen showing fire footage | 30 |
| Car headlights, streetlights at night | 30 |
| Normal gas stove cooking | 50 |

**Decision on stove flame:** label it `fire`. Let the **fusion layer** resolve whether it is a hazard, not the vision model. Keep each component doing one job.

6 of 7 categories automated via DuckDuckGo image search, see scripts/fetch_hard_negatives.py. TV/laptop fire footage category requires manual screenshot collection.

### 6.5 Test videos

| Source | Purpose |
|---|---|
| Furg Fire Dataset | Real fire clips → measure detection latency |
| Own phone recordings | The adversarial set — the important one |

Record 5 adversarial clips, ~30s each: candle, sunset, steam, TV showing fire, person in red clothing. These produce the false-positive rate, which is the headline number of the evaluation.

### 6.6 Sensor data collection

| Session | Duration | Label | Purpose |
|---|---|---|---|
| Ambient baseline | 15 min | safe | Establish `baseline` |
| Ambient long | 2 h background | safe | Drift and noise characterisation |
| Lighter gas (unlit) | 5 × 5s bursts | hazard | Establish `peak` |
| Candle nearby | 3 × 60s | hazard | Combined vision + gas + temp event |
| Cooking / steam | 10 min | safe | The critical hard negative for fusion |

Log everything to `eval/calibration/` as CSV with timestamps. This becomes the calibration evidence section of the report.

---

## 7. Day-by-day schedule

Two checkpoints: **Day 3** and **Day 11**. If Day 3 slips, immediately cut MQ-135 and GPS.

| Day | Date | Track | Deliverable at end of day |
|---|---|---|---|
| 0 | Aug 18 | Both | Repo pushed, `config.yaml` written, dataset downloading, **hardware requested/ordered**, Telegram bot created |
| 1 | Aug 19 | SW | 3-class dataset split, ~300 hard negatives shot and labelled, class balance plotted |
| 2 | Aug 20 | SW | MobileNetV3 fine-tuned on Colab, confusion matrix recorded, exported to `fire_mnv3.onnx` |
| 3 | Aug 21 | SW | **Checkpoint.** `webcam → onnx → prints FIRE 0.94` works on laptop |
| 4 | Aug 22 | SW | TemporalVoter integrated, FPS measured, 5 adversarial videos recorded |
| 5 | Aug 23 | SW | False-positive rate documented per scenario. **Headline metric of the report** |
| 6 | Aug 24 | HW | Arduino sketch flashed, H1–H9 build steps complete, CSV arriving in Python. **MQ calibration run** |
| 7 | Aug 25 | HW+SW | Fusion logic working end to end. Buzzer and LEDs driven from laptop |
| 8 | Aug 26 | SW | FastAPI `/incident` live, LangGraph skeleton, Overpass returns nearest fire station |
| 9 | Aug 27 | SW | Telegram alert with snapshot lands on phone, 30s cancel window, `dispatch_sim.py` writes packet |
| 10 | Aug 28 | SW | S3 uploading incident snapshots and JSONL. IoT Core telemetry if ahead of schedule |
| 11 | Aug 29 | Both | **Checkpoint.** Streamlit dashboard. 20 hazard + 20 non-hazard trials logged. Offline test passes |
| 12 | Aug 30 | Docs | README, architecture diagram, metrics table, 3-min demo video. **Submit** |

---

## 8. Claude Code prompts per phase

Paste these into Claude Code in VS Code. Each assumes `plan.md` and `config.yaml` are in the repo — reference them so Claude Code has the context.

### Day 0 — scaffold

```
Read plan.md section 4.2. Create the exact folder structure described,
with empty __init__.py files where needed, a .gitignore covering .env,
models/, data/, __pycache__, and *.onnx, and a requirements.txt from
section 4.1. Then create config.yaml with the schema implied by
sections 5.5 and 6.1 — vision thresholds, sensor thresholds and serial
port, fusion cancel window, and hardcoded location. Use placeholder
values with a comment marking which ones get calibrated on Day 6.
```

### Day 1 — data prep

```
Write train/prepare_data.py. It takes a raw D-Fire download directory
and produces train/ and val/ folders with three class subdirectories:
neutral, smoke, fire. Use an 85/15 stratified split. Also accept an
optional --extra-negatives directory whose images all go into the
neutral class. Print a class balance table at the end and save a bar
chart to eval/class_balance.png. Handle corrupt or unreadable images
by skipping and logging them, not crashing.
```

### Day 2 — training

```
Write train/train_classifier.py for Google Colab. Fine-tune a
torchvision MobileNetV3-Small pretrained on ImageNet for 3-class
classification. Freeze the feature extractor for the first 2 epochs,
then unfreeze and train the whole network at a lower LR. Use
AdamW, cosine LR schedule, and standard augmentation (random flip,
color jitter, random resized crop to 224). Log per-epoch train/val
loss and accuracy. At the end, save the best checkpoint by val
accuracy, print a confusion matrix, and save it to
eval/confusion_matrix.png. Set all seeds for reproducibility.

Then write train/export_onnx.py that loads the checkpoint and exports
to models/fire_mnv3.onnx with dynamic batch axis, and verifies the
ONNX output matches the PyTorch output within 1e-4.
```

### Day 3 — edge loop v1

```
Read plan.md sections 4.2 and 6.1. Write edge/camera.py and
edge/vision.py.

camera.py: a Camera class wrapping cv2.VideoCapture with read(),
encode_jpeg(frame), and release(). Handle the camera failing to open
with a clear error.

vision.py: a VisionModel class that loads models/fire_mnv3.onnx via
onnxruntime, preprocesses a BGR frame to the 224x224 normalized tensor
the model expects, runs inference, and returns
{'fire': bool, 'smoke': bool, 'p_fire': float, 'p_smoke': float}.
Read all thresholds from config.yaml — no hardcoded numbers.

Then a minimal edge/main.py that loops camera -> vision -> print.
No sensors yet.
```

### Day 4 — temporal smoothing

```
Add a TemporalVoter class to edge/vision.py implementing the N-of-M
rule from plan.md section 6.1, using collections.deque with maxlen.
Wire it into VisionModel so predict() returns both the raw per-frame
probability and the smoothed boolean decision. Read window,
votes_needed, and frame_threshold from config.yaml.

Also add an FPS counter to main.py that prints a rolling average
every 30 frames.
```

### Day 5 — adversarial eval

```
Write eval/run_eval.py. It takes a directory of labelled test videos
(filename prefix indicates ground truth: fire_*.mp4, neutral_*.mp4)
and runs the full vision pipeline over each. For each video report:
whether an alarm fired, time-to-first-alarm in seconds, and the
fraction of frames above threshold. Aggregate into a table showing
per-scenario false positive rate and overall precision/recall.
Save results to eval/results.csv and print a formatted table.
```

### Day 6 — Arduino and serial

```
Read plan.md sections 5.2 and 5.3. Write arduino/sensor_node.ino:
read MQ-2 on A0, MQ-135 on A1, DHT22 on D2, print a CSV line
"mq2,mq135,temp,humidity" every second at 9600 baud. Handle DHT
returning NaN by printing -1. Accept a single character over serial:
'A' turns on the buzzer (D8) and red LED (D9) and turns off the green
LED (D10), 'S' does the reverse.

Then write edge/sensors.py: a SensorReader class that opens the
serial port from config.yaml on a daemon thread, parses CSV lines,
maintains a 10-sample deque of temperature to compute temp_rate
(degrees change over the window), exposes latest() returning a dict,
and set_alarm(bool) writing the command byte. Malformed lines must be
skipped without crashing the thread.
```

### Day 6b — calibration helper

```
Write eval/calibrate_mq.py. It connects to the Arduino, logs raw
MQ-2 and MQ-135 values with timestamps to a CSV in
eval/calibration/, and runs in two modes:
--baseline (log for N minutes, then print mean, std, min, max)
--peak (log continuously and print a live rolling max, for the
lighter test)
At the end of a baseline run, print the suggested warn and danger
thresholds using the formula in plan.md section 5.5.
```

### Day 7 — fusion

```
Read plan.md section 2 and the fusion table. Write edge/fusion.py
with a Level enum (SAFE, WATCH, WARNING, CRITICAL) and a fuse()
function taking vision_fire, vision_smoke, gas_high, temp_spiking
and returning (Level, reason_string).

Rules in priority order:
1. (fire or smoke) AND gas_high -> CRITICAL, "visual hazard confirmed by gas sensor"
2. fire AND temp_spiking -> CRITICAL, "flame detected with rapid temperature rise"
3. gas_high AND NOT (fire or smoke) -> WARNING, "gas concentration high, no visible flame"
4. fire -> WARNING, "visual flame, unconfirmed by sensors"
5. smoke -> WATCH, "possible smoke, monitoring"
6. else -> SAFE, "nominal"

Then update edge/main.py to the full loop: camera -> vision +
sensors -> fusion -> LOCAL alarm first (sensors.set_alarm), THEN
attempt the network POST to the agent inside a try/except with a
2 second timeout. A network failure must never suppress the local
alarm. Add a 60 second cooldown so one fire does not spam the agent.
```

### Day 8 — agent part 1

```
Read plan.md section 2. Write agent/server.py: a FastAPI app with
POST /incident accepting the payload main.py sends (level, reason,
vision dict, sensors dict, base64 snapshot). It saves the snapshot to
disk and invokes the LangGraph app.

Write agent/tools.py with find_nearest_fire_station(lat, lon,
radius_m) querying the OSM Overpass API for amenity=fire_station and
returning the closest by haversine distance, with a graceful fallback
dict when nothing is found or the request times out.

Write agent/graph.py with the LangGraph StateGraph skeleton: nodes
verify, locate, compose, notify_owner, wait, escalate, simulate.
Conditional edge after verify (escalate only if level is CRITICAL)
and after wait (END if cancelled). Stub the node bodies for now.
```

### Day 9 — agent part 2

```
Fill in the remaining nodes in agent/graph.py.

compose: call Groq via the groq SDK, using the llama-3.1-8b-instant
model, to turn the structured incident state into a 2-sentence
human-readable alert. Include a
deterministic template fallback if the API call fails — the alert
must go out even if the LLM does not respond.

notify_owner: send a Telegram message with the snapshot image and
the composed text, plus the line "Reply CANCEL within 30 seconds to
stop escalation."

wait: poll Telegram getUpdates for 30 seconds looking for a message
containing CANCEL from the configured chat ID. Return early on match.

escalate: send to all configured emergency contacts.

simulate: build the full dispatch packet described in plan.md and
append it as one JSON line to dispatch_log.jsonl. It must include
"SIMULATED": true and a note that no emergency service was contacted.
Print a clear console banner. Never make a real call.
```

### Day 8/9 revised scope (decided 2026-08-31, not yet built)

The Day 8 and Day 9 prompts above are the original spec and are left
unedited. The following decisions, made 2026-08-31, extend that scope
for when Phase 8/9 is actually built. This section is planning/
documentation only — none of it is implemented yet.

**Notification channels: now two, not one.**
1. Telegram — unchanged from the Day 9 prompt above (alert message,
   30s cancel window, then simulated dispatch on no response/cancel).
2. **NEW: Twilio call and/or SMS to the developer's own phone number.**
   Not any emergency service — info.md §2.1's absolute rule only
   prohibits contacting real emergency services; alerting the
   developer's own number was always implicitly fine and is now
   explicit. Same 30s confirm/cancel window pattern as Telegram.
   Requires Twilio credentials in `.env`: `TWILIO_ACCOUNT_SID`,
   `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `TWILIO_TO_NUMBER` (match
   `.env.example` naming conventions when added — same no-secrets-in-
   code rule, info.md §2.5, as every other credential).
   **Cost note: Twilio is a real-cost service**, unlike Groq/Telegram's
   free tiers (see §4.3 tool-choices table above, which previously
   noted "Twilio trial is restrictive" as a reason to avoid it — that
   reasoning is superseded by this decision, not deleted). Flag this
   clearly wherever the project's cost/budget is documented, so it is
   never presented as fully free.

**GPS / location capability — scope clarified.**
Per the existing "hardcoded coordinates, GPS optional" decision
(§1, unchanged), the concrete Overpass deliverable is: query and
**display** the nearest real fire station's contact info for the
hardcoded/simulated coordinate (the Day 8 prompt's
`find_nearest_fire_station` above, previously listed in §9's cut list
and now being actively planned rather than cut). This is purely
informational display. **The system never calls or contacts that
number.** Read-only lookup/display only — never an automated contact
action — to avoid any future ambiguity against info.md §2.1.

**Refinement (2026-09-01): fire station name + number goes IN the
alert content on both channels, not just a separate display field.**
The Overpass-looked-up nearest fire station's name and phone number
must appear inside the actual notification content the developer
receives, not only in some other display surface:
- **Telegram:** the fire station name and number are included as
  plain text in the alert message body itself, alongside the
  compose-node's generated alert text.
- **Twilio call:** the fire station name and number are included in
  the TTS (text-to-speech) content the call reads aloud, using the
  same compose-node-generated text as Telegram, or — per info.md §3.2
  and consistent with the LLM-failure fallback already planned for
  Telegram — a clear deterministic template fallback if the LLM call
  fails. Delivery mechanism (spoken vs. written) does not change what
  content is required.

**Purpose, stated explicitly so it is never ambiguous later:** this
is informational only, so the **developer** (the person receiving the
alert) can call the real fire station themselves, immediately,
without needing to look anything up. **The system NEVER dials,
forwards, or connects to the fire station's number automatically, on
the Twilio call, on Telegram, or on any other channel, under any
condition.** This applies identically to voice calls as it does to
SMS/Telegram — the fact that a call can *read the number aloud* is not
license to also *dial* it. Including the number as content read to or
shown to the developer is categorically different from the system
placing a call or sending a message to that number itself, and must
never be conflated in a future implementation. This restates and
narrows — does not relax — the "system never calls or contacts that
number" rule two paragraphs above; both statements describe the same
boundary and must be read together, not against each other.

**Alert feedback logging — new scope, data collection only.**
Every alert (Telegram and/or Twilio) that reaches the 30s window
should have its outcome captured — true positive (real hazard) vs
false alarm, based on the developer's response — and logged as
structured data (e.g. a new `eval/alert_feedback.csv` or similar,
exact format to be decided when this phase is actually built).
**This is explicitly scoped as data collection only.** Per info.md
§2.4 (no fabricated metrics/results), do not build, imply, or claim
any reinforcement learning or automated threshold adjustment from
this data unless and until it is actually built and evaluated later —
current timeline (30 August deadline) makes a real, defensible RL
implementation unlikely to fit, and a fabricated or trivial "RL" claim
would violate the project's own no-fabrication rule. If time allows
later, RL becomes a legitimate future-work item building on this
logged data — explicitly not committed to as of this update.

**Alert feedback schema — decided ahead of implementation (2026-08-31),
so an RL-shaped log doesn't require re-migration later.** RL itself
remains fully deferred and not committed per the paragraph above; this
only decides the *shape* of the data being collected once Phase 8b is
actually built, following an RL-style state/action/reward/metadata
structure:

- **STATE** — the full decision context at the moment of the alert:
  fusion level at trigger (WARNING/CRITICAL), `p_fire`, MQ-2 raw value,
  MQ-135 raw value, `gas_high` boolean, temporal voter vote count.
- **ACTION** — the threshold configuration in effect at that moment:
  `mq2_warn`, `mq2_danger`, `mq135_warn`, `mq135_danger`,
  `fire_decision_threshold`, `votes_needed` — the tunable parameters a
  future RL policy would adjust.
- **OUTCOME/REWARD** — the developer's response during the 30s cancel
  window, translated to a reward signal: `+1` for confirmed real
  hazard, `-1` for false alarm (developer cancels). **Timeout-with-
  no-response is an explicit open decision, deliberately not made
  now** — must be decided when Phase 8b is actually implemented, not
  left ambiguous in the shipped code.
- **METADATA** — timestamp and a trial/event ID, for tracing back to
  `logs.md`/report narrative.

If this decision is ever acted on, the bounded scope is a contextual
bandit or tabular Q-learning over these threshold knobs — **not deep
RL** — given realistic trial counts achievable by the 30 August
deadline. If trial volume ends up insufficient for any RL formulation,
this logged data still stands alone as valid, honest labeled feedback
data for the report, independent of whether RL is ever built.

### Day 10 — cloud

```
Write cloud/uploader.py with log_incident(payload, jpeg_bytes) that
uploads to S3 under the key pattern
device_01/YYYY/MM/DD/HHMMSS.jpg and .json, and returns the key.
Use boto3 with credentials from .env. Wrap in try/except so an S3
failure logs a warning and continues — cloud must never block the
local pipeline. Add a local fallback that writes to
data/incidents/ when S3 is unreachable.

Wire this into agent/graph.py as a side effect in the simulate node.
```

### Day 11 — evaluation trial plan (reduced set, 2026-09-05)

**Deliberate reduction from the 4.4 minimum, not an oversight.** info.md
4.4 specifies ≥20 hazard + ≥20 non-hazard trials. Given real time
constraints ahead of the 7 September 2026 deadline, the developer chose
to scale down to a smaller, still-balanced **12-trial set (6 hazard, 6
non-hazard)** that deliberately covers every fusion rule and known
limitation on record, rather than run 40+ trials that would mostly
repeat the same few code paths. This reduction and its reasoning must
be carried into the final report wherever trial results are written up
— it is not to be presented as if 20+20 were run.

Each trial is run with `eval/run_trial.py` (built Phase 11, idle since
2026-09-03) and logged to `eval/results.csv`. A trial below is marked
complete only once the developer explicitly confirms it was run; each
row is then cross-checked against `eval/results.csv` (trial_id,
timestamp, actual_outcome, latency) and marked PASS/FAIL against the
expected outcome listed here.

**Gas-sensor warm-up note (2026-09-05):** the MQ sensors' hardware was
disconnected/unused for ~2 days; the developer has re-armed the full
5-minute (300s) `gas_warmup_seconds` gate from a genuine fresh
power-cycle (not a continuation of prior warm-up progress). Before
running any hazard trial that depends on a gas trigger (3, 4, 5, 6),
confirm the console shows `GATED` / `gas_high` suppressed, and let the
gate clear naturally — do not bypass or shorten it.

#### Hazard trials (expect escalation)

| # | Status | Trial | Expected outcome |
|---|---|---|---|
| 1 | PASS | Fire video (phone) alone, no gas trigger | WARNING |
| 2 | PASS (see note) | Fire video (phone) + gas-stove trigger near MQ-2 | CRITICAL |
| 3 | PASS | Gas-stove trigger alone, neutral camera view (no fire-like visual) | WARNING ("gas concentration high, no visible flame") |
| 4 | PASS (see note) | Alcohol/sanitizer trigger near MQ-135 alone, neutral camera view | WARNING (gas high, no flame) |
| 5 | PASS | Fire video (phone) + alcohol/sanitizer trigger near MQ-135 | CRITICAL |
| 6 | PASS | Gas-stove trigger + camera pointed AWAY from any fire-like footage | WARNING, not CRITICAL — confirms gas-alone never falsely escalates without vision agreement |

#### Non-hazard trials (expect SAFE, or a correctly bounded known limitation)

| # | Status | Trial | Expected outcome |
|---|---|---|---|
| 7 | PASS | Empty room, camera on, nothing happening | SAFE |
| 8 | PASS (see note) | Developer sitting normally in frame, talking/moving naturally | SAFE |
| 9 | PASS | Red clothing in frame | 0 alarms (SAFE) — per the existing adversarial-scenario bar (info.md 4.2) |
| 10 | PASS | TV/laptop-fire footage, no gas trigger | WARNING — the already-documented, bounded known limitation from Phase 5; must NOT reach CRITICAL, confirming the fusion cap (rule 4) still holds on the now-promoted v4 model |
| 11 | PASS | Bright light exposing the textured wall/background (the exact scenario that triggered the smoke-recall investigation and v4 retrain) | SAFE — live confirmation that the v4 fix holds under real conditions |
| 12 | FAIL — new finding | Normal room lighting changes (lamp on/off, walking past a window, ambient light shifts) | SAFE throughout |

**Trial 8 note (2026-09-05):** first clean attempt (`person_in_frame_v2`,
23:51:29) logged WATCH (FAIL); immediate rerun (23:53:27) logged SAFE
(PASS) with no deliberate change in conditions between runs. Marked
PASS on the second result but flagged here as borderline/non-repeatable
rather than a clean pass — worth re-running once more or noting in the
final report as an observed smoke-vote borderline case, not silently
dropped. A separate earlier attempt (`person_in_frame`, 23:42:54, WARNING)
was invalidated — a flashlight was accidentally held close to the camera,
not a genuine trial condition — and is excluded from this count.

**Trial 9 note (2026-09-05):** first attempt (`red_clothing`, 23:56:22)
logged WARNING (FAIL) — invalidated, the cloth was held very close to
the camera, a different visual input than the established "person
wearing red clothing at normal distance" adversarial scenario (plan.md
§6, info.md 4.2). Clean rerun at normal framing distance (`red_clothing`,
23:58:03) logged SAFE (PASS), consistent with every prior model version
(v1-v4) on this exact scenario. The 23:56:22 row stays in
`eval/results.csv` as an honest record but is excluded from this trial's
result.

Trial 11 re-verifies the v4 smoke-recall fix and trial 10 re-verifies
the TV-fire known limitation, both under the newly-promoted production
model — these two are deliberately retained from the wider set as the
highest-value checks, not arbitrary picks.

**Trial 11 note (2026-09-06):** first attempt (`bright_wall_v4_recheck`,
00:03:52) logged WARNING at 11.4s latency (FAIL) — reached WARNING fast,
suggesting an early transient rather than a sustained smoke lock.
Immediate rerun (00:06:35) held SAFE throughout (PASS). Cause of the
first attempt's brief WARNING identified by the developer: the camera
lens was still autofocus-hunting (focusing/unfocusing) at trial start,
producing transient blur on the textured wall — a camera-startup
artifact, not a model regression. The clean second run (lens settled)
is the representative result: SAFE throughout, confirming the v4
smoke-recall fix holds under real conditions.

**Trial 2 note (2026-09-06):** first attempt (00:54:04) correctly logged
CRITICAL (fusion/vision/gas logic all correct) but the physical buzzer
did not audibly sound — root-caused by the developer as a loose
hardware wiring connection on the buzzer circuit (D8), not a code or
fusion bug; the fusion `*** LOCAL ALARM ON ***` transition and serial
write path were never in question. Reseated the connection and
reran (01:00:15): CRITICAL logged again, buzzer audibly sounded this
time. Marked PASS on the working rerun, but this is a genuine hardware-
reliability finding worth a line in the final report's limitations/
cost section — a loose D8 connection can silently defeat the local
alarm even when detection and fusion are functioning correctly.

**Trial 4 note (2026-09-06):** first attempt (01:06:48) escalated all
the way to CRITICAL at 110.7s (FAIL) despite a neutral camera view with
no fire-like content — developer identified a camera/webcam glitch
(freeze, autofocus hunt, or exposure spike) as the cause, producing a
spurious high `p_fire` vote unrelated to what was actually in frame,
the same pattern seen in trial 11's autofocus artifact. Clean rerun
(01:08:29) correctly held at WARNING (gas high, no visible flame) as
expected — PASS. **This is the second observed instance of a camera
artifact spuriously inflating p_fire** (trial 11, trial 4) — worth
flagging as a recurring nuisance/limitation in the final report: the
webcam's autofocus/exposure transients can occasionally masquerade as
visual fire evidence for a few frames, which is exactly the failure
mode the temporal voter (5-of-8) is designed to filter, but a
sufficiently sustained glitch can still clear the vote threshold as
seen here. Not fixed on the spot; recommend letting the camera settle
(no active autofocus hunting) for a few seconds before starting a trial
as a practical mitigation, and noting the underlying model sensitivity
as a known limitation.

**Trial 12 — NEW ADVERSARIAL FINDING, not an invalid trial (2026-09-06):**
`lighting_changes` (00:25:36) genuinely FAILED — logged WARNING at
86.5s. Console trace shows `p_fire` climbing steadily 0.29 -> 0.96 over
roughly 4 seconds of complete darkness (no light at all), reaching 5/8
temporal votes and firing a real local alarm ("visual flame, unconfirmed
by sensors"), with `gas_high=False` throughout — this is a genuine
vision-side false positive in near-black frames, not gas involvement,
not sensor noise misread as a bug in the harness. It self-de-escalated
back to SAFE once votes decayed after the room was no longer fully dark.
Likely cause (not yet confirmed): the training data probably has no or
few true near-black/heavily underexposed negative frames, so a webcam's
auto-exposure noise/grain in total darkness may resemble fire-like
texture to the model. **This is a new, previously undocumented
limitation** — distinct from the bright-wall/textured-background issue
that drove the v4 retrain (opposite lighting extreme, likely different
root cause). Not fixed on the spot (no retrain/threshold tuning
performed) — recorded here as an open item for the final report's
limitations section. Partial pass note: SAFE held correctly through
ordinary lighting variation (lamp on/off with the room otherwise lit,
walking past a window) — the failure is specific to sustained total
darkness, not general lighting sensitivity.

### Day 11 — dashboard

```
Write dashboard/app.py in Streamlit with three sections:
1. Live status: current fusion level as a coloured banner, latest
   camera frame, and gauges for mq2, mq135, temperature, humidity.
2. Incident log: table read from dispatch_log.jsonl, most recent
   first, with columns timestamp, level, reason, nearest station.
3. Incident replay: select a past incident and display the exact
   snapshot frame that triggered it alongside the sensor readings at
   that moment.
Read live state from a shared JSON file that edge/main.py writes
each loop — do not import the edge modules directly.
```

### Day 12 — docs

```
Write README.md covering: what the system does, the architecture
(reference plan.md section 2), quickstart install and run
instructions, the pin map table from plan.md section 5.2, the
measured evaluation results from eval/results.csv, known limitations,
and a clearly worded note that emergency dispatch is simulated and
no emergency service is ever contacted. Keep it under 200 lines.
```

---

## 9. Cut list

If behind schedule, cut in this exact order:

1. Streamlit dashboard → replace with console output
2. AWS IoT Core telemetry → keep S3 only
3. Incident replay feature
4. GPS module → hardcoded coordinates only
5. MQ-135 → MQ-2 alone is sufficient for fusion
6. LLM message composition → deterministic template
7. Overpass lookup → hardcoded nearest station

**Never cut, under any circumstances:**

- Local on-device detection
- Buzzer and LED local alarm
- The offline (cable-unplugged) demo
- The simulated-dispatch safety framing

---

## 10. Phase 13 — ESP32-CAM migration (two-board architecture, IN PROGRESS)

**Status: hardware IN PROGRESS, firmware NOT STARTED on the sensor
board.** Camera board is flashed and confirmed (§10.10a); sensor board
wiring is confirmed working but burn-in/calibration is not complete
and no firmware has been written for it yet. This section finalizes
the architecture decided with the developer and a faculty-suggested
advancement beyond the original 12-day scope; it does not change the
status of the existing prototype (see context.md §3 — that system is
FUNCTIONALLY COMPLETE, submitted, and fully unaffected by this
future-phase plan).

**ARCHITECTURE, corrected 2026-09-16 (see §10.0a — supersedes every
single-board description below and elsewhere in this section):**
FireWatch's Phase 13 hardware is TWO separate ESP32 boards, not one.
Wherever the rest of this section says "the ESP32" or "the ESP32-CAM"
in the context of sensors, buzzer, or gas-only fallback, read that as
the **plain ESP32 DevKit** described in §10.0a — the ESP32-CAM itself
is camera/vision only and carries no sensor wiring.

**Hardware in hand:** AI-Thinker ESP32-CAM (OV2640 camera) + its MB
shield programmer, plus a plain ESP32 DevKit V1 (30-pin, added
2026-09-16) carrying MQ-2, MQ-135, and the buzzer — reusing the
existing MQ-2, MQ-135, buzzer, breadboard, and jumpers from the
Arduino build.

**The Arduino Uno and `arduino/sensor_node.ino` are fully retired by
this migration.** Between the two ESP32 boards, the Arduino's role
(camera, gas sensors, buzzer, and now networking) is fully replaced —
rather than supplemented — by two boards instead of one.

### 10.0a Two-board split and sensor pin map (added 2026-09-16)

**Board 1 — ESP32-CAM (AI-Thinker, on its MB shield):** camera/vision
only. No sensor wiring. Confirmed flashed and working (§10.10a).

**Board 2 — plain ESP32 DevKit V1 (30-pin):** MQ-2, MQ-135, buzzer.
Chosen specifically because this board exposes genuine ADC1 pins —
the ESP32-CAM's only free header pins for this purpose (IO12-15) are
ADC2, tied to the SD/flash bus, and unreliable during active WiFi
transmission. Putting sensors on a board with real ADC1 access
eliminates that ADC1-vs-ADC2/WiFi conflict entirely, rather than
managing it as an accepted risk.

**Confirmed pin assignment (plain ESP32 DevKit):**

| Component | Signal | → ESP32 DevKit pin | Notes |
|---|---|---|---|
| MQ-2 | A0 (via divider) | **GPIO34** | ADC1, input-only |
| MQ-135 | A0 (via divider) | **GPIO35** | ADC1, input-only |
| Buzzer | + | **GPIO33** | digital out |
| MQ-2 / MQ-135 | D0 | *unwired* | analog-only design, per Appendix A.2 — never use D0 |

- **UPDATED 2026-09-17 (first pass) — divider changed, breadboard
  topology replaces direct jumpers.** Both MQ-2 and MQ-135 initially
  moved to a **10kΩ/15kΩ (2:3) voltage divider** (output = input ×
  0.6) before reaching the GPIO — the sensor's A0 can swing toward 5V,
  and these GPIOs are 3.3V-max. At 5V × 0.6 = 3.0V, this was confirmed
  still under the 3.3V limit, but with **less safety margin** than the
  prior 270Ω/270Ω (1:1, ×0.5) divider. Current draw is correspondingly
  much lower (kΩ-range divider vs. the old Ω-range one) — a different
  design philosophy (low current draw vs. maximum safety margin),
  both individually valid, but a real, distinct change from what was
  previously reasoned through and logged for the 1:1 divider.
- **SUPERSEDED same night — divider changed again to 22kΩ(top)/10kΩ
  (bottom), ×0.3125 scaling, max ~1.56V for a 5V sensor output.** This
  second rewire was not logged at the time it was made; it is being
  recorded now after the fact, alongside the ADC-floor investigation
  below. **This ratio is suspected too aggressive** — see "MQ sensor
  near-zero WARMUP readings — ADC floor + divider margin investigation
  (2026-09-17)" further down and logs.md for the full analysis. Do not
  treat 22k/10k as validated; it is flagged for likely reversion back
  toward the 10k/15k (or similar, ×0.5–0.6) range pending confirmation
  against the sensor's actual measured clean-air output voltage.
- **Reason for the original change (270Ω/270Ω → 10kΩ/15kΩ):** the
  original direct-jumper wiring was unreliable under physical
  movement — Dupont jumper connections loosening enough to cause large
  (~100+ count) reading jumps when the board was bumped, even when
  visibly seated (see logs.md "UNRESOLVED: board-movement causes
  reading jumps"). Soldering was not available as a fix (parts need to
  stay reusable), so the sensors were moved to a **breadboard-based**
  wiring topology instead of staying on direct point-to-point jumpers,
  to get more mechanically stable connections without soldering.
- **New topology (breadboard-based, identical pattern for both
  sensors):** ESP32 GND → breadboard negative rail; ESP32 5V/Vin →
  breadboard positive rail; sensor VCC → positive rail; sensor GND →
  negative rail; sensor A0 → breadboard row A; top resistor row A →
  row B; bottom resistor row B → negative rail; row B (the divider
  junction) → the sensor's GPIO (34 for MQ-2, 35 for MQ-135). Each
  sensor's divider occupies its own separate breadboard rows. (Row
  labels unchanged across both the 10k/15k and 22k/10k rewires — only
  the resistor values changed.)
- Both dividers' ground legs return to a shared GND rail with the
  ESP32 DevKit's own GND.
- This is a **12-bit ADC** (0-4095), unlike the Arduino Uno's 10-bit
  ADC (0-1023) that Appendix A.2 and §5.5's calibration formula were
  originally written against. The formula's *shape* (a proportion of
  peak-baseline swing) is scale-invariant, but **whether to reuse it
  unchanged against fresh 12-bit baseline/peak numbers, or re-derive
  it, is an open decision — not yet made.** See logs.md "Phase 13 —
  architecture change: two-board split" for the flagged discussion.
- **VOID as of 2026-09-17 — captured under the old divider, not
  reusable.** "Working hardware confirmed via Serial Monitor
  (2026-09-16): stable, correlated ~100-190 range readings on both
  sensors during warm-up" and the movement-jump finding below (both
  originally logged against the **270Ω/270Ω (1:1, ×0.5)** divider) do
  **not** translate to the new **10kΩ/15kΩ (2:3, ×0.6)** divider's
  output scale for the same real-world gas concentration — a different
  divider ratio changes the ADC codes produced for a given sensor
  output voltage, so none of these numbers may be reused, rescaled, or
  treated as informal baseline data once the rewire is physically
  done. See logs.md 2026-09-17 entry for the full statement.
- **New finding, real and repeatable (numbers void, see above):** both
  sensors' readings jumped (~105→~170-185, under the OLD divider) when
  the board was physically moved or disturbed by airflow — not gas
  presence (both sensors moved together, ruling out a wiring fault).
  This is a known MQ-sensor airflow-sensitivity behavior and a genuine
  false-positive risk for the threshold formula above if the
  deployment site has ambient air movement. **Mitigation not yet fully
  resolved** — a `SUSPECT_JUMP` firmware-side flagging stopgap exists
  (inert until tuned, see logs.md), but the underlying physical fix is
  what changed here (breadboard rewire, above); whether a
  sustained-duration gas check (N-of-M, mirroring `edge/vision.py`'s
  TemporalVoter) or a wider baseline margin is also needed remains
  undecided, to be revisited with the actual `edge/`/`fusion.py` code
  in view, not blind.

### 10.1 Inference location — decided: cloud, not on-device

Research confirmed MobileNetV3-Small, even INT8-quantized, exceeds the
ESP32's realistic memory/compute budget for real-time inference.
Genuine on-device TinyML would require an entirely new, smaller
architecture trained from scratch, with an expected accuracy drop
below the proven v4 model (fire recall 0.9575, smoke recall 0.8511).

**Decision:** run the existing v4 ONNX model **unmodified** in AWS
Lambda (cloud inference) — full accuracy preserved, zero retraining
risk. This mirrors real production patterns: Ring- and Wyze-style
cameras relay to cloud/hub compute rather than running detection on
the camera's own tiny chip. MobileNet-class models are designed for
phone/edge-device-class hardware, not bare microcontrollers.

### 10.2 Cost — real estimate against AWS Lambda's free tier

AWS Lambda's permanent free tier: 1M requests/month + 400,000
GB-seconds/month.

At 640×480 @ 5fps, for an estimated **15 hours of total trial/demo
usage** (not continuous 24/7):

- ~270,000 requests → 27% of the free tier
- ~81,000 GB-seconds → 20% of the free tier

**Genuinely $0 for the realistic usage pattern**, confirmed against
published AWS pricing.

### 10.3 Camera specs — OV2640 assumption, SUPERSEDED by measurement (2026-09-16)

Original assumption: 25–30fps at VGA (640×480) with on-chip JPEG
compression, ~12–28KB per frame. Practical streaming target: 640×480 @
5fps — a stable, well-documented configuration, not the camera's
theoretical peak. **This assumed OV2640 hardware-JPEG encoding.**

**Invalidated 2026-09-16:** the actual on-board sensor is a GalaxyCore
GC2145 clone, not a genuine OV2640 (see §10.10/logs.md Phase 13a JPEG
root-cause finding) — it has no on-chip JPEG encoder, so every frame
must be software-encoded on the ESP32 itself via `frame2jpg()` before
reaching WiFi, a real CPU cost the OV2640-based 5fps figure never
budgeted for.

**Measured live** (`arduino/cam_node/cam_node.ino`, developer-run):
`frame2jpg()` alone takes ~480–500ms/frame at VGA (~2fps) — well under
the original 5fps target, confirmed by live testing, not assumed.

**Decision: capture resolution changed to QVGA (320×240), not VGA.**
At QVGA, `frame2jpg()` takes ~97–109ms/frame (~10fps), clearing the
original 5fps target. This is not an arbitrary substitution — plan.md
never actually required 5fps for its own sake; the real constraint is
info.md §4.3's alert-latency budget (phone alert ≤30s block/≤15s
target — the ≤10s buzzer bar is gas-path-only, unaffected by camera
fps per §2.2's scope), and plan.md §6.1's TemporalVoter (5-of-8 votes)
fills its window in ~4s even at 2fps, let alone ~10fps at QVGA — so
the 5fps figure was a streaming/UX assumption inherited from the
OV2640 plan, not itself load-bearing. QVGA also costs nothing at
inference: `edge/vision.py`'s `_preprocess()` resizes every frame to
224×224 regardless of source resolution.

QVGA capture also exposed a second, unrelated bug — the GC2145 driver
skips its widest field-of-view subsample ratio at QVGA and above,
producing a fixed sensor-pixel-space crop. Root-caused and fixed via a
runtime register poke in `cam_node.ino` (developer-confirmed live,
FOV "good enough" though narrower than the MacBook webcam used through
Phases 0–11) — see logs.md "Phase 13a — FPS measured, narrow-FOV bug
root-caused and fixed" for full detail. Not an fps-related finding,
noted here only because it surfaced during this same QVGA measurement
session.

**New practical streaming target: 320×240 (QVGA) @ ~10fps**, measured
on real GC2145 hardware, superseding the VGA/5fps OV2640 assumption
above.

### 10.4 Connectivity — two switchable network contexts

- **HOME:** ESP32 connects directly to home WiFi, simple
  WPA2-Personal.
- **COLLEGE:** college WiFi requires SAP ID + password via a captive
  portal, which ESP32 firmware cannot handle directly (no browser/
  portal interaction capability on a microcontroller). **Solution:**
  the developer's laptop connects to and authenticates on college WiFi
  normally (logging into the captive portal as usual), then shares
  that connection via macOS Internet Sharing as a new, simple
  WPA2-Personal hotspot. The ESP32 connects to **this shared hotspot**,
  never touching the college network or its captive portal directly.
- **WiFiManager** (standard ESP32/Arduino library) handles switching
  between these two saved-network contexts via a reset-and-reconfigure
  flow (temporary setup hotspot, web-based credential entry) — no
  reflashing needed when moving between home and college.

**Rejected alternatives, for the record:**
- Mobile hotspot — viable fallback, but laptop-sharing is preferred
  since it uses the real institutional network at college.
- WPA2-Enterprise direct connection — technically possible via the
  `esp_wpa2` library, but the college's captive portal specifically
  (not just enterprise auth) makes direct connection infeasible
  without IT-side MAC whitelisting, which was not pursued.

### 10.5 No-WiFi fallback — decided

A total WiFi outage means **no vision-based detection at all** — an
explicit, disclosed architectural trade-off of cloud inference, stated
plainly rather than hidden.

**Mitigation, updated for the two-board split (§10.0a):** the plain
ESP32 DevKit (sensor board) monitors MQ-2/MQ-135 readings locally,
against hardcoded threshold values mirroring `fusion.py`'s calibrated
warn/danger thresholds, and drives the buzzer **directly** from its
own GPIO — entirely independent of WiFi/cloud and of the ESP32-CAM.
Because gas sensing and vision now live on physically separate boards,
this fallback has no dependency at all on the ESP32-CAM's WiFi/camera
state — a stronger isolation than the original single-board plan,
where sensors and camera would have shared one WiFi radio. This
remains a genuine, disclosed degradation path (gas-only, local-only
fallback), not a silent gap: the system degrades gracefully from
"vision+gas fusion, cloud-verified" to "gas-only, local-only" rather
than going fully silent.

### 10.6 Data flow

```
ESP32-CAM (camera only)
   --WiFi-->
AWS Lambda (runs v4 ONNX model on each frame)

Plain ESP32 DevKit (MQ-2 + MQ-135 + buzzer)
   -- computes gas_high locally, drives buzzer directly, independent of WiFi --
   --WiFi (if available)--> reports gas readings for fusion display

Lambda's vision result + sensor board's gas_high, fused
   -->
FastAPI backend's NEW WebSocket endpoint (does not exist yet)
   -->
broadcast to connected React dashboard clients
   -->
rendered on a NEW "Live View" dashboard tab
```

**RESOLVED 2026-09-23 (Phase 13f, Stages 1-5 — see logs.md).** The
open transport question above is settled and built. What was actually
implemented differs from the sketch above in two deliberate ways:

1. **The sensor board POSTs to the EDGE LOOP, not the dashboard
   backend.** A plain 1 Hz HTTP POST of one JSON reading (mq2, mq135,
   state, six live thresholds) — no MQTT, since there is no broker to
   depend on and the consumer is a single known host. The ingest server
   lives inside `edge/main.py` (`edge/wifi_source.py`) rather than
   `dashboard/backend`, because that backend is an *optional* dev-time
   process: routing sensor data through it would have made the
   dashboard a hard dependency of the **detector**, inverting
   `fusion.py`'s "no model, no LLM, no network" guarantee.

2. **Detection did NOT move to Lambda.** The diagram above has Lambda
   running the ONNX model on each frame. Continuous per-frame cloud
   inference was rejected on cost ($18-89/mo) and, more importantly, on
   safety grounds: a WAN outage must never silently downgrade the
   detector. Local inference stays the always-on path. Event-triggered
   Lambda as a cloud *second opinion* on `GAS_HIGH` remains available as
   Stage 6, and is explicitly cuttable.

Camera fan-out — unaddressed in the sketch above — is solved by a relay
(`edge/camrelay.py`) holding `cam_node.ino`'s single `/stream` slot and
serving every consumer from a lock-guarded newest-frame slot. Both the
edge loop and the dashboard read through it.

Host discovery across networks (home WiFi vs phone hotspot) is by mDNS,
then a bounded subnet scan, so switching networks needs no reflash.

**Stage 6 BUILT 2026-09-24 (Phase 13g — see logs.md).** Event-triggered
Lambda second opinion, as point 2 above left open:

- **Trigger:** the rising edge of the board's `GAS_HIGH` — one gas event,
  one invocation, never per frame. Guards are client-side
  (`cloud/second_opinion.py`): rising edge, 60s cooldown, 20 calls per
  session, no retries. Default OFF (`aws.second_opinion.enabled`).
- **Advisory only.** The verdict goes to a sidecar file the dashboard
  reads and has no path back into `fuse()`. Disable it and detection is
  byte-for-byte unchanged. It never gates the buzzer.
- **Verdict is full-frame**, identical arithmetic to local; the 5-crop
  scores ride along as diagnostics only (5-crop MAX was measured and
  rejected: +1.3% recall for +18% neutral FP).
- **Shown in Live View** beside the local verdict with an explicit
  agree/disagree state, on the visual question only (fire/smoke in frame).

### 10.7 Live View — new dashboard tab (BUILT 2026-09-23, Phase 13f Stage 5)

Real-time camera feed via WebSocket, with:

- an AI classification badge overlaid (SAFE/WATCH/WARNING/CRITICAL,
  reusing the existing fusion-level color language), **plus**
- a live-updating `p_fire` confidence value/indicator shown alongside
  the feed, so a viewer can watch confidence build toward an alarm in
  real time, not just see a static badge flip.

### 10.8 Remote access

A natural consequence once the dashboard backend is actually
**deployed** (not just localhost) — contingent on completing that
deployment step (previously discussed, not yet executed), not
additional engineering once deployed.

### 10.9 Open design question — flagged for future discussion

How does info.md §2.2's "local alarm before any network attempt"
principle apply now that **vision** inference is inherently
cloud-dependent? The gas-only local fallback (§10.5 above) is the
current answer for connectivity loss specifically, but this deserves
explicit discussion/confirmation before implementation begins — not a
quiet assumption that it is fully resolved.

**RESOLVED 2026-09-09** — see info.md §2.2 (scope clarification added
directly to the principle's text). Resolution summary: the "local
alarm before network" principle is scoped specifically to GAS-based
detection (MQ-2/MQ-135), which remains fully local with zero network
dependency; vision-based detection is explicitly disclosed as
cloud-dependent by design (no local alternative was ever a candidate,
per §10.2), so the gas-only fallback on WiFi loss (§10.5) is
consistent with the principle, not a violation of it.

### 10.10 Status

**IN PROGRESS, updated 2026-09-16.** No Lambda function, WebSocket
endpoint, or dashboard code for this phase has been built yet.

**10.10a — ESP32-CAM (camera board):** flashed and confirmed working
(2026-09-09, GPIO4 LED blink test via the MB shield programmer). No
sensor wiring on this board. Camera streaming/Lambda integration
itself not yet built.

**10.10b — plain ESP32 DevKit (sensor board, added 2026-09-16):**
wiring complete and confirmed working via Serial Monitor (§10.0a).
Burn-in in progress, not yet stable. No firmware written yet — the
board has only been read manually, not running a project sketch.
Calibration (10-bit-vs-12-bit question) and the airflow false-positive
mitigation are both open decisions, not yet made — see §10.0a and
logs.md "Phase 13 — architecture change: two-board split".

---

## Appendix A — Hardware primer

### A.1 The three wires on every module

| Pin | Meaning | Connect to |
|---|---|---|
| **VCC** | Power in | Arduino `5V` |
| **GND** | Ground / return path | Arduino `GND` |
| **A0 / D0 / DATA** | The signal — what the sensor is telling you | A named Arduino pin |

Current flows from 5V, through the module, back to GND. Without a GND connection nothing works, even with VCC connected.

### A.2 Analog vs digital — why A0 and never D0

MQ modules expose both pins:

- **`D0` (digital)** — one bit: gas or no gas. Cutoff set by the small potentiometer screw on the module. Crude, hand-tuned, useless for fusion.
- **`A0` (analog)** — a number from 0 to 1023 representing actual concentration.

Always use A0. The fusion logic needs to distinguish "slightly elevated" from "dangerous," which one bit cannot express.

The 0–1023 range comes from the Arduino's 10-bit ADC: 2¹⁰ = 1024 levels, mapping 0V→0 and 5V→1023. A reading of 512 means roughly 2.5V on the pin.

### A.3 How an MQ sensor actually works

Inside is a bead of **tin dioxide (SnO₂)** wrapped around a heating coil.

1. The heater raises the bead to ~300°C. The chemistry only works hot — this is why the heater exists and why the sensor feels warm.
2. At that temperature, atmospheric oxygen adsorbs onto the bead surface and captures electrons from it. Fewer free electrons → **high resistance**.
3. Flammable gas (LPG, methane, smoke particulates) reacts with that adsorbed oxygen and **releases the captured electrons back**. More free electrons → **low resistance**.
4. The module converts resistance into a voltage read on A0.

**More gas → lower resistance → higher voltage → higher number.**

### A.4 Burn-in — why 24 to 48 hours

Sensors sit in packaging for months. Moisture, packing residue, and contaminants settle on the SnO₂ surface. On first power-up the heater is cooking all of that off, and readings drift heavily — typically starting very high and falling for hours.

Calibrating during that drift produces thresholds that are wrong a day later.

**Procedure:**

- Connect **only** VCC to 5V and GND to GND. No sketch required, no Arduino code — power is all it needs.
- Leave it. 24h minimum, 48h preferred.
- Sensor becomes noticeably warm. This is correct behaviour, not a fault.
- After 24h, watch readings for 15 minutes. Stable within ±20 → ready. Still drifting → another 24h.

### A.5 Pull-up resistors — the DHT22 10kΩ

The DHT22's data pin can only actively **pull the line low**. When it is not transmitting, the line floats and picks up electrical noise, producing `NaN` readings.

The 10kΩ resistor connects that data line to 5V, holding it high whenever the sensor is not pulling it down, giving the line a defined resting state.

**Physically:** one leg into the same breadboard column as the DHT data pin, the other leg into the 5V rail. Resistors have no polarity — orientation does not matter.

### A.6 Breadboard basics

- **The two long rails along the top and bottom edges** (marked `+` red and `−` blue) run **horizontally** the full width. These are power rails. Run one jumper from Arduino `5V` to the red rail and one from `GND` to the blue rail, and every component can then take power from anywhere along the board.
- **The main central area** connects in **vertical columns of 5 holes**, with the two halves separated by the centre channel.

Any two holes in the same 5-hole column are the same electrical point. This is how the pull-up resistor connects to the DHT data pin — both legs go in the same column.

### A.7 Component polarity

| Component | Polarity | Getting it wrong |
|---|---|---|
| LED | Long leg = anode = positive. Short leg = cathode = GND | Will not light. No damage |
| Active buzzer | Marked `+` and `−` | Will not sound. No damage |
| Resistor | None | N/A |
| DHT22 | Pin 1 = VCC, pin 2 = DATA, pin 4 = GND (pin 3 unused) | Can damage the sensor — check the datasheet marking |
| MQ modules | Labelled on PCB | Reversing VCC/GND can damage the module |

**Rule: disconnect USB power before rewiring.** Always.

---

## Appendix B — Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Arduino resets when buzzer fires | Power budget exceeded (§5.4) | Connect 5V 2A adapter to barrel jack |
| DHT22 returns NaN every read | Missing 10kΩ pull-up | Add pull-up from DATA to 5V |
| MQ reading pinned at 1023 | Still burning in, or wired to D0 not A0 | Wait longer / rewire to A0 |
| MQ reading stuck at 0 | No power to heater, or GND not connected | Check VCC and GND continuity |
| MQ reading drifts all day | Insufficient burn-in | Leave powered another 24h |
| Serial port not found in Python | Wrong port name, or Serial Monitor still open | Close Arduino IDE Serial Monitor. Check port: `COM3` on Windows, `/dev/ttyUSB0` or `/dev/ttyACM0` on Linux |
| First serial reads are garbage | Arduino auto-resets when the port opens | `time.sleep(2)` after opening the port |
| LED does not light | Reversed polarity, or missing resistor path | Flip the LED |
| Camera opens but frames are black | Another app holds the camera | Close Zoom/Teams/browser tabs |
| ONNX output differs from PyTorch | Preprocessing mismatch | Verify normalization mean/std and BGR→RGB conversion |
| Model always predicts one class | Class imbalance or LR too high | Check class balance chart, lower LR |
| Overpass returns nothing | Radius too small, or rate limited | Widen radius, add retry with backoff |
| Telegram message never arrives | Wrong chat ID, or bot never messaged first | Send `/start` to the bot from your account once |

---

## Appendix C — Report checklist

- [ ] Architecture diagram showing edge-first decision flow
- [ ] Justification for each of the 8 design changes in section 1
- [ ] Dataset composition table including the hard-negatives breakdown
- [ ] Training curves and confusion matrix
- [ ] **Per-scenario false positive rate table** — the headline result
- [ ] Detection latency distribution from the fire video set
- [ ] MQ calibration evidence: baseline, peak, derived thresholds
- [ ] Fusion truth table with the reasoning for each row
- [ ] Offline operation test result (network disconnected)
- [ ] Cost breakdown: prototype cost vs projected production cost
- [ ] Explicit ethics and safety section on simulated dispatch
- [ ] Honest limitations section
- [ ] Future work: 1D CNN on sensor sequences, Pi port, OTA updates, GPS
- [ ] 3-minute demo video including the cable-unplug moment
