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

**At the end of every phase, in the same step as this update: regenerate
`context.md` from scratch** (overwrite, not append) from the current state of
`plan.md`, `info.md`, and this file. `context.md` is a fast-recovery summary
only — never the source of truth — so it must never accumulate history of its
own; each regeneration replaces it entirely.

---

## Project state at a glance

Update this table at the end of every phase. It is the fastest way to recover context.

| Phase | Name | Status | Date | Key result |
|---|---|---|---|---|
| 0 | Scaffold and config | COMPLETE | 2026-08-18 | Folder tree + config.yaml created, parses clean |
| 1 | Dataset preparation | COMPLETE | 2026-08-18 | prepare_data.py run: train 18,464 (neutral 8,528 / smoke 4,987 / fire 4,949), val 3,258 (neutral 1,505 / smoke 880 / fire 873); 195 hard negatives folded into neutral across 6 categories; TV/laptop category (30) still not collected, carried forward |
| 2 | Model training | UNBLOCKED — ready to start | — | Unblocked by Phase 1 completion; `data/train/`, `data/val/` ready as input to `train/train_classifier.py` |
| 3 | Edge loop v1 | NOT STARTED | — | — |
| 4 | Temporal smoothing | NOT STARTED | — | — |
| 5 | Adversarial evaluation | NOT STARTED | — | — |
| 6 | Arduino and sensors | NOT STARTED | — | DHT22 out of scope for the Arduino sketch (cut, see Phase 0g) |
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
| Arduino Uno + USB-B | ☑ | ☑ | ☐ | ☐ | From library, not yet wired or blink-tested |
| MQ-2 | ☑ | ☑ | ☐ | ☐ | In hand, not yet wired — burn-in has not started |
| MQ-135 | ☑ | ☐ | ☐ | ☐ | Ordered, arriving ~20 Aug |
| DHT22 | — | — | — | — | CUT from project, see decision below |
| Buzzer | ☑ | ☐ | ☐ | ☐ | Ordered, arriving ~24 Aug |
| LEDs + resistors | ☑ | ☐ | ☐ | ☐ | Ordered as part of breadboard kit, arriving ~24 Aug |
| Breadboard + jumpers | ☑ | ☐ | — | — | Ordered, arriving ~20 Aug |
| Webcam | — | — | — | ☑ | Using MacBook built-in instead |

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

## Phase 0b — Provider swap: Anthropic to Groq

**Date:** 2026-08-18
**Status:** COMPLETE

### What was built
- `plan.md` — §4.1 `requirements.txt` block: `anthropic` → `groq`; §4.1 `.env`
  block: `ANTHROPIC_API_KEY=` → `GROQ_API_KEY=`; §4.3 tool choices table: "LLM in
  agent" row now "Groq (llama-3.1-8b-instant) via `groq` SDK"; §8 Day 9 prompt:
  "call Claude via the anthropic SDK" → "call Groq via the groq SDK, using the
  llama-3.1-8b-instant model"
- `info.md` — §2.3: "The LLM (Claude via the anthropic SDK)" → "The LLM (Groq,
  llama-3.1-8b-instant)"; §3.2 failure table: "Anthropic API" row → "Groq API",
  fallback behaviour unchanged (deterministic template, continue)
- `.env.example` — `ANTHROPIC_API_KEY=` → `GROQ_API_KEY=`
- `requirements.txt` — `anthropic` → `groq`

### Key decisions
- Switched the compose-node LLM from Claude/`anthropic` SDK to Groq/
  `llama-3.1-8b-instant`. Reason: Groq's free tier is sufficient for this
  project's expected call volume (roughly 20-40 calls total across build and
  demo), and speed matters for the verify → compose → notify latency chain.
- No change to architecture or fallback requirements: the LLM still composes
  alert text only (`info.md` §2.3), and the deterministic template fallback on
  API failure is unchanged.
- No code changed in `agent/graph.py` or `agent/tools.py` — neither file exists
  yet (only `agent/__init__.py` is present). Agent code is scheduled for Day 9
  per `plan.md` §8; this phase is plan/config only.

### Measured results
NOT YET MEASURED — no LLM calls made yet, provider swap is documentation/config
only at this point.

### How to verify
```
grep -n "groq\|anthropic" requirements.txt .env.example
grep -n "Groq\|Anthropic" info.md plan.md
```
`groq`/`Groq` should appear in all files; `anthropic`/`Anthropic` should not.

### Open items
- `groq` package not yet installed (requirements.txt not yet installed per
  Phase 0 open items)
- `GROQ_API_KEY` not yet obtained or set in local `.env`
- Agent code (`agent/graph.py`, `agent/tools.py`) still not started — Day 9 per
  schedule

### Next phase
Unchanged: environment verification (`verify_env.py`), then Day 1 data prep per
`plan.md` §8.

## Phase 0c — Project environment created

**Date:** 2026-08-18
**Status:** PARTIAL

