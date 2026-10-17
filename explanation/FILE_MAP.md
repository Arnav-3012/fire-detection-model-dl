# FireWatch — File Map

## How to use this map

This document describes what every tracked file and folder in the FireWatch
repository actually does, based on reading the code as it exists today (not
just what `plan.md` or `README.md` claim was planned). Sections mirror the
real directory tree. Bulk data/image folders are summarized with a file
count rather than enumerated file-by-file — see each folder's one-line
description for what it contains. A **Notes / discrepancies** section at the
end flags dead code, empty files, and mismatches between docs and the
tree. Excluded everywhere: `.git/`, `__pycache__/` (any depth),
`node_modules/`, `.venv/`/`venv/`/`env/`, `.DS_Store`, `.pyc` files.

## Architecture summary

FireWatch is a laptop-hosted fire/gas hazard detector. **`edge/`** runs the
always-on loop: `camera.py` grabs webcam frames, `vision.py` runs an ONNX
MobileNetV3-Small 3-class classifier (`neutral`/`smoke`/`fire`) per frame and
smooths the result with an N-of-M `TemporalVoter`, `sensors.py` reads
MQ-2/MQ-135 gas readings from an Arduino over serial, and `fusion.py`
combines vision + gas booleans into one of four levels (`SAFE` / `WATCH` /
`WARNING` / `CRITICAL`) via a fixed, deterministic priority-ordered rule
table. `main.py` wires these together and enforces the project's core safety
claim: the local buzzer/LED fire **before** any network call, and a network
failure can never suppress the local alarm. WARNING+ verdicts are POSTed
(best-effort, 2s timeout) to **`agent/`**, a LangGraph state machine
(`graph.py`) that only ever composes and delivers a response — it never
re-decides whether there's a fire. It looks up the nearest fire station
(display-only, via OSM Overpass in `locate.py`), composes alert text with a
Groq LLM plus a deterministic template fallback (`compose.py`), sends a
Telegram alert with a cancel window (`tools.py`), sends an informational
Twilio SMS to the developer's own phone (`escalate.py`), and on timeout
writes a `SIMULATED: true` dispatch packet to `dispatch_log.jsonl`
(`tools.py`) — never a real emergency contact. **`cloud/uploader.py`**
archives CRITICAL incidents to S3 with a local-file fallback. The
**dashboard** (`dashboard/backend/main.py`, a read-only FastAPI app, plus a
Vite/React frontend under `dashboard/frontend/src/`) polls these same files
(`dispatch_log.jsonl`-derived feedback CSV, `eval/results.csv`,
`data/live_sensors.json`) and never writes back into the detection/agent
pipeline. **`train/`** and **`eval/`** hold the offline ML pipeline: dataset
preparation from D-Fire plus hand-collected hard negatives
(`prepare_data.py`), MobileNetV3-Small fine-tuning (`train_classifier.py`),
ONNX export with numerical verification (`export_onnx.py`), and a large set
of diagnostic/threshold-sweep/adversarial-video evaluation scripts. The
current production model is `models/fire_mnv3.onnx` (v4, promoted
2026-09-05).

---

## Root

- `README.md` — top-level project overview: architecture diagram, repo
  layout, setup/run instructions, hardware pin table, model metrics table,
  evaluation results, dashboard description, safety/disclosure section, and
  known limitations. The canonical "read this first" doc for a new reader.
- `plan.md` — the full original specification: what changed from the
  original idea and why, software/hardware tracks, bill of materials, pin
  map, MQ calibration procedure, data collection plan, day-by-day schedule,
  the literal prompts used to build each phase in Claude Code, a cut list,
  and hardware/troubleshooting appendices. Also contains later dated
  addenda (2026-08-31 onward) documenting scope decisions made after the
  original plan was written (Twilio SMS, feedback-log schema, the reduced
  12-trial Day 11 evaluation set with per-trial pass/fail notes).
- `info.md` — operating rules for whoever (human or Claude Code) works on
  this repo: session-start protocol, absolute safety rules (no real
  emergency dispatch, local alarm before network, LLM never decides
  detection, no fabricated metrics, no secrets in git), code standards
  (config-driven thresholds, failure-behavior table, ~200-line file
  guideline), quality bars (fire recall ≥0.95 block bar, adversarial
  false-positive bars, FPS/latency bars), and the `logs.md`/`context.md`
  update protocol.
- `context.md` — a regenerated (not appended) fast-recovery summary of
  current project state: corrected architecture, current phase, model
  state, recent decisions, open items. Meant to be read instead of the full
  `logs.md` in routine sessions.
- `logs.md` — append-only build log; every phase's what-was-built,
  decisions, measured results, verification command, and open items, plus
  many dated addenda. The full historical record (~570KB) — large by
  design, per `info.md`'s protocol.
- `report.md` — the final project report (abstract, design changes,
  architecture, dataset, evaluation, limitations) — the human-readable
  writeup built from `logs.md`/`context.md`/measured CSVs, per `plan.md`'s
  Day 12 prompt and Appendix C checklist.
- `agent_explained.md`, `fusion_explained.md`, `sensor_hardware_explained.md`
  — three long-form tutorial documents (a "sensei"-style intuition → math →
  code → connection → check-yourself walkthrough) explaining, respectively,
  every function in `agent/*.py` and how the LangGraph response pipeline
  works; `edge/fusion.py`'s `fuse()` function and how it bridges vision and
  the agent; and the physical MQ gas-sensor chemistry/electronics/
  calibration side of the project. These are supplementary teaching docs,
  not specification or log documents.
- `config.example.yaml` — tracked template for `config.yaml`: every vision
  threshold (input size, fire/smoke decision thresholds, temporal-voter
  window/votes), sensor calibration values (MQ-2/MQ-135 baseline/warn/danger,
  gas warm-up gate), fusion cancel window, agent settings (Groq model,
  Telegram poll interval, Overpass URL/radius/timeout, Twilio timeout,
  feedback log path), live-log buffer settings, hardcoded location, 101/112
  emergency fallback numbers, and AWS/S3 settings with a session upload
  cap — each key commented with what it means, when it was calibrated, and
  which file/phase consumes it.
- `config.yaml` — gitignored, real filled-in copy of the above (present
  locally; not committed). Read directly by `edge/vision.py`,
  `edge/sensors.py`, `edge/fusion.py`, `edge/main.py`, `edge/livelog.py`,
  every `agent/*.py` module, `dashboard/backend/main.py`, and several
  `eval/*.py` scripts.
- `.env.example` — tracked, credential **names only** (empty values):
  `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
  `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_DEFAULT_REGION`,
  `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/`TWILIO_FROM_NUMBER`/
  `TWILIO_TO_NUMBER`.
