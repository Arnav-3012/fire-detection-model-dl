# logs.md — Build log

Project memory for FireWatch. Append-only record of what was actually built,
what was decided, and what was measured.

**Claude Code: read this file at the start of every session before writing code.**
It tells you what already exists and what state it is in. Update it at the end of
every phase using the format below, without being asked.

---

## Format

```markdown
## Phase N — <name>
**Date:** YYYY-MM-DD
**Status:** COMPLETE | PARTIAL | BLOCKED

### What was built
### Key decisions
### Measured results
### How to verify
### Open items
### Next phase
```

Rules: append never overwrite. Record failures and dead ends. Record every threshold
change with before, after, and effect. Real numbers only — write `NOT YET MEASURED`
rather than a placeholder.

---

## Project state at a glance

Update this table at the end of every phase. It is the fastest way to recover context.

| Phase | Name | Status | Date | Key result |
|---|---|---|---|---|
| 0 | Scaffold and config | COMPLETE | 2026-08-18 | Folder tree + config.yaml created, parses clean |
| 1 | Dataset preparation | NOT STARTED | — | — |
| 2 | Model training | NOT STARTED | — | — |
| 3 | Edge loop v1 | NOT STARTED | — | — |
| 4 | Temporal smoothing | NOT STARTED | — | — |
| 5 | Adversarial evaluation | NOT STARTED | — | — |
| 6 | Arduino and sensors | NOT STARTED | — | — |
| 7 | Fusion logic | NOT STARTED | — | — |
| 8 | Agent part 1 | NOT STARTED | — | — |
| 9 | Agent part 2 | NOT STARTED | — | — |
| 10 | Cloud | NOT STARTED | — | — |
| 11 | Dashboard and evaluation | NOT STARTED | — | — |
| 12 | Documentation | NOT STARTED | — | — |

---

## Live values

Single source of truth for measured values. Update as they are established.
Do not leave placeholders here — if not measured, say so.

| Value | Current | Set on | Source |
|---|---|---|---|
| Serial port | NOT SET | — | Arduino IDE, Tools → Port |
| MQ-2 baseline mean | NOT MEASURED | — | Day 6 calibration, 15 min ambient |
| MQ-2 baseline std | NOT MEASURED | — | Day 6 calibration |
| MQ-2 lighter peak | NOT MEASURED | — | Day 6 calibration |
| `mq2_warn` | PLACEHOLDER 300 | — | derived, plan.md §5.5 |
| `mq2_danger` | PLACEHOLDER 600 | — | derived, plan.md §5.5 |
| MQ-135 baseline | NOT MEASURED | — | Day 6 calibration |
| `frame_threshold` (τ) | 0.70 (initial) | — | plan.md §6.1 |
| `window` (M) | 8 (initial) | — | plan.md §6.1 |
| `votes_needed` (N) | 5 (initial) | — | plan.md §6.1 |
| Model val accuracy | NOT MEASURED | — | Day 2 |
| Model fire recall | NOT MEASURED | — | Day 2 |
| Inference FPS | NOT MEASURED | — | Day 4 |
| Hazard-to-buzzer latency | NOT MEASURED | — | Day 7 |
| Offline test | NOT RUN | — | Day 11 |

---

## Hardware status

| Item | Ordered | Received | Wired | Tested | Notes |
|---|---|---|---|---|---|
| Arduino Uno + USB-B | ☐ | ☐ | ☐ | ☐ | Blink test = tested |
| MQ-2 | ☐ | ☐ | ☐ | ☐ | **Log burn-in start time here** |
| MQ-135 | ☐ | ☐ | ☐ | ☐ | |
| DHT22 + 10kΩ | ☐ | ☐ | ☐ | ☐ | Pull-up required |
| Buzzer | ☐ | ☐ | ☐ | ☐ | Active, not passive |
| LEDs + 220Ω | ☐ | ☐ | ☐ | ☐ | |
| Breadboard + jumpers | ☐ | ☐ | — | — | M-F required |
| Webcam | ☐ | ☐ | — | ☐ | Laptop cam is fallback |

