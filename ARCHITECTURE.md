# ARCHITECTURE.md — system map and document guide

Two things live here: a short recap of how FireWatch's runtime pieces fit
together, and a map of **every doc, log, and data file in this repo** —
organized by what it's for, and which one to open for a given task. The full
narrative for each stays in its own file; this page exists so you don't have
to guess which file that is.

---

## 1. Runtime architecture

```
 ESP32-CAM ──WiFi──► camrelay.py ──► vision.py (ONNX MobileNetV3-Small)
   (MJPEG)         (one upstream         ──► TemporalVoter (N-of-M) ──┐
                    conn, many                                         │
                    consumers)                                         │
                                                                       │
 ESP32 sensor ──WiFi POST──► wifi_source.py ──► gas_high = board's ────┼──► fusion.py
  (MQ-2/MQ-135     (1 Hz JSON)  (ingest in        own GAS_HIGH state    │        │
   + buzzer)                     edge/main.py)                          │        │
       │                                                                │        │
       └─ buzzes AUTONOMOUSLY off its own verdict, independent of        │        │
          WiFi and of this host entirely                                 │        │
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

**Transport (Phase 13f, 2026-09-23).** Both boards are WiFi; serial is no
longer the data path (it remains selectable via `sensors.transport` for
bring-up). Two deliberate asymmetries:

- The **sensor ingest server runs inside `edge/main.py`**, not the
  dashboard backend, so the detector never depends on an optional
  dev-time process.
- The **camera relay runs inside the dashboard backend**, so Live View
  keeps working when the edge loop is stopped. The edge loop reads frames
  *through* that relay (`camera.edge_source`) rather than connecting to
  the board, because `cam_node.ino` serves exactly one client at a time.

Neither path is on the safety path: the sensor board owns its buzzer and
sounds it with no host involvement, so a total network failure costs
telemetry, the dashboard and the agent notification — never the local
alarm.

**Design principle:** deterministic detection, agentic response. Detection
(model + threshold/vote logic) decides whether something is a hazard; the LLM
only ever phrases a sentence about a decision already made. See
[`README.md`](README.md#architecture) for the annotated version and
[`plan.md`](plan.md) §1 for the full rationale behind every choice here.

### Directory roles

| Directory | Role |
|---|---|
| `edge/` | Always-running local loop: camera, vision, sensors, fusion, buzzer/LED. Detection only — never calls out. |
| `agent/` | Response only, triggered after detection. LangGraph state machine, LLM compose, Telegram/Twilio, simulated dispatch. |
| `cloud/` | S3 archive upload, CRITICAL incidents only. |
| `dashboard/` | Read-only FastAPI backend + React frontend. Never writes to edge/agent state. |
| `train/`, `models/` | Dataset prep, training, ONNX export. `models/` is gitignored (checkpoints). |
| `eval/` | Adversarial video tests, threshold sweeps, per-trial logging. |
| `arduino/` | Firmware for each physical board (sensor node, cam node, calibration capture, buzzer test). |
| `tools/` | Standalone one-off scripts (sensor calibration) not part of the running system. |
| `scripts/` | Data capture / scraping / review helpers used during dataset building. |
| `data/` | Training data, captured clips, incident snapshots. Gitignored. |
| `logs/` | Local-only hardware trial logs and archived/superseded data snapshots (see §3). Gitignored. |

---

## 2. Project documents — which one to open

FireWatch tracks its own build process as deliberately as it tracks fire. Six
root-level docs form one system; **`info.md` §0 is the canonical read order**
— this table is the quick-reference version of it.

| Doc | Use it when... | Don't use it for... |
|---|---|---|
| [`info.md`](info.md) | Starting *any* session — operating rules, absolute safety constraints, doc authority order. Read first, always. | Current project state (that's `context.md`) |
| [`context.md`](context.md) | You need current-state orientation: phase, recent decisions, open items. Read this **second**, every session. Regenerated, not appended — may be stale; `logs.md` is the fallback source of truth. | Historical detail or exact past measurements (that's `logs.md`) |
| [`plan.md`](plan.md) | You need the specification: architecture rationale, hardware BOM/pin maps, data collection plan, schedule, troubleshooting appendix. This is the authority on *what should be true*. | A record of what actually happened (that's `logs.md`) |
| [`logs.md`](logs.md) | You need historical detail: exact past measured numbers, full reasoning behind a past decision, resolving a conflict `context.md` can't settle. Append-only, never overwritten — the record of *what was actually built*. Large; don't read by default (`info.md` §0). | Quick orientation (that's `context.md`) or the spec (that's `plan.md`) |
| [`report.md`](report.md) | Writing or referencing the final project report/deliverable (Phase 12). | Day-to-day build decisions — those belong in `logs.md` |
| `phase12.md` / `chat2.md` | Continuing the *current in-flight* hardware/architecture update (ESP32 migration). Session-scoped working checklists, not permanent project memory — they go stale and should be deleted or folded into `plan.md`/`logs.md`/`context.md` once that phase closes. | Anything that should outlive this one update phase |

**Authority order when sources conflict** (`info.md` §1): developer's current
message → `plan.md` (spec) → `info.md` (rules) → `logs.md` (history) → your
own judgment, last.

---

## 3. Logs and data — what's tracked, what's local-only

| Path | What it is | Written by | Tracked in git? |
|---|---|---|---|
| `dispatch_log.jsonl` | One JSON line per simulated dispatch — the permanent incident record | `agent/tools.py::simulate_dispatch()` | No (runtime data, gitignored) |
| `eval/results.csv` | Hazard/non-hazard trial outcomes and latency — source of truth for report numbers | `eval/run_trial.py` | No |
| `eval/alert_feedback.csv` | Append-only outcome log for agent responses | `agent/feedback.py` | No |
| `eval/calibration/*.csv` | Raw MQ sensor calibration measurements | `tools/calibrate_sensors.py`, `eval/calibrate_mq.py` | No |
| `data/live_sensors.json` | 1 Hz live snapshot for the dashboard's live chart | `edge/livelog.py` | No |
| `baseline_history.json` | Active MQ sensor boot-baseline tracking, current calibration session | Manually maintained (see `logs.md`) | No |
| `logs/hardware_trials/` | Superseded side-by-side comparison run logs (`esp32_run*.log`, `webcam_run*.log`, `continuous_log.csv`) — kept for the reasoning trail in `logs.md`, not live data | Manual capture during hardware trials | No (whole `logs/` dir gitignored) |
| `logs/archive/` | Superseded snapshots kept only for historical reference (e.g. `baseline_history_old_fixed_gate_*.json`) — explicitly retired, do not resume writing to these | Manual archival | No |

**Rule of thumb:** if a path is hardcoded in `config.yaml`/`config.example.yaml`
or read by running code, it stays where the code expects it (root or `eval/`,
`data/`, per the table above) — don't relocate those. Everything else that's
just a dated trial log or a "kept for reference" file belongs under `logs/`,
sorted into `hardware_trials/` (raw comparison runs) or `archive/` (explicitly
superseded, read-only history).

---

## 4. Adding a new log or doc

- **A new one-off hardware trial log?** → `logs/hardware_trials/`, and note
  the finding in `logs.md` (the log file itself is not the record — the
  reasoning in `logs.md` is).
- **A file being retired/superseded but worth keeping?** → `logs/archive/`,
  don't leave it at root.
- **A new session-scoped working doc** (like `phase12.md`)? → root is fine
  while the phase is active, but fold its conclusions into
  `plan.md`/`logs.md`/`context.md` and delete it once that phase closes —
  per its own stated rule.
- **Permanent project narrative?** → it almost certainly already has a home
  in one of the six docs in §2. Extend those before creating a new one.