- `.env` — gitignored, real credentials (present locally).
- `.gitignore` — excludes `.env`/`config.yaml` (secrets/local config),
  `models/` and `data/` (weights and datasets), Python/Node build
  artifacts, large adversarial `.mov`/`.avi` clips, `.DS_Store`, and
  runtime-generated logs (`dispatch_log.jsonl`, `eval/alert_feedback.csv`,
  `data/live_sensors.json`, `eval/calibration/*.csv`) — these are treated as
  generated data, not source.
- `requirements.txt` — Python dependencies: `torch`, `torchvision`, `onnx`,
  `onnxruntime`, `opencv-python`, `numpy`, `pandas`, `pyserial`, `fastapi`,
  `uvicorn`, `langgraph`, `langchain-core`, `groq`, `boto3`, `paho-mqtt`,
  `python-dotenv`, `pyyaml`, `requests`, `ddgs` (DuckDuckGo image search),
  `kaggle`, `matplotlib`, `pillow`, `onnxscript`. Notably: no `streamlit`
  entry despite `plan.md` originally specifying a Streamlit dashboard (see
  Notes).
- `setup.sh` — bash setup script: creates a Python 3.11 venv, installs
  `requirements.txt`, prints next steps (`python scripts/verify_env.py`).
  Fails loudly if `python3.11` isn't found.
- `setup.ps1` — PowerShell equivalent of `setup.sh` for Windows.
- `dispatch_log.jsonl` — runtime-generated (gitignored per `.gitignore`, but
  present locally with real content): one JSON line per `simulate_dispatch()`
  call from `agent/tools.py`, each carrying `"SIMULATED": true` and an
  explicit no-real-contact note. Read by `dashboard/backend/main.py`
  indirectly is NOT the case — the dashboard actually reads
  `eval/alert_feedback.csv` for incidents (see `dashboard/backend/main.py`
  below) and S3 for the archive; this file is the local append-only
  ledger of what would have been dispatched.

## `.claude/`

Empty directory (no tracked files found under it) — presumably a local
Claude Code project-settings location with nothing currently populated.

## `.vscode/`

- `settings.json` — VS Code Python environment settings: points the Python
  extension at a conda environment named `firewatch`
  (`/opt/anaconda3/envs/firewatch/bin/python`) as the default interpreter
  and environment/package manager. Editor configuration only, not part of
  the application.

---

## `arduino/`

### `arduino/sensor_node/`

- `sensor_node.ino` — Arduino sketch flashed to the Uno. Reads MQ-2 (`A0`)
  and MQ-135 (`A1`) once per second via `millis()`-based non-blocking
  timing (not `delay()`, so an alarm byte is never left unread for up to a
  second) and streams each reading as a `"mq2,mq135\n"` CSV line at 9600
  baud — consumed by `edge/sensors.py` and `eval/calibrate_mq.py`. Also
  accepts a single-byte command over serial: `'A'` drives the buzzer
  (`D8`) HIGH, `'S'` drives it LOW; anything else is ignored, and there is
  deliberately no acknowledgment reply. No DHT22/temperature code — that
  sensor was cut from the build (see Notes).

---

## `edge/`

The always-running local detect-and-alarm loop. No file here may block on
network I/O before the local alarm fires (`info.md` 2.2).

- `__init__.py` — empty, makes `edge` importable as a package.
- `camera.py` — `Camera` class wrapping `cv2.VideoCapture` for the single
  webcam source (device index 0, MacBook built-in). Discards the first 10
  frames on open (`_warm_up()`) to skip macOS auto-exposure/focus settling
  frames; `read()` raises `RuntimeError` on a bad grab rather than
  returning `None`; `encode_jpeg()` is used by `edge/main.py`'s
  `notify_agent()`. A camera that fails to open prints likely causes and
  calls `sys.exit(1)` — loud-and-exit, not silent retry.
- `vision.py` — `TemporalVoter` (N-of-M rolling-window vote over per-frame
  booleans, via `collections.deque(maxlen=window)`) and `VisionModel`
  (loads `models/fire_mnv3.onnx` via `onnxruntime.InferenceSession`,
  reading `input_size`/`fire_decision_threshold`/`smoke_decision_threshold`/
  `frame_threshold`/`window`/`votes_needed`/`smoke_votes_needed` from
  `config.yaml`). `VisionModel.predict()` preprocesses a BGR frame
  (BGR→RGB, resize, ImageNet-normalize, NCHW), runs the ONNX session,
  softmaxes the logits, and returns `fire`/`smoke`/`p_fire`/`p_smoke`
  (fire via a probability threshold, smoke via argmax-AND-threshold).
  `predict_smoothed()` feeds both a fire `TemporalVoter` and a separate
  smoke `TemporalVoter` and returns the merged raw + smoothed result
  (`alarm`, `votes`, `smoke_sustained`, `smoke_votes`). `CLASS_TO_IDX =
  {"fire": 0, "neutral": 1, "smoke": 2}` is hardcoded (fixed by the trained
  checkpoint, not a tunable).