### What was built
- Conda environment `firewatch`, Python 3.11.15 (matches `plan.md` §4.1 pin:
  3.10/3.11, not 3.12) — created at `/opt/anaconda3/envs/firewatch`
- All packages from `requirements.txt` installed into it and confirmed present:
  `torch`, `torchvision`, `onnx`, `onnxruntime`, `opencv-python`, `numpy`,
  `pandas`, `pyserial`, `fastapi`, `uvicorn`, `langgraph`, `langchain-core`,
  `groq`, `boto3`, `paho-mqtt`, `streamlit`, `python-dotenv`, `pyyaml`,
  `requests`

### Key decisions
- Used conda rather than venv, to match the developer's existing conda workflow
  (`base` and `ssdivenv` environments already present on the machine).

### Measured results
NOT YET MEASURED — environment created and populated, but `verify_env.py` has
not been run yet, so pass/fail per `info.md` §5 is still unconfirmed.

### How to verify
```
conda env list | grep firewatch
conda run -n firewatch python --version
conda run -n firewatch pip list
```

### Open items
- `anthropic` package (0.122.0) is still installed in the `firewatch` env from
  before the Phase 0b provider swap — it is no longer in `requirements.txt`.
  Harmless (unused, not imported by any code yet) but should be removed for
  cleanliness: `conda run -n firewatch pip uninstall anthropic -y`
- `.env` has not been created — only `.env.example` exists. `GROQ_API_KEY`,
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and AWS credentials are all still
  unset. Real values must be filled in before any Day 9 agent call or Day 10
  cloud upload can work.

### Next phase
Day 1 data prep per `plan.md` §8.

## Phase 0d — verify_env.py written and passed

**Date:** 2026-08-18
**Status:** COMPLETE

### What was built
- `verify_env.py` — checks Python version is 3.10 or 3.11, imports every
  package listed in `requirements.txt` (mapped to actual import names where
  they differ, e.g. `opencv-python` → `cv2`, `pyserial` → `serial`,
  `paho-mqtt` → `paho.mqtt.client`, `python-dotenv` → `dotenv`,
  `pyyaml` → `yaml`), and confirms `config.yaml` parses. Prints `[PASS]`/
  `[FAIL]` per check and `ALL PASS` or a failure line at the end. Exit code 0
  on pass, 1 on any failure.

### Key decisions
- Import-name mapping built as an explicit dict rather than guessed
  string transforms — several `requirements.txt` names do not derive from
  their PyPI name mechanically (`opencv-python`, `pyserial`, `paho-mqtt`,
  `python-dotenv`), so a naive transform would false-fail.

### Measured results
```
conda run -n firewatch python verify_env.py
```
All 19 packages PASS, Python 3.11 PASS, config.yaml PASS. `ALL PASS`.
This satisfies the Phase 0c open item and the `info.md` §5 "Environment"
row ("`verify_env.py` prints all-pass").

### How to verify
```
conda run -n firewatch python verify_env.py
```
Expect `ALL PASS` and exit code 0.

### Open items
None for this phase. Carried over from Phase 0c: leftover `anthropic`
package, and `.env` not yet created with real credentials.

### Next phase
Day 1 data prep per `plan.md` §8.

## Phase 0f — Camera smoke test (scripts/test_camera.py)

**Date:** 2026-08-18
**Status:** COMPLETE

### What was built
- `scripts/test_camera.py` — throwaway diagnostic, explicitly not part of the
  edge module. Opens the default webcam (`cv2.VideoCapture(0)`), displays the
  live feed with a rolling FPS counter drawn on each frame, exits on 'q'. If
  the camera fails to open, prints a clear error naming the three likely
  causes: another app holding the camera, OS camera permission not granted,
  or wrong device index.

### Key decisions
- Kept entirely out of `edge/` — `edge/camera.py` is scheduled for Day 3 per
  `plan.md` §8 and `info.md` §3.4 (scope discipline: build only what the
  current phase asks for). This script duplicates none of that future
  module's structure (no `Camera` class, no `encode_jpeg`) so there is
  nothing to reconcile or throw away later.
- Device index left as a hardcoded module-level constant (`DEVICE_INDEX = 0`)
  rather than a CLI arg or config.yaml entry — this is a one-off manual smoke
  test run by a human at the terminal, not application code, so it is exempt
  from the "no magic numbers" rule in `info.md` §3.1 (which governs
  `edge/`/`agent/`/`cloud/` etc., not `scripts/`).

### Measured results
Developer ran the script and confirmed visually: camera opens (device index
0, default laptop webcam), live feed displays, FPS counter renders, 'q'
closes the window cleanly. No numeric FPS value was recorded — this test
only confirms the camera path works, not a throughput measurement. Exact
FPS on this hardware remains NOT YET MEASURED (that measurement belongs to
Day 4 per `plan.md` §8, against the real inference loop, not this diagnostic).

### How to verify
```
conda run -n firewatch python scripts/test_camera.py
```
Expect a window showing the live webcam feed with "FPS: NN.N" drawn in green
top-left, updating every frame. Press 'q' to close. If no camera is available,
expect the `[ERROR]` message with the three likely causes instead of a crash.
**Confirmed working on developer's machine, 2026-08-18.**