**MQ-2 burn-in started:** NOT STARTED
**MQ-2 burn-in valid from:** —

---

## Entries

<!-- Append new phase entries below this line. Newest at the bottom. -->

## Phase 0 — Project setup

**Date:** 2026-08-18
**Status:** PARTIAL

### What was built
- `plan.md` — full specification, 12-day schedule, hardware and software tracks
- `info.md` — operating rules and quality bars for Claude Code
- `logs.md` — this file

### Key decisions
- Laptop is the edge device for v1, not Raspberry Pi. Pi setup risks 2 days of the
  12 available and can fail outright. Pi listed as optional stretch only.
- Emergency dispatch is simulated, never real. Legal exposure under BNS §217 and no
  public dispatch API exists. Matches industry practice (Nest, ADT verify with a
  human before dispatch).
- Detection stays deterministic; the LLM is confined to message composition.
- Camera plus gas sensor fusion retained rather than camera-only — a camera cannot
  see a gas leak with no flame, which is the original report's primary scenario.
- 1D CNN on sensor time-series cut to future work. Insufficient time to collect
  labelled sensor sequences.

### Measured results
NOT YET MEASURED — no code or hardware yet.

### How to verify
`plan.md`, `info.md`, and `logs.md` present in repo root.

### Open items
- Hardware not yet ordered or requested from college lab
- MQ burn-in not started — **this is the critical path item**
- Repo not yet initialised
- D-Fire dataset not downloaded
- Telegram bot not created

### Next phase
Phase 0 completion: scaffold prompt from `plan.md` section 8, then environment
verification, then camera smoke test. All three are doable without hardware.

## Phase 0 — Scaffold and config

**Date:** 2026-08-18
**Status:** COMPLETE

### What was built
- Folder structure per `plan.md` §4.2: `arduino/`, `train/`, `models/`, `edge/`,
  `agent/`, `cloud/`, `dashboard/`, `eval/adversarial/`, `eval/calibration/`
- `__init__.py` in each Python package dir (`train/`, `edge/`, `agent/`, `cloud/`,
  `dashboard/`, `eval/`) — `models/` and `arduino/` excluded, they hold non-Python
  artifacts only
- `.gitignore` — covers `.env`, `models/`, `data/`, `__pycache__/`, `*.pyc`,
  `*.onnx`, `*.pt`, `eval/calibration/*.csv`
- `requirements.txt` — exact dependency list from `plan.md` §4.1
- `.env.example` — variable names from `plan.md` §4.1 (`ANTHROPIC_API_KEY`,
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`), all empty values
- `config.yaml` — full schema per `plan.md` §5.5/§6.1: `vision`, `sensors`,
  `fusion`, `location` sections. Confirmed valid YAML via `yaml.safe_load`

### Key decisions
- `AWS_DEFAULT_REGION` left empty in `.env.example` rather than pre-filled with
  `ap-south-1` (plan.md §4.1 shows it filled) — `.env.example` holds names with
  empty values per `info.md` §2.5 and the Day 0 task instruction; the real value
  belongs in `.env`, not committed as a default.
- `mq135_warn` threshold formula is not specified in plan.md §5.5 (only MQ-2's
  warn/danger formulas are given). Marked as a Day 6 placeholder to be derived
  analogously — flagged here rather than inventing a formula.
- No application logic written — camera, model, sensor, and fusion code are out
  of scope for this phase per the task constraints and `info.md` §3.4.

### Measured results
NOT YET MEASURED — scaffold only, no models or hardware involved.

### How to verify
```
find . -not -path './.git*' | sort
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))" && echo OK
```

### Open items
- Hardware not yet ordered or requested from college lab
- MQ burn-in not started — still the critical path item
- D-Fire dataset not downloaded
- Telegram bot not created
- `dependencies` in `requirements.txt` not yet installed/verified (Day 0 env
  verification step, per `info.md` §5, still pending)

### Next phase
Environment verification (`verify_env.py`, per `info.md` §5 testing table), then
Day 1 data prep per `plan.md` §8.