- `sensors.py` — `SensorReader`: opens the Arduino serial port
  (`config.yaml`'s `sensors.serial_port`/`baud`) on a daemon thread, parses
  the `"mq2,mq135"` CSV stream, exposes `latest()` (last-known readings,
  `None` until the first valid line), `first_reading_monotonic()` (anchor
  for the gas warm-up gate), and `set_alarm(bool)` (writes `'A'`/`'S'` to
  the same serial handle from the caller's thread, fire-and-forget). A
  malformed line is dropped silently; a dead/unplugged port logs a warning
  and retries every 3s without crashing the reader thread or the vision
  loop (`info.md` 3.2).
- `fusion.py` — the deterministic hazard-decision core. `Level` is an
  `IntEnum` (`SAFE`=0, `WATCH`=1, `WARNING`=2, `CRITICAL`=3).
  `temp_spiking()` is a permanent stub always returning `False` (no DHT22
  temperature sensor in this build). `load_gas_thresholds()` and
  `compute_gas_high()` read/derive MQ warn thresholds from `config.yaml`.
  `fuse(vision_fire, vision_smoke, gas_high, temp_spiking)` applies five
  priority-ordered rules and returns `(Level, reason_string)`: only
  vision+gas agreement (rule 1) or vision+temp-spike (rule 2, permanently
  disabled) reach `CRITICAL`; gas-alone or vision-alone fire cap at
  `WARNING`; smoke-alone is `WATCH`. No model, no LLM, no network here.
- `livelog.py` — `LiveLogWriter`: a 1 Hz, queue-buffered, atomic-file-write
  live-readings feed for the dashboard. The main loop's only cost is a
  `SimpleQueue.put()` at most once per second; a separate daemon thread
  drains the queue into a `deque(maxlen=buffer_size)` and rewrites
  `data/live_sensors.json` via write-then-`os.replace` so readers never see
  a partial file. Records `mq2`, `mq135`, `p_fire`, and the already-computed
  fusion `level` string at every tier (not just WARNING+).
- `main.py` — the entry point wiring everything together. Loop order per
  frame: read camera → `predict_smoothed()` → read sensors → compute
  gas-warm-up-gated `gas_high` → `fuse()` → **drive the local buzzer via
  `reader.set_alarm()`** (transition-driven, no cooldown) → *then*, only if
  WARNING+ and past a 60s cooldown, POST the incident to the agent
  (`notify_agent()`, 2s timeout, try/except, never blocks/suppresses the
  alarm already fired) → record a live-log sample → print an FPS counter
  every 30 frames. `notify_agent()` JPEG-encodes the frame and POSTs
  `{level, reason, vision, sensors, snapshot_b64}` to
  `config.yaml`'s `agent.incident_url`.

---

## `agent/`

LangGraph-based response agent. Handles response only — detection is
already finished by the time any file here runs (`info.md` 2.3).

- `__init__.py` — empty, makes `agent` importable as a package.
- `graph.py` — builds and runs the fixed-edge LangGraph state machine
  (`IncidentState` TypedDict). Nodes, in order: `verify` (rejects
  sub-WARNING input, generates `event_id`/`timestamp`, never upgrades) →
  `locate` (calls `agent/locate.py`, display-only) → `compose` (calls
  `agent/compose.py`) → `notify_owner` (sends Telegram via
  `agent/tools.py`, baselines the cancel-poll offset) → `escalate` (sends
  Twilio SMS via `agent/escalate.py`) → `wait` (polls for a Telegram
  CANCEL reply) → conditional edge to `cancelled` or `simulate` (both
  append a feedback row via `agent/feedback.py`, and upload CRITICAL
  incidents to S3 via `cloud/uploader.py`). `run_incident()` is the entry
  point called by `agent/server.py`. The `__main__` block runs a synthetic
  "fire drill" (`python -m agent.graph warning|critical`) without needing
  the edge loop.
- `compose.py` — the one place an LLM is allowed. `compose_alert_text()`
  calls Groq (`groq` SDK, model from `config.yaml`'s `agent.groq_model`,
  currently `openai/gpt-oss-20b`) with a system prompt that forbids judging
  whether there's a fire; falls back to a deterministic `TEMPLATES` string
  if Groq fails, times out, returns empty text, hits the token cap, or
  omits the required verbatim time phrase. `compose_sms_text()` builds a
  separate, shorter (`SMS_CHAR_BUDGET`=300 chars) SMS body — no cancel
  instruction, since SMS has no listening mechanism. `natural_time_phrase()`
  converts an ISO timestamp to a concrete clock-time phrase (e.g. "at 9:29
  PM") — never a vague "just now".
- `locate.py` — `find_nearest_fire_station()`: queries OSM Overpass for
  `amenity=fire_station` within a radius of `config.yaml`'s hardcoded
  `location.latitude/longitude`, computes haversine distance, and returns
  a display-only dict (`found`, `name`, `phone`, `distance_km`, `line`).
  One short retry on transient Overpass failure; falls back to a graceful
  "could not be determined" dict on genuine failure or a `(0,0)`
  placeholder location. Explicitly documented as never a dial target.
- `escalate.py` — `send_twilio_alerts()`: sends an informational SMS (via
  raw Twilio REST calls with `requests`, not the Twilio SDK) to the
  developer's own `TWILIO_TO_NUMBER` only. The Twilio **voice call** code
  path is fully implemented but commented out and permanently disabled
  (`call_ok = False`) because Twilio trial accounts gate calls behind an
  interactive "press any key" prompt. Never raises; any failure logs a
  warning.
- `feedback.py` — `append_feedback()`: appends one row per resolved
  incident to `eval/alert_feedback.csv` (state/action/outcome/reward
  schema) — `CANCELLED` → reward `-1`, `TIMEOUT` → reward `+1`. Explicitly
  data-collection only; no RL or automated threshold tuning is implemented
  or implied.
- `tools.py` — `send_telegram()` (posts to the Telegram Bot API, sends the
  snapshot as a photo with caption, falls back to text-only, retries
  once), `latest_update_id()`/`poll_for_cancel()` (the reply-based CANCEL
  mechanism, polling `getUpdates`), and `simulate_dispatch()` (appends a
  `{"SIMULATED": true, ...}` JSON line to `dispatch_log.jsonl` and prints
  an unmistakable console banner — this is the **only** thing that
  happens on "dispatch"; nothing here ever contacts a real service).
- `server.py` — FastAPI app (`uvicorn agent.server:app --port 8000`,
  binds `127.0.0.1` only). `POST /incident` accepts the payload
  `edge/main.py` sends, decodes/saves the base64 snapshot to
  `config.yaml`'s `agent.snapshot_dir` (`data/incidents`), and runs
  `agent.graph.run_incident()` as a FastAPI `BackgroundTasks` job so the
  HTTP response returns immediately (the graph can run 60s+ due to the
  cancel window). `GET /health` for a liveness check.

---

## `cloud/`

- `__init__.py` — empty, makes `cloud` importable as a package.
- `uploader.py` — `log_incident()`: uploads a CRITICAL incident's JSON
  packet (+ optional JPEG) to S3 under `device_01/YYYY/MM/DD/HHMMSS_<event_id>`,
  called at most once per incident from `agent/graph.py`'s `simulate()`
  node. Cost-safety design: a process-lifetime `session_max_uploads`
  circuit breaker (default 50, from `config.yaml`'s `aws.max_uploads_per_session`),
  no retry-with-backoff (one attempt, log-and-return on failure), and a
  local fallback write to `data/incidents/` (`_local_fallback()`) if S3 is
  unreachable. Never blocks or delays the local dispatch log.

---

## `dashboard/`

- `__init__.py` — empty, makes `dashboard` importable as a package.
- No top-level `app.py` exists here despite `plan.md`'s original Streamlit
  spec — see Notes; the actual dashboard is the FastAPI+React pair below.

### `dashboard/backend/`

- `__init__.py` — empty.
- `main.py` — a second, independent, **read-only** FastAPI app
  (`uvicorn dashboard.backend.main:app --port 8001`) — deliberately thin,
  no fusion/decision logic, never imports `agent/server.py`. Endpoints:
  `GET /api/incidents` (reads `eval/alert_feedback.csv` as JSON), `GET
  /api/s3-archive` (lists every `device_XX/` prefix's JSON objects from
  S3, graceful error response on failure), `GET /api/trials` (reads
  `eval/results.csv`), `GET /api/fire-station` (calls `agent.locate
  .find_nearest_fire_station()` directly, caches only successful finds so
  a transient Overpass failure doesn't stick), `GET /api/live-sensors`
  (reads `data/live_sensors.json`, the file `edge/livelog.py` writes, plus
  calibrated gas thresholds from `config.yaml`), `GET /health`. CORS
  restricted to the Vite/CRA local dev origins. Explicitly calls
  `load_dotenv()` with an absolute repo-root path (a documented 2026-09-03
  bug fix — this file previously had no AWS credentials because nothing
  else it imports calls `load_dotenv()`).

### `dashboard/frontend/`

- `index.html` — Vite entry HTML (mounts `#root`, loads `src/main.jsx`).
- `package.json` — npm scripts (`dev`/`build`/`lint`/`preview`);
  dependencies `plotly.js`, `react`/`react-dom` 19, `react-plotly.js`;
  devDependencies `vite`, `@vitejs/plugin-react`, `oxlint`.
- `package-lock.json` — npm lockfile.
- `vite.config.js` — minimal Vite config with the React plugin.
- `.oxlintrc.json` — Oxlint (Rust-based JS/TS linter) configuration.
- `.gitignore` — frontend-local ignores (build output, etc.).
- `README.md` — the stock Vite+React template README (React Compiler,
  Oxlint notes) — generic boilerplate, not FireWatch-specific content.
- `public/favicon.svg`, `public/icons.svg` — static SVG assets.

#### `dashboard/frontend/src/`

- `main.jsx` — React root: renders `<App />` in `<StrictMode>` into
  `#root`, imports `index.css`.
- `App.jsx` — top-level component. Sets up five `usePolling()` data feeds
  (incidents every 5s, S3 archive every 30s on tab focus, trials/fire
  station every 60s on tab focus, live sensors every 3s on Overview
  focus) and renders the `Tabs` component with five tab contents:
  Overview, Live Incidents, Historical Archive, Evaluation Trials,
  Nearest Fire Station.
- `api.js` — thin `fetch` wrappers against `http://127.0.0.1:8001`
  (the dashboard backend): `fetchIncidents`, `fetchS3Archive`,
  `fetchTrials`, `fetchFireStation`, `fetchLiveSensors`.
- `usePolling.js` — shared polling hook (`{data, error, loading}`),
  supports an `active` flag so low-churn endpoints only poll while their
  tab is focused.
- `levels.js` — mirrors `edge/fusion.py`'s `Level` enum exactly
  (`SAFE`/`WATCH`/`WARNING`/`CRITICAL`) plus a color map, so the
  dashboard's severity ordering can never drift from the backend's.
- `plotlyTheme.js` — a shared dark Plotly layout override
  (`darkLayout`, `plotlyConfig`) so every chart matches the app's dark
  "ember on ash" theme instead of Plotly's default light theme.
- `formatTimestamp.js` — `formatTimestamp()`: converts an ISO string or
  unix-seconds number into a human-readable "3:14 PM, Sep 6" string,
  mirroring `agent/compose.py`'s `natural_time_phrase()` convention on
  the frontend side. Returns the input unchanged if unparseable.
- `index.css` — the full app stylesheet: CSS custom properties for the
  dark "ember/ash" color palette, glassmorphism panel styles, layout
  grid classes, card/badge/skeleton/tooltip styles.

##### `dashboard/frontend/src/tabs/`

- `Overview.jsx` — the largest tab: a system-health "hero" ring gauge
  (live if `edge/main.py`'s live feed is fresh within 12s, else falls
  back to the last logged incident, with an explicit "Device Offline"
  state), four metric cards (total/WARNING/CRITICAL counts, cancel
  rate), a Plotly step-line fusion-level timeline with custom hover
  tooltips and per-level background bands, a compact fire-station card,
  a most-recent-event card, and the full-width `LiveSensorChart`.
- `LiveIncidents.jsx` — a filterable, expandable feed-style list (not a
  table) over the incidents data, with level/outcome/date-range filters
  and a raw-JSON expand-on-click per card.
- `HistoricalArchive.jsx` — renders the S3 archive grouped by device
  prefix as per-device tables (timestamp, level, reason, owner response,
  S3 key), with a device filter and explicit error/empty states.
- `EvaluationTrials.jsx` — a bar chart of trial outcome counts plus a
  raw data table of every row in `eval/results.csv`; shows an explicit
  "no trial data yet" state if trials haven't been run.
- `FireStation.jsx` — the dedicated fire-station tab: name/distance/phone
  card plus a display-only emergency-numbers (101/112) card explicitly
  labeled "never auto-dialed".

##### `dashboard/frontend/src/components/`

- `LiveSensorChart.jsx` — Plotly dual-line chart of mq2/mq135 live
  readings with dotted warn/danger threshold lines and annotations,
  reading from the `/api/live-sensors` feed.
- `Tabs.jsx` — a WAI-ARIA-compliant tab widget (roving tabindex,
  arrow-key/Home/End navigation, `role="tablist"`/`"tab"`/`"tabpanel"`).
- `icons.jsx` — hand-written inline SVG icon set (no icon-library
  dependency) with shared stroke conventions.
- `Reveal.jsx` — a scroll-triggered fade/rise-in wrapper using
  `IntersectionObserver`, one-time (disconnects after first reveal).
- `Skeleton.jsx` — shimmer loading placeholders (`SkeletonMetricCard`,
  `SkeletonPanel`) shown while a tab's first fetch is in flight.
- `LevelBadge.jsx` — colored pill for a fusion level, with an icon and
  optional pulse animation for CRITICAL.
- `CountUp.jsx` — animates a numeric metric card value from its previous
  to next value over ~350ms using `requestAnimationFrame`.
- `StateCard.jsx` — shared empty/error/offline state card with inline
  SVG icon, used across every tab.
- `ChartTooltip.jsx` — a custom glass-style hover tooltip for Plotly
  charts (replacing Plotly's default), clamped to stay inside its
  container.

---

## `train/`

Dataset preparation, model training, and ONNX export pipeline.

- `__init__.py` — empty, makes `train` importable as a package.
- `prepare_data.py` — builds the 3-class `data/train/`+`data/val/` split.
  Pools D-Fire's train/val/test folders (ignoring their original
  boundaries), derives an image-level label from each YOLO per-box label
  file (`label_from_yolo_file()`, fire takes priority over smoke),
  recursively folds in `data/hard_negatives/` (all → `neutral`) and any
  `--extra-fire-positive` directories (all → `fire`), verifies every
  image is readable before copying, and does a class-stratified 85/15
  split (`stratified_split()`, seed 42). Refuses to run against
  non-empty output folders unless `--clean` is passed (a 2026-08-27
  train/val leakage incident is the reason). Calls
  `train/check_leakage.py` on itself at the end and
  `train/data_report.py` for the balance table/chart.
- `train_classifier.py` — fine-tunes `torchvision`'s
  `mobilenet_v3_small` (ImageNet-pretrained) into the 3-class classifier.
  Two-stage training: stage 1 (2 epochs) trains only the new
  `Linear(1024→3)` head with the backbone frozen at LR 1e-3; stage 2
  unfreezes everything and continues at LR 5e-5, each stage with its own
  cosine LR schedule and fresh AdamW optimizer. Trains on Apple-silicon
  MPS if available (`select_device()`), fails loudly rather than
  silently falling back to CPU on an MPS-specific error. Saves the best
  checkpoint by val accuracy (not the last epoch) to
  `models/fire_mnv3_best.pt` with the `class_to_idx` mapping embedded.
  Calls `train/metrics_report.py` for the confusion matrix/training
  curves, and hard-exits (code 2) if fire recall on val is below 0.95
  (`info.md` 4.1's block bar).
- `export_onnx.py` — loads a `.pt` checkpoint, exports to ONNX with a
  dynamic batch axis (`torch.onnx.export`), then verifies the exported
  graph's output against real PyTorch inference on 32 real validation
  images (not random tensors), comparing raw logits within a `1e-4`
  tolerance. Exits non-zero if verification fails — "do not deploy this
  artifact".
- `check_leakage.py` — standalone train/val leakage regression guard.
  Content-hashes (md5) every image in `data/train` and `data/val`,
  reports cross-split overlap by filename AND by content (catching
  disambiguated-name duplicates a filename check would miss), plus
  within-split duplicate groups. Exit code 1 on any cross-split content
  overlap. Called both standalone and from `prepare_data.py`.
- `data_report.py` — `print_balance_table()` and `save_balance_chart()`,
  factored out of `prepare_data.py` to keep it under `info.md`'s
  ~200-line guideline. Prints per-class train/val counts, hard-negative
  and extra-fire-positive breakdowns by category, and saves a grouped
  bar chart to `eval/class_balance.png`.
- `metrics_report.py` — evaluation reporting helpers factored out of
  `train_classifier.py`: `confusion_matrix()`, `per_class_metrics()`
  (precision/recall/F1 computed by hand from the confusion matrix, not
  sklearn — "the arithmetic IS the lesson"), `print_metrics_table()`,
  `save_confusion_matrix_plot()`, `save_training_curves()`.

---

## `eval/`

Threshold sweeps, adversarial-video evaluation, trial logging, and
model-inspection diagnostics. Most scripts here are explicitly
diagnostic-only (they don't edit `config.yaml` or retrain) and reuse
`edge/vision.py`/`edge/fusion.py` directly rather than reimplementing
detection logic (`info.md` 3.4).

- `__init__.py` — empty.
- `run_eval.py` — the Day 5 adversarial evaluation driver. Loads a
  `VisionModel` against a specified ONNX checkpoint (via a temp
  config-override file, keeping `VisionModel`'s constructor untouched),
  runs every frame of each adversarial video through
  `predict_smoothed()`, and counts alarm **events** (rising edges of the
  smoothed alarm flag, not raw per-frame counts) plus time-to-first-alarm
  and smoke-WATCH events. Exposes `run_video()` and `ADVERSARIAL_DIR`,
  reused by `votes_needed_sweep.py`.
- `run_trial.py` — the Day 11 evaluation trial logger (`info.md` 4.4).
  Launches `edge/main.py` as a real subprocess, tails its stdout for the
  `"{LEVEL}: {reason}"` line `format_status()` already prints, tracks the
  highest level reached and time-to-first-level-change as detection
  latency, and appends one row to `eval/results.csv`
  (`trial_id`/`timestamp`/`trial_label`/`expected_outcome`/
  `actual_outcome`/`detection_latency_seconds`/`pass`). Has a documented
  `ACCEPTABLE_BOUNDS` exception for the known TV/laptop-fire limitation.
- `calibrate_mq.py` — the Day 6b MQ sensor calibration helper. Connects
  to the Arduino, logs raw MQ-2/MQ-135 values with timestamps to
  `eval/calibration/*.csv`, and supports `--baseline` (log for N minutes,
  print mean/std/min/max and suggested warn/danger thresholds using the
  `baseline + 0.30/0.60 * (peak - baseline)` formula) and `--peak` (live
  rolling max during a trigger test, labeled per sensor).
- `threshold_sweep.py` — diagnostic-only sweep of the fire decision
  threshold (`fire_decision_threshold`) over candidate values
  `[0.30..0.50]`, reporting the recall/precision/false-alarm tradeoff
  against `info.md` 4.1's block bars. Does not edit `config.yaml` or
  retrain.
- `smoke_threshold_sweep.py` — sibling sweep for the smoke decision
  threshold, comparing a plain-probability rule vs. the actual
  argmax-AND-threshold rule `edge/vision.py` uses, over candidates
  `[0.30..0.70]`.
- `votes_needed_sweep.py` — diagnostic sweep of `TemporalVoter`'s
  `votes_needed` (N), reusing `run_eval.py`'s `build_model()`/`run_video()`
  rather than reimplementing the video loop, specifically targeting the
  TV/laptop-fire adversarial scenario's persistence-vs-real-flicker
  asymmetry.
- `test_fusion.py` — a standalone (no pytest) printed pass/fail test
  scaffold for `edge/fusion.py`'s `fuse()` covering every rule in
  priority order, including proving rule 2 (temp-spiking) is
  structurally reachable even though production can never trigger it.
  Exit code 0 on all-pass, 1 on any failure.
- `val_inference.py` — shared helper (`load_model()`, `run_inference()`)
  used by `inspect_misclassified.py` and the threshold-sweep scripts so
  the model-loading and val-set-inference logic isn't duplicated.
- `inspect_misclassified.py` — diagnostic-only: pulls up real
  misclassified fire images (from the confusion matrix's off-diagonal
  cells) with the model's full probability distribution, splitting
  "close calls" from "confident misses", and copies the images into
  `eval/misclassified_fire_as_smoke/` and
  `eval/misclassified_fire_as_neutral/` for human review.
- `inspect_model.py` — a large model-inspection/report-writing aid
  (architecture dump, parameter sanity checks, feature-map
  visualization, Grad-CAM). Not part of the training/eval pipeline
  proper — produces everything under `eval/model_understanding/`.
- `compare_v3_stove_flame.py` — a one-off diagnostic comparing v2 vs v3
  model behavior on the exact same `fire_candle.mov` frames a prior
  Grad-CAM investigation used, to keep the comparison controlled.
- `scratch_stove_gradcam.py` — a one-off diagnostic for a specific Day 5
  gas-stove-flame zero-alarm finding: runs v2's ONNX model over
  `fire_candle.mov` to find representative frames, then runs Grad-CAM
  (reusing `inspect_model.py`'s implementation) on v2's `.pt` checkpoint
  at those frames.
- `alert_feedback.csv` — runtime-generated (gitignored) log written by
  `agent/feedback.py`; also the data source for the dashboard's
  `/api/incidents` endpoint. Present locally with real rows (level,
  p_fire, mq2/mq135, gas_high, votes, threshold config in effect,
  outcome, reward).
- `results.csv` — untracked-but-present (`?? eval/results.csv` in git
  status) log written by `eval/run_trial.py`; the Day 11 evaluation
  trial ledger read by the dashboard's `/api/trials` endpoint.
- `class_balance.png`, `class_balance_v3.png`, `confusion_matrix.png`,
  `confusion_matrix_v3.png`, `training_curves.png`, `training_curves_v3.png`
  — generated report images from `train/data_report.py`/
  `train/metrics_report.py`, current (v4/latest) and archived v3 versions
  side by side.
- `train_log.txt` — a saved plain-text training run log.

### `eval/adversarial/` (5 files)

Self-recorded ~30s adversarial test video clips: `fire_candle.mov`,
`neutral_redclothing.mov`, `neutral_steam.mov`, `neutral_sunset.mov`,
`neutral_tvfire.mov`. Consumed by `eval/run_eval.py` and
`eval/votes_needed_sweep.py`. Large `.mov` files are gitignored per
`.gitignore` (up to ~290MB, over GitHub's limit) but present locally.

### `eval/calibration/` (7 files)

MQ-2/MQ-135 raw calibration CSVs written by `eval/calibrate_mq.py`:
one baseline log and several peak-trigger logs (lighter-near-MQ-2,
breath-near-MQ-135). Gitignored raw measurement data.

### `eval/model_understanding/` (14 files)

Output directory for `eval/inspect_model.py` and
`eval/scratch_stove_gradcam.py`: architecture dump (`architecture.txt`,
`architecture_diagram.png`), per-class feature-map visualizations,
per-class Grad-CAM overlays, and four stove-flame Grad-CAM frames from
the one-off diagnostic. Exploratory tooling output, not phase
deliverables.

### `eval/misclassified_fire_as_smoke/` (51 files) and `eval/misclassified_fire_as_neutral/` (17 files)

Copies of actual validation images the model misclassified, saved by
`eval/inspect_misclassified.py` for human review — one folder per
confusion-matrix off-diagonal cell of interest.

---

## `scripts/`

One-off data-collection and environment utilities — explicitly not part
of the `edge`/`agent`/`train` application code.

- `fetch_hard_negatives.py` — downloads 6 of 7 hard-negative categories
  (sunset, red/orange objects, warm lights, steam, car lights at night,
  stove cooking) via DuckDuckGo image search (`ddgs` package, no API key),
  validating each image with PIL before saving. The 7th category
  (TV/laptop fire footage) is deliberately excluded — not a natural
  search subject.
- `fetch_small_flame_images.py` — same downloader pattern, targeting
  small/localized-flame FIRE-class images (matchstick, lighter, small
  candle, gas-stove flame) to address a Grad-CAM finding that the model
  under-weights small contained flames. Saves to
  `data/additional_fire_training/scraped/<category>/`; does not fold the
  result into the training split itself.
- `capture_webcam_negatives.py` — captures hard-negative frames directly
  from the edge device's own webcam (reusing `edge/camera.py` and
  `edge/vision.py` verbatim) for a scene the live loop specifically
  misclassifies (a bright-lit textured wall), because the camera's own
  sensor/exposure characteristics matter and a phone-filmed clip of the
  same scene didn't reproduce the failure. Can optionally record a
  held-out video via `--record-video`.
- `extract_tv_fire_frames.py` — extracts evenly-spaced frames (target 30)
  from a developer-recorded phone video of a laptop screen playing fire
  footage, for the TV/laptop-fire hard-negative category that couldn't be
  scraped.
- `review_hard_negatives.py` — a Streamlit app for manually
  approving/rejecting scraped images before `prepare_data.py` treats them
  as clean data (the DuckDuckGo scrape has a documented ~83% reject rate
  on some categories, e.g. "steam" matching keyword-only, no real vapor).
  Parameterized via `--target-dir` to review any similarly-structured
  scraped tree.
- `test_camera.py` — throwaway camera smoke test (opens the webcam, shows
  FPS-overlaid live feed, quits on `'q'`) predating `edge/camera.py`,
  used to confirm a camera was reachable before that module existed.
- `verify_env.py` — imports every major dependency from
  `requirements.txt` and prints a pass/fail table; exits non-zero on any
  import failure. Run after `setup.sh`/`setup.ps1`.

---

## `models/`

Gitignored (per `.gitignore`) but present locally — ONNX and PyTorch
model artifacts, checked by file type/size rather than opened directly.

- `fire_mnv3.onnx` (307KB) + `fire_mnv3.onnx.data` (5.8MB, external
  weights blob) — the **current production model** (v4, promoted
  2026-09-05, byte-identical to `fire_mnv3_v4.onnx` per `config.example.yaml`).
  Loaded by `edge/vision.py`'s `VisionModel` via the `model_path` key in
  `config.yaml`.
- `fire_mnv3_best.pt` (5.9MB) — the PyTorch checkpoint saved by
  `train/train_classifier.py` (best epoch by val accuracy), the direct
  input to `train/export_onnx.py`.
- `fire_mnv3_v1_backup.onnx`/`.onnx.data` — archived v1 ONNX export.
- `fire_mnv3_v2_superseded.onnx`/`.onnx.data`/`.pt` — archived v2
  checkpoint and export.
- `fire_mnv3_v3.onnx`/`.onnx.data`/`.pt` and
  `fire_mnv3_v3_superseded.onnx`/`.onnx.data`/`.pt` — v3 artifacts (two
  copies under slightly different names, both present).
- `fire_mnv3_v4.onnx`/`.onnx.data`/`.pt` — the v4 artifacts that
  `models/fire_mnv3.onnx` is a byte-identical copy of.

---

## `data/`

Gitignored (per `.gitignore`) but present locally. Root-level loose
files: `capture_preview.jpg` (a preview image, likely from
`scripts/capture_webcam_negatives.py`), `hard_negatives_review_state.json`
(persisted approve/reject state for `scripts/review_hard_negatives.py`),
`live_sensors.json` (the file `edge/livelog.py` writes and
`dashboard/backend/main.py` reads).

- **`data/train/`** — the actual training split written by
  `train/prepare_data.py`. `fire/` (5,064 files), `smoke/` (4,987 files),
  `neutral/` (8,627 files) — one subfolder per class, `torchvision.datasets.ImageFolder`-compatible.
- **`data/val/`** — the validation split, same class structure.
  `fire/` (894 files), `smoke/` (880 files), `neutral/` (1,522 files).
- **`data/dfire_raw/`** — a locally cloned copy of the D-Fire dataset
  repository (has its own nested `.git/`, i.e. a separate git repo
  checked out inside this one, not a submodule reference). Contains
  `data/{train,val,test}/{images,labels}` (43,054 files total across all
  three splits) in YOLO format, plus `utils/` and `figures/` from the
  upstream D-Fire repo. This is `train/prepare_data.py`'s `--dfire-dir`
  input.
- **`data/hard_negatives/`** — reviewed (kept) hard-negative images, one
  subfolder per scenario, all folded into the `neutral` class:
  `bright_light_textured_wall/` (30), `bright_light_textured_wall_webcam/`
  (60, self-filmed via `scripts/capture_webcam_negatives.py`),
  `car_lights_night/` (29), `red_orange_objects/` (37), `steam/` (36),
  `stove_cooking/` (26), `sunset_window/` (28), `tv_laptop_fire/` (30,
  self-filmed via `scripts/extract_tv_fire_frames.py`), `warm_lights/`
  (35).
- **`data/hard_negatives_rejected/`** — images from the same scraping
  process that failed manual review (`scripts/review_hard_negatives.py`),
  kept as a record rather than deleted: `bright_light_textured_wall_webcam/`
  (60, with a `take2/` subfolder), `red_orange_objects/` (30),
  `steam/` (19), `stove_cooking/` (4).
- **`data/additional_neutral_training/`** — a `bright_light_textured_wall/`
  subfolder with 1 file; a near-empty/placeholder addition.
- **`data/additional_fire_training/`** — extra small/localized-flame
  training images (see `scripts/fetch_small_flame_images.py`), folded
  into `fire` via `train/prepare_data.py --extra-fire-positive`.
  `scraped/` (44 files across matchstick/lighter/candle/gas-stove-flame
  categories), `scraped_rejected/` (68), `scraped_v2/` (92, a second
  scrape pass with `_v2` category suffixes), `scraped_v2_rejected/` (22).
- **`data/rejected_clips/`** — 1 file; rejected video clip(s) from a
  data-collection pass.
- **`data/adversarial_extra/`** — 1 file; an extra adversarial clip
  beyond the main `eval/adversarial/` set (referenced by
  `eval/run_eval.py --extra-video`).
- **`data/incidents/`** — not currently present as a populated directory
  in this snapshot beyond what's created at runtime; this is
  `cloud/uploader.py`'s local-fallback write location and
  `agent/server.py`'s snapshot save directory (`config.yaml`'s
  `agent.snapshot_dir`).

---

## `graphify-out/`

Generated knowledge-graph artifact directory produced by the `graphify`
skill against this repository (dated 2026-08-18, before most of the
project's later phases were built — see Notes).

- `GRAPH_REPORT.md` — the top-level summary report: corpus stats (10
  files, ~12,974 words at the time it was generated), graph stats (207
  nodes, 204 edges, 54 communities), and a list of community hub labels
  (e.g. "Edge Loop Architecture", "Agent Response Graph (LangGraph)",
  "Sensor Hardware & Pin Map") used for graph navigation.
- `graph.html` — an interactive HTML rendering of the knowledge graph.
- `graph.json` — the graph data itself (nodes/edges) in JSON.
- `manifest.json` — graphify run manifest/metadata.
- `cost.json` — token/cost accounting for the graphify extraction run.
- `.graphify_root`, `.graphify_labels.json`, `.graphify_python` — internal
  graphify state/marker files.
- `cache/ast/` — cached AST-parse data (48K), one subfolder
  `v0.9.46/` keyed by parser version; not opened (binary/cache content).
- `cache/semantic/` — cached semantic-extraction data (200K), one
  subfolder `pd5fd89c46bb5/` keyed by a content hash; not opened.
- `cache/stat-index.json` — a small cache index file (4K).

---

## Cross-references (verified by reading imports/paths)

- `edge/main.py` imports `Camera` (`edge/camera.py`), `VisionModel`
  (`edge/vision.py`), `SensorReader` (`edge/sensors.py`), `Level`/
  `compute_gas_high`/`fuse`/`load_gas_thresholds`/`temp_spiking`
  (`edge/fusion.py`), and `LiveLogWriter` (`edge/livelog.py`) — it is the
  sole integration point for all of `edge/`.
- `edge/vision.py` loads `models/fire_mnv3.onnx` (path from
  `config.yaml`'s `vision.model_path`) via `onnxruntime.InferenceSession`.
- `edge/main.py` POSTs to `agent/server.py`'s `/incident` endpoint (URL
  from `config.yaml`'s `agent.incident_url`), which invokes
  `agent/graph.py`'s `run_incident()`.
- `agent/graph.py` imports `compose_alert_text`/`compose_sms_text`
  (`agent/compose.py`), `send_twilio_alerts` (`agent/escalate.py`),
  `append_feedback` (`agent/feedback.py`), `find_nearest_fire_station`
  (`agent/locate.py`), `latest_update_id`/`poll_for_cancel`/
  `send_telegram`/`simulate_dispatch` (`agent/tools.py`), and
  `log_incident` (`cloud/uploader.py`) — confirming the full node wiring
  described in its own docstring.
- `agent/tools.py`'s `simulate_dispatch()` writes `dispatch_log.jsonl`
  (path from `config.yaml`'s `agent.dispatch_log`).
- `agent/feedback.py`'s `append_feedback()` writes `eval/alert_feedback.csv`
  (path from `config.yaml`'s `agent.feedback_log`), which
  `dashboard/backend/main.py`'s `/api/incidents` endpoint reads directly.
- `dashboard/backend/main.py` imports `find_nearest_fire_station` directly
  from `agent/locate.py` (reused verbatim, not reimplemented) for its
  `/api/fire-station` endpoint, and reads `data/live_sensors.json` (the
  file `edge/livelog.py` writes) for `/api/live-sensors`, and
  `eval/results.csv` (written by `eval/run_trial.py`) for `/api/trials`.
- `dashboard/frontend/src/api.js` calls the dashboard backend at
  `http://127.0.0.1:8001`; `dashboard/frontend/src/levels.js` explicitly
  mirrors `edge/fusion.py`'s `Level` enum ordering in a comment.
  `dashboard/frontend/src/formatTimestamp.js` explicitly mirrors
  `agent/compose.py`'s `natural_time_phrase()` convention.
  `dashboard/frontend/src/App.jsx` -> `Overview.jsx` reads
  `state.get("live_sensors")`/timestamps produced by `edge/livelog.py`.
- `train/prepare_data.py` imports `check` from `train/check_leakage.py`
  and `print_balance_table`/`save_balance_chart` from
  `train/data_report.py`; reads from `data/dfire_raw/data` and
  `data/hard_negatives/` by default, writes `data/train/`+`data/val/`.
- `train/train_classifier.py` imports from `train/metrics_report.py`;
  reads `data/train`+`data/val`, writes `models/fire_mnv3_best.pt` and
  `eval/confusion_matrix.png`/`eval/training_curves.png`.
- `train/export_onnx.py` reads a `.pt` checkpoint and `data/val`, writes
  an `.onnx` file under `models/`.
- `eval/run_eval.py` imports `VisionModel` directly from `edge/vision.py`
  (via `sys.path` manipulation) — reused, not reimplemented; its
  `ADVERSARIAL_DIR`/`run_video()` are imported in turn by
  `eval/votes_needed_sweep.py`.
- `eval/test_fusion.py` imports `Level`/`compute_gas_high`/`fuse`/
  `load_gas_thresholds`/`temp_spiking` directly from `edge/fusion.py`.
- `eval/threshold_sweep.py`, `eval/smoke_threshold_sweep.py`, and
  `eval/inspect_misclassified.py` all import `CHECKPOINT_PATH`/
  `load_model`/`run_inference` from `eval/val_inference.py`.
- `scripts/capture_webcam_negatives.py` imports `edge/camera.py` and
  `edge/vision.py` directly (reused verbatim per `info.md` 3.4).
- Every `agent/*.py` module that talks to an external API
  (`compose.py`, `escalate.py`, `tools.py`) calls `load_dotenv()` at
  import time to read `.env`; `dashboard/backend/main.py` calls
  `load_dotenv()` explicitly with an absolute repo-root path (a
  documented fix, since it imports none of the agent modules that would
  otherwise have loaded `.env` as a side effect).

---

## Notes / discrepancies

- **No Streamlit dashboard exists**, despite `plan.md` section 4.2's
  original repository-structure spec listing `dashboard/app.py` (a
  Streamlit app) and `requirements.txt`'s originally-planned dependency
  list including `streamlit`. Checked: `requirements.txt` at the repo
  root has no `streamlit` entry, and no `dashboard/app.py` file exists —
  the actual dashboard is the FastAPI (`dashboard/backend/main.py`) +
  Vite/React (`dashboard/frontend/`) pair built later, per `plan.md`'s
  own dated 2026-09-03 addendum instructing the backend to be "thin" and
  per the README's "Dashboard" section, which correctly describes the
  React/FastAPI pair rather than Streamlit. `plan.md`'s cut-list and Day
  11 prompt sections describing Streamlit were left unedited as
  historical record — this is a planned pivot, not an unnoticed gap, but
  the root `plan.md` structure diagram itself is now stale against the
  real tree.
- **`scripts/review_hard_negatives.py` is a Streamlit app** (`streamlit
  run scripts/review_hard_negatives.py`) even though `streamlit` is not
  in `requirements.txt` — this would fail to run in a fresh environment
  built strictly from `requirements.txt` unless `streamlit` is installed
  separately. This is a real, checkable gap between the documented
  dependency list and an actual script's requirements.
- **`data/dfire_raw/` contains its own nested `.git/` directory** — a
  full separate git repository checked out inside this project's tree,
  not a git submodule reference. Since `data/` is gitignored wholesale,
  this has no practical effect on FireWatch's own git history, but it is
  worth flagging as unusual repository structure.
- **`graphify-out/` predates most of the project.** `GRAPH_REPORT.md` is
  dated 2026-08-18 (day 0 of the 12-day build) and its corpus stats (10
  files, ~13k words) reflect only the very earliest scaffold —
  `edge/`, `agent/`, `dashboard/`, `train/`, and `eval/` as they exist
  today were mostly built after this graph was generated. It should not
  be treated as an up-to-date map of the current codebase (this
  `FILE_MAP.md` supersedes it for that purpose).
- **Three long "explained" markdown files at the repo root**
  (`agent_explained.md`, `fusion_explained.md`,
  `sensor_hardware_explained.md`) plus `report.md` are all untracked
  (`??` in `git status`) — they exist in the working tree but have never
  been committed. They are legitimate, substantive tutorial/report
  documents (verified by reading their content), not stray scratch
  files, but a reader relying on `git log`/`git show` for repo history
  would not find them.
- **`eval/results.csv` is also untracked** (`?? eval/results.csv`) despite
  being the "single source of truth for hazard/non-hazard trial outcomes"
  per `README.md`'s Evaluation section — it exists locally with real
  trial rows (confirmed by reading its contents) but has never been
  committed, so a fresh clone of the committed history would not have
  it. `.gitignore` does not exclude it, so this looks like it simply
  hasn't been staged/committed yet rather than a deliberate exclusion.
- **`.claude/` is present but empty** — no tracked files found under it.
- **`data/incidents/`** (the snapshot-save and S3-local-fallback
  directory referenced by `agent/server.py` and `cloud/uploader.py`) was
  not found as a populated directory in this snapshot of `data/` — it is
  created on demand (`mkdir(parents=True, exist_ok=True)`) by both
  writers, so its absence here simply means no incident has triggered a
  local-fallback or snapshot save recently, not a missing feature.
- **DHT22 / temperature sensor: consistently and correctly documented as
  cut**, not a silent gap. `arduino/sensor_node.ino` has no temperature
  code, `edge/sensors.py`'s docstring explicitly says temperature parsing
  was removed (not stubbed), and `edge/fusion.py`'s `temp_spiking()` is a
  permanent stub returning `False` with a docstring explaining fusion
  rule 2 is structurally present but unreachable in production. All
  three files, plus `README.md`, `plan.md`, and `info.md`, agree on this
  — a genuinely well-documented scope cut, not a discrepancy.
- **No dead/duplicate code or empty stray files were found** among the
  application source files actually read (`edge/`, `agent/`, `cloud/`,
  `dashboard/backend/`, `dashboard/frontend/src/`, `train/`, top-level
  `eval/*.py`, `scripts/*.py`, `arduino/*.ino`) — every `__init__.py` is
  intentionally empty (package markers), and every script's `__main__`
  block is either a real CLI entry point or an explicitly-labeled
  throwaway smoke test (e.g. `edge/camera.py`'s and `edge/vision.py`'s
  `if __name__ == "__main__"` blocks, `scripts/test_camera.py`).