### Open items
None for this phase. Carried over: leftover `anthropic` package, `.env` not
yet created with real credentials, `setup.sh`/`setup.ps1` not run end-to-end.

### Next phase
Day 1 data prep per `plan.md` §8. (Day 3 remains the scheduled slot for
`edge/camera.py` and `edge/vision.py`.)

## Phase 0e — Portable setup scripts and scripts/verify_env.py

**Date:** 2026-08-18
**Status:** COMPLETE

### What was built
- `setup.sh` — Mac/Linux setup script. Requires `python3.11` on PATH, creates
  `.venv/`, upgrades pip, installs `requirements.txt`. Exits with an error if
  `python3.11` is not found rather than silently falling back to another
  version (plan.md §4.1 pins 3.10/3.11, not 3.12).
- `setup.ps1` — Windows equivalent. Uses the `py -3.11` launcher (or
  `$env:PYTHON_BIN` override), same venv-create-and-install flow.
- `scripts/verify_env.py` — supersedes the root-level `verify_env.py` from
  Phase 0d (which is deleted). Imports every dependency from
  `requirements.txt` (same PyPI-name → import-name mapping as before) and
  prints a formatted PASS/FAIL table with per-package version, instead of the
  old line-by-line output. Exits 1 if anything fails, 0 on all-pass.

### Key decisions
- `setup.sh`/`setup.ps1` build a **venv**, not a conda env, even though the
  working `firewatch` conda env from Phase 0c/0d already exists and remains
  in daily use. Reason (confirmed with developer): these scripts are for
  reproducibility on a machine that may not have conda — a grader or a fresh
  checkout — not a replacement for the existing conda workflow. Developer
  chose to keep them as venv scripts rather than skip them or rewrite for
  conda.
- Old root-level `verify_env.py` (Phase 0d) deleted rather than kept alongside
  the new one, to avoid two diverging copies of the same check. The new
  `scripts/verify_env.py` is the single source of truth going forward.
- `setup.sh` was not executed end-to-end in this phase (developer paused the
  dry-run once it was clear the conda env already satisfies the same need) —
  syntax-checked with `bash -n` only. `scripts/verify_env.py`'s table output
  was run and confirmed working against the existing `firewatch` conda env.

### Measured results
```
conda run -n firewatch python scripts/verify_env.py
```
All 19 packages + python + config.yaml PASS in table form. `ALL PASS`.
`setup.sh` itself: syntax-checked only (`bash -n setup.sh`), not executed —
NOT YET MEASURED end-to-end (no venv actually created from it in this repo).

### How to verify
```
bash setup.sh          # Mac/Linux — creates .venv, installs requirements.txt
# or on Windows: .\setup.ps1
python scripts/verify_env.py
```
Per `info.md` §5, this is the exact command sequence to confirm the
environment before starting real work.

### Open items
- `setup.sh`/`setup.ps1` not yet run end-to-end by the developer — only
  syntax-checked. If a venv is ever created from them, confirm it installs
  cleanly on a real machine before relying on it for grading/handoff.
- Same carryover as Phase 0c: leftover `anthropic` package in the conda env,
  and `.env` not yet created with real credentials.

### Next phase
Day 1 data prep per `plan.md` §8.

## Phase 0g — DHT22 cut from project

**Date:** 2026-08-18
**Status:** COMPLETE

