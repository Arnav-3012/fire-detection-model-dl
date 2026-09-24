# FireWatch — Final Project Report

**IoT fire and gas hazard detection with edge inference and agentic response**

| | |
|---|---|
| **Deadline** | 30 August 2026 |
| **Report date** | 6 September 2026; Phase 13 addendum 24 September 2026 |
| **Owner** | Solo build |
| **Status** | Phases 0–13 complete. Sections 1–12 are the Phase 12 report as written; Section 13 covers the Phase 13 two-board migration |

---

## Abstract

FireWatch is a laptop-hosted edge node that fuses a webcam-based fire/smoke
classifier with Arduino-read MQ-2 and MQ-135 gas sensors to produce a
three-tier hazard verdict (SAFE / WARNING / CRITICAL) entirely on-device,
with no dependency on network connectivity for detection. A LangGraph
agent handles response only — Telegram alerting with a cancel window,
Twilio SMS, a display-only nearest-fire-station lookup, and a simulated
(never-transmitted) dispatch log — while a React/FastAPI dashboard
surfaces live and historical state. The production vision model
(MobileNetV3-Small, "v4") reaches 0.9575 fire recall and 0.8511 smoke
recall on a leak-free validation split. A reduced 12-trial live evaluation
(6 hazard / 6 non-hazard, scaled down from the original ≥20+≥20 target
under time constraints) passed 11 of 12 trials and surfaced one new,
previously undocumented failure mode — a false WARNING in total darkness —
along with two hardware/environmental findings (a loose buzzer connection,
and camera autofocus transients briefly inflating fire confidence). All
findings are reported here as measured, not smoothed over.

**Phase 13 addendum (Section 13).** After the original report, the build
moved to two WiFi boards: an ESP32-CAM streaming video through a relay,
and an ESP32 sensor board that owns its own baseline, thresholds and
buzzer. The migration uncovered two silent failures in the gas path — a
parser that dropped every line from the new firmware, and host-side
thresholds that would have produced a false alarm on MQ-2 and a missed
detection on MQ-135 at the same time — both fixed and measured. An AWS
Lambda running the same v4 model now gives an advisory second opinion
(bit-identical `p_fire` to local on the reference frame), and the
dashboard was rebuilt around the live camera and sensor feed.

---

## Table of Contents

