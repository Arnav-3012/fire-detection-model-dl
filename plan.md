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
10. [Appendix A — Hardware primer](#appendix-a--hardware-primer)
11. [Appendix B — Troubleshooting](#appendix-b--troubleshooting)
12. [Appendix C — Report checklist](#appendix-c--report-checklist)

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