### What was built
Documentation only. No application or Arduino code touched.
- `logs.md` — Hardware status table corrected (this entry's parent edit): ordered/received/wired/tested state fixed for all components, DHT22 row replaced with a cut notice, Webcam row corrected to reflect MacBook built-in camera use.
- `plan.md` §5.2 — DHT22 row removed from the Arduino Uno pin map table; a one-line note added directly under the table pointing here for the open fusion-rule item.

### Key decisions
- **DHT22 is cut from the project.** Reason: cost, and it was not available from the college library — would have required purchase on top of an already-ordered component list, and budget did not support adding it.
- This removes temperature/humidity sensing entirely: no `temp_rate` signal, and no humidity correction for MQ drift.
- `plan.md` §5.2 listed DHT22 on D2 with a 10kΩ pull-up — this was stale and has been corrected in this same pass (row removed, note added).
- `plan.md` §5.5 (MQ calibration) referenced DHT22 for temperature-humidity correction of MQ readings. This correction is no longer available — **documented limitation**, not resolved here.
- The fusion table in `plan.md` §8 Day 7 prompt (`fuse()` function, rule 2: "fire AND temp_spiking -> CRITICAL") depends on DHT22 for `temp_spiking`. **This rule is now broken by the cut.** Not resolved in this pass — see Open items below. `plan.md` §8 text itself was left untouched per explicit instruction; it will be corrected once the fusion-rule question is resolved in a planning session.
- H7 (DHT22 wiring) and its test step in `plan.md` §5.3 are no longer applicable, since the component is cut — no build order renumbering was done in this pass (out of scope; `plan.md` §5.3 was not touched).

### Measured results
N/A — documentation-only pass, no code or measurements involved.

### How to verify
```
grep -n "DHT22" plan.md logs.md
```
`plan.md` §5.2 should show no DHT22 row in the pin table, only the note below it. `logs.md` Hardware status table should show DHT22 as cut, not as an unordered item.

### Open items
- **BLOCKING Day 7 fusion work.** `plan.md` §8 Day 7 prompt rule 2 ("fire AND temp_spiking -> CRITICAL") has no data source now that DHT22 is cut. Needs a decision in a planning session before Day 7: drop the rule, replace `temp_spiking` with a different signal, or fold it into another rule. **Not urgent today — do not decide now.**
- `plan.md` §5.5 MQ calibration's humidity/temperature correction of MQ drift is unavailable — carry forward as a documented limitation in the eventual report (`info.md` §4.4 / Appendix C).
- `plan.md` §5.3 build order (H7 and its test) still references DHT22 — not renumbered or edited in this pass, since item 3 of today's task scoped the plan.md edit to §5.2 only.

### Next phase
Day 1 data prep per `plan.md` §7/§8, software-only (see sequencing note below).

## Phase 0h — Today's sequencing decision: software-first

**Date:** 2026-08-18
**Status:** COMPLETE

### What was built
Documentation only — this entry records a scheduling decision, not a build.

### Key decisions
- As of today's session, all physical hardware wiring and testing (Arduino blink test, MQ-2 burn-in start, the H1–H9 build steps in `plan.md` §5.3) is **deferred to a later session**.
- Today's work is software-only: Day 1 dataset preparation per `plan.md` §7/§8.
- This is a **deliberate sequencing choice, not a blocker**. MQ burn-in takes 24–48h regardless of when it starts, so doing software work first avoids idle time later waiting on burn-in to complete.
- No hardware status fields change as a result of this deferral — all remain exactly as corrected in Phase 0g.

### Measured results
N/A — scheduling decision only.

### How to verify
Compare `logs.md` Hardware status table before/after this session: no wired/tested checkboxes flipped as part of this entry.

### Open items
None new. Carries forward the Phase 0g blocking item (Day 7 fusion rule) and all prior open items (hardware not yet wired, MQ burn-in not started, `.env` not populated, leftover `anthropic` package).

### Next phase
Day 1 data prep per `plan.md` §8.

## Phase 1 — Data collection (D-Fire clone + hard negatives)

**Date:** 2026-08-18
**Status:** PARTIAL

### What was built
- `data/dfire_raw/` — initially cloned from `https://github.com/gaiasd/DFireDataset.git` (code/docs only); this session, the real dataset (images + YOLO labels + `data.yaml`) downloaded on top of it via `kaggle datasets download -d sayedgamal99/smoke-fire-detection-yolo -p data/dfire_raw --unzip`
- `scripts/fetch_hard_negatives.py` — one-time data collection utility, downloads hard-negative images via DuckDuckGo image search (`ddgs` package). Hardcoded category dict (6 of plan.md §6.4's 7 categories), per-category subfolder output under `data/hard_negatives/<category>/`, PIL validation before saving, `--category` retry flag, summary table on completion.
- `requirements.txt` — added `ddgs`; this session, added `kaggle`
- `data/hard_negatives/` — real downloaded images, 6 subfolders (see Measured results)
- `~/.kaggle/access_token` — Kaggle CLI credential, placed by the developer (not by Claude Code) between sessions; confirmed working via `kaggle datasets list -s fire` before any download was attempted

### Key decisions
- **D-Fire dataset structure differs from what was expected.** The cloned GitHub repo (`gaiasd/DFireDataset`) contains only `README.md`, `LICENSE`, `figures/`, and `utils/utils.py` (YOLO↔pixel coordinate conversion helpers). It does **not** contain the actual images or label files. Per the repo's own README, the real dataset (images + YOLO-format annotations, pre-split train/val/test) is hosted externally on OneDrive links, with a Kaggle mirror also linked (`sayedgamal99/smoke-fire-detection-yolo`). This is the actual, current distribution method for D-Fire — not an error in the clone.
- **class_id 0=smoke / 1=fire could NOT be confirmed against this clone.** The repo's `utils/utils.py` only has coordinate-conversion functions (`pixel2yolo`, `yolo2pixel`), no class-ID mapping constant. The README states annotations are in YOLO format but does not spell out which numeric class ID maps to which label. This must be confirmed from whichever actual source (OneDrive dataset zip or the Kaggle mirror) is used to obtain the real files, in the next session, before `train/prepare_data.py` is written. Do not assume 0=smoke/1=fire without checking the real label files or an explicit `classes.txt`/`data.yaml` that ships with them.
- **Decision (this session): use the Kaggle mirror instead of the OneDrive link.** `sayedgamal99/smoke-fire-detection-yolo` chosen over D-Fire's README OneDrive links, for automation and speed — the Kaggle CLI (`kaggle datasets download`) is scriptable end-to-end with an API token, while the OneDrive links require a manual, unauthenticated browser download with no way to verify programmatically. `kaggle` package added to `requirements.txt`. CLI confirmed installed and authenticated (`kaggle datasets list -s fire` returned real results, including this exact dataset ref, size ~3.05GB, usability 1.0) before any download was attempted, per the explicit instruction not to proceed on an unconfirmed credential.
- **DuckDuckGo package swap: `duckduckgo_search` → `ddgs`.** `pip install duckduckgo_search` succeeds but the package itself is deprecated — importing it prints "this package has been renamed to `ddgs`, use `pip install ddgs` instead" — and a live test query against it immediately hit `RatelimitException: 403 Ratelimit`. This was flagged to the developer before proceeding (per the task's explicit instruction not to silently retry a different approach). The developer confirmed switching to `ddgs`, which is the same maintainer's current package name, identical API (`from ddgs import DDGS; DDGS().images(...)`) — not a different search method. `requirements.txt` now lists `ddgs`, not `duckduckgo_search`.
- **Pixabay was the originally planned source, replaced with DuckDuckGo-based scraping.** Reason: Pixabay's API gates hi-res image downloads behind a 24-hour manual approval step, which does not fit this project's timeline. No `PIXABAY_API_KEY` was found in `.env.example` to remove — it was never added in a prior session, so no cleanup was needed there.
- TV/laptop fire-footage category (30 images, plan.md §6.4) deliberately excluded from the script — not a natural photography subject, needs manual screenshot collection. Flagged in the script's docstring and console output.

### Measured results
D-Fire (Kaggle mirror `sayedgamal99/smoke-fire-detection-yolo`), downloaded and unzipped into `data/dfire_raw/` via `kaggle datasets download -d sayedgamal99/smoke-fire-detection-yolo -p data/dfire_raw --unzip`:

**Actual structure found** (differs from plan.md's assumed train/test-only layout — this mirror ships three splits):
```
data/dfire_raw/
├── data.yaml            <- class mapping, see below
├── data/
│   ├── train/images/  (14,122 files)
│   ├── train/labels/  (14,122 files)
│   ├── val/images/    (3,099 files)
│   ├── val/labels/    (3,099 files)
│   ├── test/images/   (4,306 files)
│   └── test/labels/   (4,306 files)
├── README.md            <- from the original GitHub clone (Phase 1 first entry), unrelated to this Kaggle download
├── LICENSE               <- ditto
├── figures/              <- ditto
└── utils/utils.py        <- ditto
```
Note: the Kaggle zip was extracted into the same `data/dfire_raw/` directory the GitHub clone previously populated (`-p data/dfire_raw` was the specified destination). Nothing was overwritten — the GitHub clone had no `data/` subfolder to collide with — but `dfire_raw/` is now a merge of two sources: the original repo's docs/utils (from the earlier clone) and this Kaggle mirror's actual images/labels/`data.yaml`. Total image data: 3.0GB.

**Class mapping — RESOLVED.** `data/dfire_raw/data.yaml` contains:
```yaml
names: ['smoke', 'fire']
nc: 2
```
This confirms **class_id 0 = smoke, class_id 1 = fire** — matching the original assumption from plan.md, but now from an authoritative source rather than a guess. Verified against real label content, not just metadata: a sample of `data/train/labels/*.txt` shows both class IDs in use (7,794 lines starting `0`, 9,638 lines starting `1` in the sampled set) in YOLO format (`class_id x_center y_center width height`, normalized 0–1) — e.g. `1 0.2162... 0.7391... 0.1369... 0.1505...` (a fire box) and `0 0.7672... 0.2889... 0.0368... 0.0546...` (a smoke box). Also confirmed 6,458 empty label files in `train/labels/` alone (valid YOLO convention — zero boxes means no fire/smoke detected in that image), consistent with the original D-Fire README's documented "None: 9,838 images" category — corroborating this is genuinely the same underlying dataset, just properly pre-split.

Hard negatives, real per-category counts from the actual run (unchanged from prior session, included here for completeness):

| Category | Requested | Downloaded | Failed |
|---|---|---|---|
| sunset_window | 50 | 28 | 7 |
| red_orange_objects | 40 | 33 | 2 |
| warm_lights | 50 | 35 | 0 |
| steam | 50 | 23 | 12 |
| car_lights_night | 30 | 29 | 6 |
| stove_cooking | 50 | 30 | 5 |
| **Total** | **270** | **178** | **32** |

178/270 (66%) of target reached in this run. Categories fell short of target because the search endpoint returned fewer unique candidate URLs than needed once failed downloads (mostly `403 Forbidden` from hotlink-protected stock photo sites, a few timeouts) were filtered out — `CANDIDATE_MULTIPLIER = 4` in the script was insufficient headroom for some queries. Failed downloads themselves are expected and handled (skipped and logged, not crashed) — the shortfall is candidate exhaustion, not a script defect. Verified saved files are real, valid images (checked file sizes and one sample folder — `warm_lights/`, 35 files, 6.9MB, mixed .jpg/.png/.webp).

### How to verify
```
kaggle datasets list -s fire | grep sayedgamal99
find data/dfire_raw -type d -not -path '*/.git*'
cat data/dfire_raw/data.yaml
for d in data/hard_negatives/*/; do echo "$d: $(ls "$d" | wc -l)"; done
```

### Open items
- ~~D-Fire actual images/labels not yet obtained~~ **RESOLVED this session** — downloaded via Kaggle CLI, 21,527 total labelled images across train/val/test.
- ~~class_id → class_name mapping for D-Fire not confirmed~~ **RESOLVED this session** — `data/dfire_raw/data.yaml` confirms `names: ['smoke', 'fire']` (0=smoke, 1=fire), cross-checked against real label file contents.
- **`train/prepare_data.py` is now UNBLOCKED** on the D-Fire side. It still needs to decide how to fold the three D-Fire splits (train/val/test) together with plan.md §8's specified 85/15 stratified split — plan.md's Day 1 prompt describes producing `train/`/`val/` from "a raw D-Fire download directory" assuming one undifferentiated pool, not a dataset that already ships three splits. Not resolved in this session (no training/split logic per this session's scope) — flag for the next session before writing `prepare_data.py`.
- `dfire_raw/` now mixes two sources under one directory (original GitHub clone's docs/utils + this Kaggle mirror's data/data.yaml) — harmless since nothing collided, but worth knowing if the folder looks unexpected later.
- Hard negatives short of target in all 6 categories (see Measured results table) — 92 images short of the 270 target. Retry with `python scripts/fetch_hard_negatives.py --category <name>` per category, ideally after raising `CANDIDATE_MULTIPLIER` or waiting (some shortfall was hotlink-protected sources that will likely fail again).
- TV/laptop fire-footage category (30 images) — manual screenshot collection still required, not started.
- Hard negatives are stock/scraped images, not self-shot photos as plan.md §6.4 originally specified ("shoot ~300 photos personally"). **This is a documented limitation**, distinct from the plan's original intent — record in the eventual report (`info.md` Appendix C checklist) as a deviation with reasoning (Pixabay's 24h gate, timeline pressure).
- Per-category subfolder output structure (`data/hard_negatives/<category>/`) is a known dependency for `train/prepare_data.py` in the next session — it must walk the `--extra-negatives` directory recursively, not expect a flat directory. Not resolved in this session, per task scope (no training/split logic this session).

### Next phase
`train/prepare_data.py` per `plan.md` §8 Day 1 prompt — unblocked on D-Fire data availability and class mapping. Still needs (a) a decision on how to handle D-Fire's pre-existing train/val/test splits against the plan's 85/15 stratified-split instruction, and (b) the developer's manual hard-negative review pass (see addendum below) before hard-negative counts can be treated as final.

### Addendum — manual review tool built
- `scripts/review_hard_negatives.py` — one-time Streamlit app (no new dependency, `streamlit` already in `requirements.txt` for Day 11) letting the developer visually approve/reject each downloaded hard-negative image. Built because the `ddgs` scrape in `scripts/fetch_hard_negatives.py` matches on keywords, not visual content — a known example: a commercial steam-kettle product photo landed in the `steam` category despite showing no actual vapor.
- Walks all 6 categories under `data/hard_negatives/`, one image at a time (`width="stretch"`, not a thumbnail), category + filename shown above it. "Keep" advances with no file operation. "Reject" moves the file to `data/hard_negatives_rejected/<category>/` — preserved, not deleted, in case a call needs reversing or rejects are useful later. Sidebar lets the developer jump to any category non-linearly (e.g. `steam` first, the known problem category). Per-category running kept/rejected count shown, and a completion summary once a category is fully reviewed.
- Progress persists across restarts via `data/hard_negatives_review_state.json` (gitignored — falls under the existing blanket `data/` rule in `.gitignore`, no new ignore entry needed) — a filename → "kept"/"rejected" map, so re-opening the app does not force re-review of already-decided images.
- **Not yet run.** This needs the developer's own eyes; not something to execute on their behalf. Launch with: `streamlit run scripts/review_hard_negatives.py`

### Open items (addendum)
- **`train/prepare_data.py` should NOT be finalized against the current hard-negative counts (178/270) until this manual review pass is done.** Some fraction of those 178 are expected to be rejected as keyword-matched-but-visually-wrong (the `steam` category, 23 downloaded, is the suspected worst offender per the example above) — the real usable count per category is unknown until the developer runs the review tool. Treat the Measured results counts above as pre-review, not final.
- Rejected images are moved (not copied) out of `data/hard_negatives/<category>/`, so `prepare_data.py`'s recursive walk of that directory in the next session will only see what survived review — this is intentional, not a bug to reconcile.

### Addendum 2 — review completed, two categories topped up, one bug found and fixed

**Developer completed the manual review pass.** First-pass results confirmed the suspected `steam` problem and also surfaced a second weak category:

| Category | Downloaded | Kept | Rejected | Reject rate |
|---|---|---|---|---|
| steam | 23 | 4 | 19 | 83% |
| red_orange_objects | 33 | 18 | 15 | 45% |
| car_lights_night | 29 | 29 | 0 | 0% |
| stove_cooking | 30 | 30 (29 decided + 1 leftover) | 0 | 0% |
| sunset_window | 28 | 28 | 0 | 0% |
| warm_lights | 35 | 35 | 0 | 0% |

4 usable `steam` images is not enough to be a meaningful hard-negative class. Developer chose to retry `steam` and `red_orange_objects` with sharpened search queries rather than accept the shortfall (per `info.md` §7, this was a judgment call put to the developer, not made silently).

**Query changes in `scripts/fetch_hard_negatives.py`:**
- `steam`: `"steam kettle kitchen bathroom"` → `"boiling kettle steam vapor rising closeup"` (old query mostly returned commercial kettle product photos with no visible vapor)
- `red_orange_objects`: `"red cushion sofa orange jacket indoor"` → `"red orange cushion pillow blanket closeup indoor"`
- `CANDIDATE_MULTIPLIER` raised 4 → 8 globally, since the first run's shortfall was partly download failures (mostly `403` from hotlink-protected sources), independent of the query-wording problem.

**Bug found and fixed during the retry: filename collision / silent overwrite.** The original script always numbered downloads starting at `{category}_000`, with no check for files already in the output directory. Re-running `--category steam` after the review pass had already reduced that folder to 4 files **overwrote 3 of those 4 already-approved images** with new, unreviewed downloads (same filename, different content) — only `steam_001.jpeg` survived, and only because the new run's index-1 candidate happened to save with a different extension (`.jpg` vs `.jpeg`), avoiding a literal clash. Caught by comparing file mtimes before/after. Flagged to the developer immediately rather than proceeding to the second retry with the same latent bug.

**Fix:** added `next_free_index()` to `scripts/fetch_hard_negatives.py` — scans the output directory for existing `{category}_NNN.*` files and resumes numbering from the highest index + 1, instead of always starting at 0. Verified against the already-damaged `steam` folder (correctly resumed at 35) and confirmed protective on the `red_orange_objects` retry, run afterward — all 18 previously-approved files checked byte-for-byte present post-retry, no losses.

Also manually corrected `data/hard_negatives_review_state.json` to drop the 22 stale `steam/*` entries (indices 0–22, both kept and rejected) that no longer pointed at the images they were originally recorded against, keeping only `steam/steam_001.jpeg: kept` — the one entry confirmed by mtime to be untouched. This let the review app correctly treat the 35 new steam downloads as unreviewed rather than skipping them as already-decided.

**Damage from the bug:** 3 specific developer-approved `steam` images (previously `steam_000.jpg`, `steam_003.jpg`, `steam_019.jpg`) are permanently gone — overwritten before the fix was written. No other category was affected; `red_orange_objects`'s retry ran after the fix and lost nothing.

**Final counts after retry + second review pass**, per `data/hard_negatives_review_state.json` and on-disk file counts (which agree):

| Category | Kept (final, usable) | Rejected (session total) |
|---|---|---|
| car_lights_night | 29 | 0 |
| red_orange_objects | 37 | 30 |
| steam | 36 | 19 (pre-fix; not reflected in current state file, see note below) |
| stove_cooking | 30 | 0 |
| sunset_window | 28 | 0 |
| warm_lights | 35 | 0 |
| **Total kept** | **195** | — |

Note: `hard_negatives_rejected/steam/` still physically contains 19 files from the original (pre-retry) review pass — those moves happened before the state-file cleanup, so the files are correctly parked there even though their JSON entries were removed. This is harmless: `prepare_data.py` only reads `data/hard_negatives/`, not the rejected folder.

195 kept vs. the original plan.md §6.4 target of 270 (across these 6 categories, i.e. excluding the 30-image TV/laptop category) — **72% of target**, a large improvement over the pre-review raw download count but still short. This is being accepted as sufficient to proceed rather than doing a third retry round — flagged as a documented shortfall for the report, not silently treated as if the target was hit.

### Open items (addendum 2)
- **RESOLVED**: hard-negative counts are now final and review-clean. `train/prepare_data.py` can be written against these numbers (195 total across 6 categories, plus the still-outstanding 30-image TV/laptop category requiring manual screenshot collection, unchanged from earlier).
- 3 originally-approved `steam` images were lost to the overwrite bug before the fix — acceptable, since the retry replaced them with a much larger, better-matching set (36 kept vs. the original 4), but noted here for completeness per `info.md` §6 ("record failures and dead ends too").
- `next_free_index()` fix in `scripts/fetch_hard_negatives.py` is now permanent — any future re-run of `--category <name>` against a non-empty folder is safe.
- Still open, unchanged from Addendum 1: TV/laptop fire-footage category (30 images) needs manual screenshot collection, not started.

### Next phase (updated)
`train/prepare_data.py` per `plan.md` §8 Day 1 prompt. Hard-negative counts are now final (195 kept, reviewed). Still needs a decision on how to handle D-Fire's pre-existing train/val/test splits against the plan's 85/15 stratified-split instruction before writing code (unresolved, carried over from Addendum 1).

### Addendum 3 — prepare_data.py written and run, Phase 1 COMPLETE

**Date:** 2026-08-18

### What was built
- `train/prepare_data.py` — pools D-Fire's train/val/test splits, derives an image-level label from each YOLO label file (no label or empty -> neutral, class 0 only -> smoke, class 1 present -> fire, priority to fire when both appear), recursively walks `data/hard_negatives/` into `neutral`, stratifies an 85/15 train/val split by class (seed 42), physically copies files into `data/train/<class>/` and `data/val/<class>/`, prints a class balance table plus a hard-negative per-category breakdown, and saves a bar chart.
- `train/data_report.py` — `print_balance_table()` and `save_balance_chart()`, split out of `prepare_data.py` to keep it near the ~200-line guideline (info.md §3.3).
- `eval/class_balance.png` — grouped bar chart, train vs val per class.
- `requirements.txt` — added `matplotlib` (chart output, was missing) and `pillow` (image verification; was present transitively via torchvision but not pinned directly).
- `data/train/`, `data/val/` — real output, `neutral`/`smoke`/`fire` subdirectories each.

### Key decisions
- **Split strategy: Option B, pool everything.** All three D-Fire splits (train/val/test — 14,122 + 3,099 + 4,306 = 21,527 images) pooled and re-split 85/15 by this script, ignoring D-Fire's original split boundaries entirely. Reasoning: `plan.md` §8's Day 1 prompt was written assuming a single undifferentiated D-Fire download directory, not a mirror that ships three pre-split folders, and `plan.md` does not specify a held-out test set anywhere beyond the Day 5 adversarial eval and Day 11 trial evaluation — so there was no held-out-test-set requirement this pooling could violate. Decided and documented before writing code, resolving the Addendum 1/2 open item.
- Fire takes priority over smoke when a label file contains both class IDs — matches info.md §4.1's strictest bar (fire recall), an image with any fire content is never filed as merely smoke.
- Hard negatives walked recursively (`rglob`), not top-level — the directory holds 6 per-category subfolders, not a flat list of images.
- `matplotlib` and `pillow` added to `requirements.txt` and installed — required for the chart and image-verification steps respectively; neither was present as a direct dependency before this phase.
- Applied `long-story-short`: fixed a reproducibility bug caught during review — the filename-collision fallback used Python's built-in `hash()`, which is randomized per-process for strings (`PYTHONHASHSEED`), so the disambiguated filename for a collision would differ run to run even with the same split seed. Replaced with `hashlib.md5` for a stable digest, and `shutil.copyfile` replaced a manual read-all-bytes-then-write for idiomatic, memory-light copying. Verified behavior-preserving by re-running end to end: identical counts before and after (no actual filename collisions occurred in this dataset, so the fix is inert for this run but correct for future ones).

### Measured results
Real counts, from the actual run (`conda run -n firewatch python train/prepare_data.py`), no placeholders:

| Class | Train | Val | Total |
|---|---|---|---|
| neutral | 8,528 | 1,505 | 10,033 |
| smoke | 4,987 | 880 | 5,867 |
| fire | 4,949 | 873 | 5,822 |
| **TOTAL** | **18,464** | **3,258** | **21,722** |

Hard-negative contribution (all folded into `neutral`, per-category):

| Category | Count |
|---|---|
| car_lights_night | 29 |
| red_orange_objects | 37 |
| steam | 36 |
| stove_cooking | 30 |
| sunset_window | 28 |
| warm_lights | 35 |
| **Total** | **195** |

0 files skipped (no corrupt images, no malformed label files encountered in this run). 21,722 total images = 21,527 D-Fire + 195 hard negatives. Chart saved to `eval/class_balance.png`.

**TV/laptop fire-footage hard negatives (30 images, category 7 of 7 per plan.md §6.4) are still not collected.** This run proceeded without them, as instructed — noted here as a carried-forward open item, not a blocker.

### How to verify
```
conda run -n firewatch python train/prepare_data.py
for d in data/train/* data/val/*; do echo "$d: $(ls "$d" | wc -l)"; done
open eval/class_balance.png
```

### Open items
- TV/laptop fire-footage category (30 images) — manual screenshot collection still required, not started. Carried forward, not blocking Phase 1 completion (plan.md §8's Day 1 scope was the split script itself).
- `hard_negatives_rejected/` correctly excluded (script only reads `data/hard_negatives/`) — confirmed by spot-checking output does not contain rejected filenames.

### Next phase
Day 2 per `plan.md` §8: `train/train_classifier.py` (MobileNetV3-Small fine-tune on Colab) and `train/export_onnx.py`.