1. [What FireWatch Is](#1-what-firewatch-is)
2. [Design Changes From the Original Idea](#2-design-changes-from-the-original-idea)
3. [Architecture](#3-architecture)
4. [Dataset](#4-dataset)
5. [Training Results](#5-training-results)
6. [Adversarial Evaluation](#6-adversarial-evaluation)
7. [Phase 11 Evaluation Trials](#7-phase-11-evaluation-trials)
8. [Hardware Status](#8-hardware-status)
9. [Cost Breakdown](#9-cost-breakdown)
10. [Ethics and Safety](#10-ethics-and-safety)
11. [Limitations](#11-limitations)
12. [Future Work](#12-future-work)
13. [Phase 13: Two-Board Migration](#13-phase-13-two-board-migration)

---

## 1. What FireWatch Is

**Core deliverable:** a laptop-hosted edge node with a webcam and an
Arduino sensor board detects fire or smoke locally, cross-checks it
against gas readings, and — with the internet disconnected — produces a
verified alert that reaches a real phone and a logged simulated dispatch
packet, all within seconds of hazard onset.

**The demo moment:** mid-demonstration, the network is disconnected. The
buzzer still fires, the local decision still happens with no cloud
round-trip. On reconnection, the queued alert reaches the phone. This is
the single strongest argument for the architecture: detection survives
exactly the failure condition — a fire taking out the router — that a
cloud-dependent design cannot.

**Explicitly out of scope:** real emergency-service integration, a mobile
app, over-the-air model updates, multi-device fleet management, training
a model from scratch, and enclosure/PCB design.

---

## 2. Design Changes From the Original Idea

Eight deliberate deviations from the original concept, each made for a
stated engineering or legal reason rather than convenience:

| # | Original plan | Revised plan | Reason |
|---|---|---|---|
| 1 | Auto-dial emergency services | Simulated dispatch, logged but never transmitted | False emergency reporting is a criminal offence (BNS §217); no public dispatch API exists; real products verify with a human first anyway |
| 2 | Camera → cloud → model decides | Model runs locally on the edge device; cloud logs and retrains only | A fire destroys the router — detection must survive network loss. Cloud inference per frame also breaks the cost model |
| 3 | Camera only | Camera **plus** gas sensors, fused | Camera alone false-triggers on sunsets, steam, TVs, red objects, and cannot see a gas leak with no visible flame |
| 4 | Raspberry Pi as edge device | **Laptop is the edge device**; Pi optional stretch | Pi setup (OS flash, camera enable, ARM builds) costs at least 2 days and can fail outright |
| 5 | Train a CNN from scratch | Fine-tune pretrained MobileNetV3-Small | No time to collect and label a dedicated fire dataset; transfer learning reaches useful accuracy in one session |
| 6 | Agent decides if there is a fire | Agent handles **response only**, never detection | LLMs are non-deterministic — never place one in a safety-critical detection path |
| 7 | 1D CNN on sensor time-series | Threshold plus temporal smoothing | Not enough time to collect labelled sensor sequences; listed as future work |
| 8 | GPS module for location | Hardcoded coordinates, GPS optional | Indoor GPS modules do not get a satellite lock |

**Design principle carried throughout:** deterministic detection, agentic
response.

---

## 3. Architecture

### 3.1 Vision model: architecture and rationale

**Model:** MobileNetV3-Small, ImageNet-pretrained, fine-tuned into a
3-class (neutral / smoke / fire) classifier. Production checkpoint is
**v4** (`models/fire_mnv3.onnx`, SHA `36de3559…`), exported from
`fire_mnv3_v4.pt` (`train/train_classifier.py`, `train/export_onnx.py`).

**Why MobileNetV3-Small and not a larger network.** The deployment
target is a laptop CPU running ONNX Runtime at ≥5 FPS *while* a live
camera loop and the rest of the fusion pipeline are also running
(`plan.md` §4.3 / `info.md` §4.3's real-time bar). MobileNetV3-Small is
~2.5M parameters and was designed via hardware-aware neural architecture
search specifically for fast mobile/CPU inference — a ResNet-50-class
model (~25M parameters) might add a point or two of raw accuracy but
would risk the FPS budget the whole safety case depends on. This is a
deliberate params-vs-latency trade: give up a small amount of ceiling
accuracy to guarantee the 30 FPS the temporal voter and buzzer latency
targets assume.

**Why transfer learning instead of training from scratch.** The dataset
is 18,678 training images (Section 4) — far too few to learn general
visual features (edges, textures, colour gradients, shape) from
scratch. ImageNet pretraining already learned those features on 1.2
million images; fine-tuning only needs to teach the network the last
step: mapping features it already knows how to extract onto
neutral/smoke/fire. This is design change #5 (Section 2).

**Head replacement.** The stock MobileNetV3-Small classifier ends in
`Linear(1024 → 1000)` for ImageNet's 1000 classes, which is meaningless
for this task. That final layer is discarded and replaced with a fresh
`Linear(1024 → 3)`. Every layer before it keeps its pretrained ImageNet
weights; only this new head starts from random initialization.

**Two-stage training schedule (12 epochs total, `--epochs 12` default):**

| Stage | Epochs | What's trainable | Learning rate | Why |
|---|---|---|---|---|
| 1 — head warm-up | 1–2 | Only the new `Linear(1024→3)` head (`classifier.3`); the rest of the network is frozen (`requires_grad=False`) | `1e-3` | The random head's large, noisy early gradients would otherwise backpropagate into and scramble the pretrained filters before the head has learned anything sensible |
| 2 — full fine-tune | 3–12 | Every parameter, unfrozen | `5e-5` (20× lower than stage 1) | Once the head is sensible, the pretrained ImageNet filters are nudged gently toward fire/smoke-specific textures. A stage-1-sized learning rate here would overwrite useful pretrained weights instead of adapting them — "catastrophic forgetting" |

Both stages use `AdamW` with a `CosineAnnealingLR` schedule (per stage,
stepped once per epoch, not per batch). A fresh optimizer instance is
created at the stage-2 transition — required because the stage-1
optimizer never registered the (until then frozen) backbone parameters.

**Input pipeline.** Inputs are 224×224 RGB, normalized with ImageNet's
channel statistics (`mean [0.485, 0.456, 0.406]`, `std [0.229, 0.224,
0.225]`) — required because the pretrained filters were themselves
trained on inputs normalized this exact way; anything else would push
inputs out of the distribution the pretrained features expect. Training
images are augmented (random-resized crop scale 0.6–1.0, horizontal
flip, mild colour jitter — brightness/contrast/saturation ±0.2, hue only
±0.02) to simulate a fire appearing nearer/farther/off-centre and under
different white balance, while deliberately keeping hue jitter small
since hue is exactly what separates fire from steam and sunsets in this
task; aggressive hue jitter would destroy the signal the model needs to
learn. Validation images get a plain 224×224 resize and normalization
only, with no augmentation, and deliberately a direct resize rather than
resize-then-center-crop — this is chosen to exactly mirror what
`edge/vision.py` does to a live webcam frame at inference time, so
validation accuracy is an honest estimate of deployment accuracy rather
than a jittered training-time metric.

**Training hardware.** Training ran locally on the developer's Apple
M4 Pro via PyTorch's MPS (Metal) backend — a deliberate deviation from
`plan.md`'s original plan to train on Google Colab, made because local
MPS training was available and avoided Colab's session/runtime
constraints. Batch size 128 (larger than a typical Colab T4's headroom
would allow, since the M4 Pro's 24GB unified memory gives more room —
with the caveat that "unified" memory is shared with the OS and every
other open app, so the usable ceiling is softer than a discrete GPU's
dedicated VRAM). Seeds are fixed (`SEED=42`) across Python, NumPy, and
PyTorch for reproducibility, with an explicit documented caveat: MPS
does not offer CUDA's deterministic-algorithm guarantees, so two runs
with identical seeds may still differ in the last decimal places of a
metric — bit-exact repeatability is only promised on CPU.

**Export and equivalence check.** The trained PyTorch checkpoint is
exported to ONNX (`train/export_onnx.py`) for the edge loop's
ONNX-Runtime inference path. Every promoted checkpoint (v1 through v4)
is checked for PyTorch/ONNX numerical equivalence — maximum absolute
logit difference across 32 real validation images — before being
trusted as production; v4's diff was **5.99 × 10⁻⁵**, against a
1 × 10⁻⁴ pass bar.

**Decision thresholds on top of the raw model** (`config.yaml`,
`edge/vision.py`): the raw 3-class softmax output is not used directly
as a verdict. Fire is called only if `P(fire) ≥ 0.30` — chosen via a
threshold sweep as the lowest threshold that still clears both the
project's fire-recall and fire-precision bars (`info.md` §4.1). Smoke
requires an "argmax-AND" rule: smoke must both win the 3-way class vote
**and** clear `P(smoke) ≥ 0.45` — added after live testing showed argmax
alone let smoke spuriously win 3-way splits at 0.28–0.44, a real observed
false-positive band this rule removes by construction, at a measured
cost of a small drop in raw smoke recall on the validation set (Section
5).

### 3.2 Detection pipeline (fusion and alarm)

- **Temporal voting:** a sliding 8-frame window requires 5 positive votes
  (5-of-8) before a fire or smoke signal is trusted, independently for
  each class, at confidence threshold `tau = 0.70` for fire's per-frame
  gate. This is what turns a single noisy model output on one frame into
  a stable verdict, and is the mechanism that (mostly) absorbs transient
  camera artifacts — see Section 7.3 for a case where a sustained-enough
  artifact still cleared it.
- **Gas sensing:** Arduino Uno reads MQ-2 (A0) and MQ-135 (A1) at 1 Hz,
  streamed to the host over serial. A 240-second warm-up gate forces
  `gas_high = False` after any fresh power-cycle, since a cold MQ-135
  reads above its own warn threshold before settling.
- **Fusion:** vision and gas signals are combined into four levels —
  SAFE, WATCH, WARNING, CRITICAL. Vision-only fire/smoke evidence caps at
  WARNING ("visual flame/smoke, unconfirmed by sensors"); gas-only
  evidence with no visual corroboration also caps at WARNING ("gas
  concentration high, no visible flame"); only agreement between vision
  and a genuine gas reading reaches CRITICAL ("visual hazard confirmed by
  gas sensor"). This non-escalation guarantee — that gas alone can never
  reach CRITICAL — is explicitly tested in Section 7.
- **Local alarm:** the buzzer (Arduino D8) sounds on any WARNING+ level,
  driven by a transition-only serial write (`'A'`/`'S'` bytes) from the
  host, independent of and prior to any network activity.

### 3.3 Response pipeline (agent)

Detection and response are strictly separated (design change #6, Section
2). On a WARNING+ verdict, `edge/main.py` posts to a LangGraph agent
(`agent/graph.py`) which:

1. Looks up the nearest fire station via Overpass (`agent/locate.py`) —
   **display-only**, the station name/number appears in alert text but is
   never an automated dial target.
2. Composes an alert message (Groq `openai/gpt-oss-20b` with a
   deterministic template fallback).
3. Sends it via **Telegram** — the sole channel through which an owner
   can cancel a pending dispatch (reply `CANCEL` within a 60-second
   window).
4. Sends an informational-only **Twilio SMS** (voice calls were dropped
   from scope — see Section 11).
5. On timeout (no cancel) or explicit cancel, logs the outcome to
   `eval/alert_feedback.csv` and, for CRITICAL incidents only (cancelled
   or not), uploads an incident packet to S3 — this is the cloud log/
   retrain corpus, never a real dispatch.

### 3.4 Dashboard

A React (Vite) frontend and a read-only FastAPI backend (port 8001,
independent of the agent's own server) expose five tabs: Overview, Live
Incidents, Historical Archive (S3), Evaluation Trials, and Nearest Fire
Station. Built as a deviation from `plan.md`'s original Streamlit
specification, per explicit developer instruction, prioritizing visual
polish. *Superseded in Phase 13: four tabs with a live-first home page —
see Section 13.5.*

---

## 4. Dataset

The production split (rebuilt 2026-09-04, leak-checked by filename **and**
content hash) contains:

| Split | Images |
|---|---|
| Train | 18,678 |
| Validation | 3,296 (neutral 1,522 / smoke 880 / fire 894) |

Eight categories in total, including targeted hard-negative sets:

- `bright_light_textured_wall` — 30 frames added specifically to fix a
  live smoke false-positive on patterned backgrounds under bright light
  (see Section 5).
- Webcam hard negatives and a held-out validation clip that **include the
  developer and 1–3 other people in frame**. This was a deliberate
  developer decision to keep and disclose this data as-is — it must never
  be described as "clean," "controlled," or "background-only" in any
  downstream summary of this project.

A content-hash leakage check (`train/check_leakage.py`) additionally
caught 4 stock photos that were byte-identical across the `stove_cooking`
(neutral) and `gas_stove_flame*` (fire) categories in an earlier split;
these were resolved by treating stove flame as fire and moving the
neutral duplicates out of the training set.

---

## 5. Training Results

Four checkpoints were trained (v1–v4); v4 is production as of 2026-09-05.

| Metric | v3 (archived) | **v4 (production)** |
|---|---|---|
| Validation accuracy | 0.9031 | **0.9129** |
| Fire recall @ 0.30 threshold | 0.9541 (margin 0.41 pts) | **0.9575 (margin 0.75 pts)** |
| Fire precision @ 0.30 | 0.8660 | 0.8664 |
| Smoke recall @ 0.45 argmax-AND | 0.8284 (below the 0.85 bar) | **0.8511 (first checkpoint to clear it)** |
| Macro F1 | 0.8967 | 0.9065 |
| Smoke false positives (val) | 107 | 109 |
| ONNX export diff (max \|PyTorch − ONNX\| logit) | — | **5.99 × 10⁻⁵**, PASS (≤ 1×10⁻⁴ bar) |

The v3 → v4 retrain was driven by a live finding: a bright, textured wall
under strong lighting produced a sustained smoke false-positive lock
(smoke votes saturating 8-of-8) that the temporal voter alone could not
filter. Adding `bright_light_textured_wall` hard negatives and retraining
dropped the held-out clip's smoke-frame rate from **98.0% to 0.0%** — the
single clearest before/after result in the project (also independently
re-confirmed live in Section 7, trial 11).

Training curves and a confusion-matrix image were not compiled into this
report — they exist as artifacts from the training run and can be
regenerated from the training script/logs if needed for submission.

---

## 6. Adversarial Evaluation

Fixed adversarial video clips (Phase 5), re-run against production v4:

| Scenario | v3 result | v4 result | Status |
|---|---|---|---|
| Sunset | 0 alarms | 0 alarms | PASS |
| Steam | 21 smoke-WATCH events | 5 smoke-WATCH events | Improved, still a documented limitation |
| Red clothing | 0 alarms | 0 alarms | PASS |
| TV/laptop fire | 7 alarms | 6 alarms | **Documented, bounded limitation** — capped at WARNING by fusion, never reaches CRITICAL |
| Candle | 3 alarms | 4 alarms | Expected — a candle is genuine open flame |
| Bright-wall webcam clip, smoke-frame rate | 98.0% | **0.0%** | Fixed by the v4 retrain |

This is the headline false-positive table referenced in `plan.md`'s report
checklist. The TV-fire and steam scenarios remain the two open,
consciously-accepted adversarial limitations of the vision model; both
are bounded by fusion rule design (vision-only evidence cannot reach
CRITICAL) rather than eliminated at the model level.

---

## 7. Phase 11 Evaluation Trials

### 7.1 Deliberate scope reduction

`info.md` §4.4 specifies a minimum of **≥20 hazard and ≥20 non-hazard**
live trials. Given real time constraints ahead of the 7 September 2026
working deadline, the developer made an explicit, reasoned decision to
run a smaller, still-balanced set of **12 trials (6 hazard, 6
non-hazard)** instead. This is disclosed here plainly: **the 20+20 bar
was not met**, and this report does not present 12 trials as equivalent
to that target.

The reduction was not arbitrary. Each of the 12 trials was chosen to
exercise a distinct fusion rule or re-verify a specific finding already
on record, rather than repeat the same few code paths:

- Trials 1, 2, 5 — the core WARNING → CRITICAL escalation path (vision
  alone vs. vision+gas agreement, on both gas sensors).
- Trials 3, 4, 6 — gas-alone behavior; trial 6 specifically confirms gas
  can never falsely escalate to CRITICAL without vision agreement.
- Trials 7–9 — established SAFE/adversarial baselines from Phase 5.
- Trial 10 — re-confirms the TV-fire known limitation stays bounded to
  WARNING on the newly-promoted v4 model.
- Trial 11 — re-confirms the v4 smoke-recall retrain fix under live
  conditions, on the exact scenario that caused it.
- Trial 12 — general lighting robustness.

### 7.2 Results

All 12 trials were run via `eval/run_trial.py` against production v4,
each logged to `eval/results.csv` and cross-checked against the expected
outcome. **Result: 11 of 12 PASS.**

| # | Trial | Expected | Actual | Latency | Result |
|---|---|---|---|---|---|
| 1 | Fire video alone, no gas | WARNING | WARNING | 83.2 s | PASS |
| 2 | Fire video + gas-stove (MQ-2) | CRITICAL | CRITICAL | 11.3 s (clean rerun) | PASS* |
| 3 | Gas-stove alone, neutral view | WARNING | WARNING | 54.3 s | PASS |
| 4 | Alcohol/MQ-135 alone, neutral view | WARNING | WARNING | 73.9 s (clean rerun) | PASS* |
| 5 | Fire video + alcohol/MQ-135 | CRITICAL | CRITICAL | 98.8 s | PASS |
| 6 | Gas-stove, camera pointed away | WARNING | WARNING | 3.0 s | PASS |
| 7 | Empty room | SAFE | SAFE | not reached | PASS |
| 8 | Person in frame, moving naturally | SAFE | SAFE | not reached (clean rerun) | PASS* |
| 9 | Red clothing in frame | SAFE | SAFE | not reached (clean rerun) | PASS* |
| 10 | TV/laptop fire, no gas | WARNING | WARNING | 1.9 s | PASS |
| 11 | Bright wall / v4 smoke-recall recheck | SAFE | SAFE | not reached (clean rerun) | PASS* |
| 12 | Lighting changes incl. total darkness | SAFE | WARNING | 86.5 s | **FAIL** |

\* See findings below — first attempt on these trials was affected by an
invalid condition, a camera artifact, or a wiring fault; the reported
result is from a clean, representative rerun. Nothing here is hidden —
every first-attempt anomaly is documented in the findings that follow.

### 7.3 Findings

**Finding 1 — Total darkness produces a false WARNING (Trial 12, unresolved FAIL).**
With the room in complete darkness, `p_fire` climbed steadily from 0.29
to 0.96 over roughly 4 seconds, reached 5-of-8 temporal votes, and fired
a genuine local alarm ("visual flame, unconfirmed by sensors"). `gas_high`
was `False` throughout the episode, ruling out any gas-side contribution
— this is a vision-only false positive. The alarm self-de-escalated once
light returned and votes decayed. This is a **new, previously
undocumented limitation**, distinct from the bright-wall issue that drove
the v4 retrain (opposite lighting extreme). The suspected but
**unconfirmed** cause is that the training set likely contains few or no
true near-black, heavily underexposed negative frames, so webcam
auto-exposure noise/grain in darkness may resemble fire-like texture to
the model. Ordinary lighting variation (lamp on/off with the room
otherwise lit, walking past a window) did **not** reproduce this — the
failure is specific to sustained total darkness. No retrain or threshold
change was made in response; it is reported here as an open limitation.

**Finding 2 — A loose D8 buzzer connection silently defeated the physical alarm (Trial 2, hardware).**
On the first attempt at Trial 2, the fusion logic correctly computed and
logged CRITICAL, and the code-level alarm transition fired as expected —
but the physical buzzer did not sound. The cause was a loose wiring
connection at the Arduino's D8 pin (the buzzer's designated pin per the
project's pin map), not a software fault; no "alarm byte not sent" serial
warning appeared, confirming the software write path was healthy
throughout. Reseating the connection and rerunning reproduced CRITICAL
with the buzzer sounding correctly. This is recorded as a
hardware-reliability lesson: correct detection and fusion logic does not
guarantee a correct physical alarm if a connection is loose, and this
should be physically re-verified before any live demonstration.

**Finding 3 — Camera autofocus/exposure transients twice inflated fire confidence enough to move the temporal vote (Trials 4 and 11, recurring nuisance).**
On Trial 11's first attempt, the camera's autofocus was still hunting at
trial start; the resulting transient blur produced a brief WARNING
against what should have been a stable bright-wall SAFE reading. On Trial
4's first attempt — a trial designed to test gas alone with a neutral
camera view — a similar camera glitch pushed `p_fire` high enough,
combined with the real MQ-135 gas trigger, to reach a spurious CRITICAL.
Both were resolved cleanly on an immediate rerun once the camera had
settled. This is recorded as a recurring, documented nuisance: the
webcam's autofocus/exposure behavior can occasionally sustain a false
fire signal long enough to clear the 5-of-8 temporal vote threshold. The
practical mitigation used here — letting the camera sit still for a few
seconds before starting a trial — is not a fix at the model or fusion
level and should be treated as an operational caveat, not a resolved
issue.

**Finding 4 — Trial 8 showed a borderline, non-repeatable result.**
Two back-to-back runs of "person in frame, moving naturally" under
identical conditions produced different outcomes: the first reached
WATCH, the immediate rerun held SAFE. No deliberate change in conditions
was made between the two runs. This sits close to the smoke-vote decision
boundary and is reported as an observed non-repeatability rather than a
resolved pass — a genuinely clean, unambiguous pass was not obtained on
this specific scenario.

**A separate class of invalidated attempts** (Trials 8's earlier
flashlight-near-camera attempt, and Trial 9's cloth-held-too-close
attempt) are excluded from the results table above — these were
identified as testing a materially different physical condition than the
trial specifies (e.g., red clothing worn at normal distance vs. fabric
pressed against the lens), not a system failure, and the clean rerun at
the correct condition is what is reported.

---

## 8. Hardware Status

*This section is the Phase 11 hardware as trialled. The Arduino Uno and
webcam were retired in Phase 13; the current two-board hardware is in
Section 13.3.*

| Item | Status |
|---|---|
| Arduino Uno R3 | Working; alarm sketch ('A'/'S' → D8) confirmed live |
| MQ-2 (A0) | Wired, calibrated: baseline 57.1, warn 115.57, danger 174.04 |
| MQ-135 (A1) | Wired, calibrated: baseline 51.1, warn 98.77, danger 146.44; confirmed undamaged post-incident |
| Buzzer (D8) | Confirmed working; one loose-connection incident found and fixed during Phase 11 (Section 7, Finding 2) |
| DHT22 | **Cut from scope** — `temp_spiking()` always returns `False`; not a wired/working sensor in this build |
| Red/green LEDs, breadboard | Ordered, never wired — H3 (red LED test) not re-confirmed |
| Webcam | MacBook built-in, confirmed working through adversarial and Phase 11 trials |

Pin map (`plan.md` §5.2): MQ-2 → A0, MQ-135 → A1, active buzzer → D8,
red LED → D9 (unwired), green LED → D10 (unwired). MQ modules are wired
to their analog (A0/A1) output, never the digital threshold pin, per the
project's own guidance that fusion needs a concentration value, not a
single bit.

---

## 9. Cost Breakdown

**Prototype hardware cost (Tier 1, required parts):**

| Item | Qty | Approx. cost (₹) |
|---|---|---|
| Arduino Uno R3 + USB-B cable | 1 | 500–700 |
| MQ-2 gas/smoke module | 2 | 160 |
| MQ-135 air quality module | 1 | 100 |
| DHT22 (AM2302) | 1 | 150 *(purchased but cut from the final build — see Section 8)* |
| Breadboard 830pt | 1 | 80 |
| Jumper wires (M-M, M-F) | 40 | 120 |
| Active buzzer 5V | 1 | 20 |
| LEDs + resistors | — | 30 |
| **Total** | | **≈ ₹1,200–1,400** |

**Recurring/real-cost software services:**

- **Twilio SMS** — real per-message cost on a trial account; used for
  informational alerts only. Flagged repeatedly in this project's own
  logs as a cost item to budget for beyond the prototype phase, and
  re-flagged here.
- **Groq** (`openai/gpt-oss-20b`) — free tier, 1,000 requests/day, used
  for alert message composition with a deterministic fallback.
- **Telegram Bot API, AWS S3 (CRITICAL-only upload), Overpass API** — free
  tier / no meaningful cost at prototype scale; S3 has an explicit
  session upload-count circuit breaker (`aws.max_uploads_per_session: 50`)
  as a cost-safety measure.

A projected production cost model (per-unit hardware cost at scale,
ongoing per-device SMS/cloud cost) was not compiled as part of this
report — it would need a target deployment volume assumption not yet
defined for this project.

---

## 10. Ethics and Safety

Simulated dispatch is a first-class design constraint, not an
afterthought (design change #1, Section 2):

- No code path in this system ever contacts a real emergency service.
  `agent/graph.py`'s dispatch is fully local — a JSON packet logged to
  `dispatch_log.jsonl` and, for CRITICAL incidents, archived to S3 for
  retraining/review purposes only.
- Every alert channel (Telegram, SMS) explicitly states that the system
  will not contact the fire station or emergency services, and the
  fire-station name/number included in alert text is **display-only** —
  it is sourced from a live Overpass lookup but is never an automated
  dial target under any circumstance.
- The only outbound real-world communication in this entire system is to
  the developer's own verified phone number (Telegram + Twilio), never to
  a third party.
- Training data containing identifiable people (webcam hard negatives,
  the held-out bright-wall clip) is disclosed here plainly, as required by
  the developer's own decision recorded during the v4 retrain — this data
  is not described as "clean" or "controlled" anywhere in this report.

---

## 11. Limitations

This section consolidates every known, honestly-reported weakness of the
system as built:

1. **Evaluation trial count.** Phase 11 ran 12 live trials, not the
   ≥20+≥20 specified in `info.md` §4.4, due to time constraints ahead of
   the deadline. See Section 7.1 for the full reasoning; this is a scope
   reduction, not a hidden shortfall.
2. **Total-darkness false positive (new, Section 7.3 Finding 1).**
   Unconfirmed root cause, unresolved — the single confirmed FAIL in the
   Phase 11 trial set.
3. **TV/laptop-fire bounded false positive.** A television or laptop
   screen showing fire footage reliably triggers vision-side WARNING
   (6 alarms on the standard adversarial clip on v4); bounded by fusion
   design so it can never reach CRITICAL without gas corroboration, but
   not eliminated at the model level. *Phase 13 lowered `votes_needed`
   from 5 to 3 for the slower ESP32-CAM stream, which reopened this; the
   developer re-ran it on the ESP32-CAM and reported it passing
   (Section 13.6 — count not yet recorded).*
4. **Steam sustained smoke-WATCH events.** Reduced from 21 (v3) to 5
   (v4) but not eliminated — steam remains a known, if much-improved,
   smoke false-positive source.
5. **Camera autofocus/exposure transients (Section 7.3 Finding 3).** Can
   occasionally sustain a false fire signal long enough to clear the
   temporal vote; observed twice during Phase 11 trials, both resolved by
   letting the camera settle rather than by a model/fusion fix.
6. **MQ-135 weak real-CO₂ sensitivity.** Noted from calibration; MQ-135
   is more reliably triggered by VOCs (e.g., alcohol/sanitizer, used as
   the calibration and trial stimulus) than by CO₂ specifically.
7. **People-in-frame training data.** Webcam hard negatives and the
   held-out validation clip include the developer and 1–3 other people
   in every inspected frame — kept and disclosed by deliberate developer
   decision, not incidental.
8. **DHT22 cut from scope entirely** — no temperature-rise signal exists
   in this build; `temp_spiking()` is a permanent stub returning `False`.
9. **GPS not used** — coordinates are hardcoded (design change #8);
   indoor GPS lock was never achievable.
10. **Twilio voice calling dropped from scope** — trial-tier accounts
    gate every call behind an interactive "press any key" prompt that
    defeats a one-way informational call; SMS remains fully in scope.
11. **Warm-up gate does not persist across process restarts** *(resolved
    in Phase 13: the sensor board now runs its own slope-based warm-up
    gate, which survives any host restart; the host timer applies only
    on the legacy-firmware fallback path)* — a
    tooling gap discovered while running Phase 11 trials (see Section
    12); each trial subprocess resets the 240-second gas warm-up timer
    from zero rather than tracking real elapsed sensor uptime. Not a
    production issue (a real deployment does not restart the process
    mid-operation), but it did require deliberately waiting out the gate
    on every gas-dependent trial during evaluation.

Phase 13 adds these (details in Section 13.7):

12. **ESP32-CAM IP is hardcoded** in `camera.stream_url` — the camera is
    a server and cannot use the sensor board's host discovery.
13. **GC2145 camera sensor.** The module shipped with a GC2145 clone
    sensor rather than the planned OV2640; its colour response differs
    from the webcam the model was trained around.
14. **Sensor-board movement sensitivity.** Moving the board causes
    reading jumps (cause unconfirmed). Mitigated by fixed mounting and
    the firmware's 3-of-5 vote, not engineered away.
15. **MQ-135 calibration delta trend.** The three stimulus runs behind
    `MQ135_CALIBRATED_DELTA` trended upward (485 → 566 → 665),
    suggesting incomplete recovery between exposures; the mean is used
    and the question is flagged unresolved.
16. **The cloud second opinion needs internet.** It is advisory, so
    losing it never affects detection.

---

## 12. Future Work

- **1D CNN on labelled sensor time-series** (design change #7) — replace
  the current threshold-plus-temporal-smoothing gas logic with a learned
  model, once enough labelled sequences exist.
- **Raspberry Pi port** (design change #4) — move off the laptop-as-edge-
  device architecture for a genuinely embeddable deployment.
- **Over-the-air model updates** — currently out of scope entirely;
  models are promoted by manual file copy.
- **GPS integration** — revisit once outdoor/near-window deployment is a
  target scenario where a satellite lock is achievable.
- ~~**Persist the gas warm-up timer across process restarts**~~ —
  resolved by Phase 13 (the board owns the gate). The original note,
  kept for the record: the tooling gap found in Section 11, item 11. Fixing it properly means
  writing `SensorReader`'s first-valid-reading timestamp somewhere
  durable (a small state file) rather than in-process memory, which
  touches the safety-critical edge loop and would need a full live
  FPS/buzzer re-verification pass before being trusted, per this
  project's own standing rule for any edge-loop change.
- **Dedicated darkness-adversarial testing.** Trial 12's total-darkness
  false positive (Section 7.3, Finding 1) was observed once, live, with
  a suspected but unconfirmed cause. A proper fix would need a dedicated
  low-light/near-black adversarial clip set, an eval sweep analogous to
  the existing threshold sweeps, and — if the hypothesis holds — targeted
  near-black hard negatives added to training, mirroring exactly the
  process that fixed the bright-wall smoke issue in v4.

---

## 13. Phase 13: Two-Board Migration

*Addendum, 24 September 2026. Every number in this section was measured
and is recorded in `logs.md` (Phase 13a–13h). Where the developer ran a
test and reported the outcome without supplying a number, the table says
so rather than filling one in (`info.md` §2.4).*

### 13.1 What changed and why

A faculty-suggested extension replaced the webcam + Arduino Uno with two
WiFi boards:

- **ESP32-CAM (camera board)** streams MJPEG. It serves one client at a
  time, so a relay in the dashboard backend holds that single connection
  and fans frames out to the edge loop and every dashboard viewer.
- **ESP32 DevKit (sensor board)** reads MQ-2/MQ-135, captures a fresh
  baseline every boot after a slope-based warm-up gate, derives WARN/DANGER
  from ratio thresholds, tracks slow drift, keeps absolute hard ceilings,
  and **sounds its own buzzer on its own verdict**. It POSTs one reading
  per second to an ingest server inside the edge loop, discovering the
  host by subnet scan so it moves between networks with no reflash.

The planned cloud inference was **not** adopted as the detector: local
ONNX inference stays primary, and the Lambda became an advisory second
opinion (13.4). The core claim survives and is stronger: the gas alarm
now needs neither WiFi nor the laptop.

### 13.2 Findings from the migration

| Finding | Measured |
|---|---|
| Gas detection was **silently dead** on the new firmware: the parser required exactly 2 CSV fields, the board sends 3 or 9 | Every line dropped; readings `None` forever while the process looked healthy |
| Host-side config thresholds vs the board's live values (same session) | MQ-2: clean air read 119, above config warn 115.57 → **continuous false alarm**. MQ-135: config warn 98.77 vs live warn 31.86 → **real gas never detected** |
| `votes_needed` on the ~7–8 fps ESP32-CAM stream (alarm / p_fire-hit ratio) | 0.13 at N=5 vs 1.09 at N=3 (webcam at N=5: 1.17) → production set to 3 |
| Camera relay fan-out | 3 simultaneous viewers each received 27 identical frames from exactly one upstream connection |
| Edge loop reading through the relay | 6.5 fps at 320×240, matching the board's native rate |
| WiFi killed mid-gas-alarm | Board buzzer kept sounding throughout; host degraded to `gas_high=False` and recovered |
| Dashboard threshold lines (Phase 13h) | Previous boot's thresholds shown after a board reboot, and config values shown during warm-up; fixed by carrying thresholds on every sample |

The fix for the second row: the board's `GAS_HIGH` state is now the gas
verdict. Config.yaml's gas values are a fallback for legacy firmware only.

### 13.3 Hardware (current)

| Item | Status |
|---|---|
| ESP32 DevKit sensor board | Working over WiFi on home network and phone hotspot; USB-free (phone-powered) operation verified |
| MQ-2 (GPIO34), MQ-135 (GPIO35) | Via 22k/10k dividers (5 V → 3.3 V ADC); thresholds computed per boot by firmware |
| Buzzer (GPIO33) | Driven by the board's own GAS_HIGH; verified sounding with WiFi down |
| AI-Thinker ESP32-CAM | Working through the relay; GC2145 sensor (not the planned OV2640) |
| Arduino Uno, webcam | Retired |
| DHT22 | Still cut from scope |

### 13.4 Cloud second opinion

On the rising edge of GAS_HIGH, the current frame goes to an AWS Lambda
(ap-south-1, IAM-signed Function URL) running the same v4 model. The
dashboard shows local and cloud side by side with an agree/disagree state.
It runs on a background thread after the local alarm and never feeds
fusion.

| Measurement | Result |
|---|---|
| `p_fire`, local vs Lambda, reference frame | 0.998336017131805 both — bit-identical (ORT 1.29 local vs 1.20.1 Lambda; worst deviation anywhere 3e-06) |
| Planned 5-crop MAX rule vs full frame (val, 150/class) | Full frame @0.30: recall 0.980, neutral FP 0.000. 5-crop MAX @0.30: recall 0.993, neutral FP 0.180 → **rule rejected**, crops kept as diagnostics |
| Pillow instead of OpenCV for resize | Verdict flipped on 8 of 400 frames (2%) → OpenCV kept |
| JPEG quality for the upload (300 val frames) | q80 1.0% verdict flips, q90 1.0%, q95 0.3% → q95 |
| Package size | 236.9 MB of the 250 MB limit |
| Latency | ~23 ms warm locally, 722 ms cold on Lambda |

Cost guards are client-side (rising edge, 60 s cooldown, 20 calls per
session) because the account's concurrency quota left no room to reserve
concurrency; it is off by default, and `scripts/deploy_lambda.py --delete`
removes every billed resource. Item B (S3-triggered re-scoring) was cut:
the archive holds no real CRITICAL snapshots to re-score.

### 13.5 Dashboard

Four tabs. The home page is fed by one 1 Hz WebSocket and shows, in
order: a status strip (live level, edge-feed age, board state, camera,
threshold source, last incident), the live camera with a relay-driven
LIVE/SIGNAL LOST overlay, per-sensor bullet bars against the board's
thresholds, a gas chart with a **hazard-index** view (each reading scaled
to its own sensor's thresholds: baseline 0, warn 1, danger 2) and a raw
view with step-traced thresholds, the nearest fire station, the cloud
second opinion, and incident history.

### 13.6 Re-verification on the two-board hardware

The developer ran these on 24 September 2026 and reported all passing.

| Test | Outcome | Numbers |
|---|---|---|
| Offline — WAN down | Reported pass | Not yet recorded |
| Offline — WiFi down | Reported pass | Not yet recorded |
| End-to-end latency | Reported pass | Not yet recorded |
| TV/laptop fire footage on the ESP32-CAM (bar ≤ 2 alarms) | Reported pass | Not yet recorded |
| Evaluation trials on two-board hardware | Reported pass | Not yet recorded |
| Phase 8b Telegram/Twilio drills | Reported pass | Not yet recorded |
| v4 textured-wall re-check | Reported pass | Not yet recorded |
| Airflow disturbance | Reported pass | Not yet recorded |
| Dashboard in a browser | Reported pass | Not yet recorded |

### 13.7 Not verified / open

- **Dashboard threshold fix on real hardware (Phase 13h):** built and
  checked against synthetic data only. The board-reboot check (warm-up
  shading, then new lines, never the previous boot's) is outstanding.
- Firmware was never compile-checked on the development machine
  (`arduino-cli` unavailable); both boards were flashed and ran.
- Lambda binaries were never executed locally (no Linux runtime); proven
  by the deploy itself.
- The CloudWatch "one invocation per gas event" check was not recorded.

