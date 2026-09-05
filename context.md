# context.md — fast context recovery

This file is regenerated, not appended to. It is a summary only — it may be
stale. **`logs.md` remains the source of truth.**

---

## 1. What FireWatch is

FireWatch is an IoT fire and gas hazard detection system with local edge
inference and agentic response, deadline 30 August 2026. Core deliverable
(plan.md §2): a laptop-hosted edge node with a webcam and an Arduino sensor
board detects fire or smoke locally, cross-checks it against gas and
temperature readings, and within 10 seconds produces a verified alert that
reaches a real phone and a logged simulated dispatch packet — with the
internet disconnected.

---

## 2. Corrected architecture (plan.md §1)

1. Simulated dispatch, full payload logged but never transmitted
2. Model runs locally on the edge device. Cloud logs and retrains only
3. Camera **plus** gas sensors, fused
4. **Laptop is the edge device.** Pi is optional stretch
5. Fine-tune pretrained MobileNetV3-Small
6. Agent handles **response only**, never detection
7. Threshold plus temporal smoothing
8. Hardcoded coordinates, GPS optional

**DHT22 is cut** (Phase 0g) — `temp_spiking()` stubbed always-False.

---

## 3. Current phase and status

From logs.md "Project state at a glance":

| Phase | Name | Status | Date | Key result |
|---|---|---|---|---|
| 0 | Scaffold and config | COMPLETE | 2026-08-18 | Folder tree + config.yaml, parses clean |
| 1 | Dataset preparation | COMPLETE (rebuilt 2026-09-04) | 2026-09-04 | Leak-free split (verified by name AND content): train 18,627 / val 3,287; 251 hard negatives, 8 categories (+bright_light_textured_wall 30, −4 mislabelled stove duplicates) |
| 2 | Model training | COMPLETE — **v4 PRODUCTION since 2026-09-05** | 2026-08-23; v3 promoted 2026-08-30; v4 trained 2026-09-04, **promoted 2026-09-05** | **v4 live in `models/fire_mnv3.onnx`** (== `fire_mnv3_v4.onnx`, sha `36de3559…`; v3 archived as `fire_mnv3_v3_superseded.*`). ONNX diff 5.99e-05 PASS. fire recall 0.9575 @ 0.30 (margin 0.75 — first widening), smoke recall 0.8511 @ 0.45 argmax-AND (**clears the 0.85 bar for the first time**), val acc 0.9129, held-out bright-wall webcam clip smoke-frame rate 98.0% → 0.0%, no adversarial regression. Training data includes people in frame — **developer decision: keep, disclose** (not "clean"). **Live wall re-check on v4 PENDING.** See §4 item -17 |
| 3 | Edge loop v1 | COMPLETE | 2026-08-24 | camera.py + vision.py + main.py, live webcam test passed |
| 4 | Temporal smoothing | COMPLETE | 2026-08-26 | TemporalVoter (5-of-8, tau=0.70) live; alarm in ~0.17s; FPS 29.5-30.5 |
| 5 | Adversarial evaluation | PARTIAL — functionally closed | 2026-08-30 | 4/5 pass. TV/laptop-fire (7 alarms vs <=2) = documented limitation, mitigated by fusion rule 4's vision-only WARNING cap (live-confirmed Phase 7) |
| 6 | Arduino and sensors | COMPLETE | 2026-08-31 | H1-H9 (H7 skipped). MQ calibration real, thresholds live in config.yaml |
| 7 | Fusion logic | COMPLETE | 2026-08-31 | Live end-to-end Test B: WARNING→CRITICAL (rule 1, gas-confirmed — core safety claim), rule 3 fallback, de-escalation cycles, buzzer sounding throughout, FPS 29.5-30.0 |
| 8 | Agent part 1 | COMPLETE — developer-verified live 2026-09-02 | 2026-09-02 | LangGraph agent + Telegram + 30s reply-CANCEL + simulate_dispatch + main.py POST wiring |
| 8b | Agent part 2 | **BUILT 2026-09-02 — developer live verification PENDING** | 2026-09-02 | Twilio informational SMS-only (own number only; **voice call dropped from scope** — Twilio trial-tier "press any key" gate defeats an informational call), Overpass display-only lookup (406 fixed + re-confirmed), RL-shaped feedback CSV. Needs: developer live drill runs. See §4 |
| 10 | Cloud (S3 dispatch upload) | **COMPLETE — developer-verified live 2026-09-03** | 2026-09-03 | `cloud/uploader.py` log_incident(), wired into BOTH graph.py terminal nodes (`simulate()` and `cancelled()`), **CRITICAL-level only, both outcomes** (WARNING never uploads either way; CRITICAL uploads whether or not the owner cancelled — so the S3 corpus covers false alarms too, for log review/model performance). Four cost-safety measures: single-fire-per-node-per-incident, session upload-count circuit breaker (`aws.max_uploads_per_session: 50`), no retry, bounded packet/JPEG size. **Live-verified via real S3 console check:** one CRITICAL object confirmed in `firewatch-dispatch-arnav` under `device_01/2026/09/02/...`, content matches `dispatch_log.jsonl` format, SIMULATED:true + no-contact note both present; cancelled-CRITICAL archival also confirmed (uploads on both timeout AND cancel, cancelled events excluded from dispatch_log.jsonl but archived to S3 with owner_response text, exactly one upload per incident, WARNING never uploads). See §4 |
| 11 | Dashboard and evaluation | **PARTIAL — dashboard built 2026-09-03, ember brand pivot + accessibility/card-variety pass 2026-09-04, developer live verification PENDING; trial-logging helper built 2026-09-03; actual evaluation trials NOT STARTED** | 2026-09-04 | **Architecture changed from plan.md's Streamlit to React + FastAPI, developer instruction** — `dashboard/backend/main.py` (new, independent FastAPI app, port 8001, read-only GET-only) serves `/api/incidents` (alert_feedback.csv), `/api/s3-archive` (all `device_XX/` prefixes, graceful error not 500), `/api/trials` (results.csv or explicit not-found), `/api/fire-station` (reuses `agent/locate.py` verbatim). `dashboard/frontend/` is a new Vite+React app, liquid-glass dark theme (ember-amber brand, 2026-09-04 pivot), plain CSS, Plotly.js charts, 5 tabs (Overview/Live Incidents/Historical Archive/Evaluation Trials/Nearest Fire Station). Latest pass (2026-09-04): full WAI-ARIA tab semantics + keyboard-operable incident cards + icon-backed hazard badges (accessibility fixes from a self-audit), plus per-card visual variety (title icons, priority/quiet metric-card weighting, horizontal `.panel-row` layout variant, cool-tint accent for non-hazard location cards) — see logs.md "Phase 11 accessibility fixes + card-level visual variety pass". `requirements.txt`'s `streamlit` removed. `eval/run_trial.py` (new) is a companion CLI that launches `edge/main.py` as a subprocess and reads its existing stdout to log one row per trial to `eval/results.csv` (info.md 4.4 schema: trial_id/timestamp/trial_label/expected_outcome/actual_outcome/detection_latency_seconds/pass) — zero changes to main.py's detection/fusion code. See §4 |
| 12 | Documentation | NOT STARTED | — | — |

---

## 4. Most recent key decisions (newest first)

-17. **v4 PROMOTED TO PRODUCTION (2026-09-05) — logs.md "Phase 2
    addendum — v4 promotion decision":** promotion was first held
    because the developer's message carried a placeholder where the
    `export_onnx.py` diff should have been; the developer then supplied
    it — **max |PyTorch − ONNX| logit diff 5.99e-05 on 32 real val
    images, PASS ≤1e-4** (same check as v1/v2/v3). The staged block
    was then run verbatim: v3 → `fire_mnv3_v3_superseded.pt/.onnx/
    .onnx.data` (sha `b15d96df…` preserved), v4 → `models/fire_mnv3.onnx`
    + `.onnx.data` (sha `36de3559…` / `06e77cc5…`, == the v4 files).
    `config.yaml` unchanged (`model_path` already the promoted path;
    0.30 / 0.45 re-verified on v4's sweeps). `edge/vision.py` untouched.
    Nothing deleted. **Remaining: live wall re-check on the promoted
    model.** Also in this entry: (a) people-in-frame decision RESOLVED — keep the 60 webcam
    hard negatives and the held-out clip as captured, with the
    developer and 1-3 other people visible in every inspected frame;
    disclosed plainly in logs.md and queued for the final report; this
    data must never be called "clean"/"controlled"/"background-only";
    (b) full v3-vs-v4 gate table recorded — every gate passes: fire
    recall 0.9541→0.9575 @ 0.30 (margin 0.41→0.75, first widening in
    four checkpoints), fire precision 0.8660→0.8664, smoke recall at the
    production argmax-AND@0.45 rule 0.8284→**0.8511 (first time over
    0.85)**, val acc 0.9031→0.9129, macro F1 0.8967→0.9065, sunset/
    steam/red-clothing 0 fire alarms unchanged, TV-fire 7→6 (still the
    documented limitation, rule-4 mitigated), candle 3→4 (expected to
    alarm), steam smoke-WATCH 21→5 events, held-out bright-wall webcam
    clip smoke-frame rate **98.0%→0.0%**, max p_smoke 0.838→0.478,
    max p_fire on the wall 0.578→0.194; (c) promotion block staged
    (v3 → `fire_mnv3_v3_superseded.*`, v4 → `fire_mnv3.onnx`, shasum
    expectations listed; `config.yaml vision.model_path` already points
    at `models/fire_mnv3.onnx`, no config edit needed); (d) live wall
    re-check protocol written with v3-failure vs v4-pass criteria.
    **Next action for the developer: the live wall re-check
    (`python edge/main.py`, activated shell) — see §7.**
-16. **v4 candidate prepared — bright_light_textured_wall hard
    negatives (2026-09-04, info.md 4.2 step 1; training NOT run):**
    live A/B confirmed the smoke WATCH false positive is the bright-lit
    textured wall/ceiling grid itself (developer in frame = SAFE,
    background alone = WATCH). Developer filmed 30.4 s
    (`data/additional_neutral_training/bright_light_textured_wall/
    IMG_6710.mov`); 30 frames extracted with the SAME
    `scripts/extract_tv_fire_frames.py` logic (new `--output-dir`/
    `--prefix` args, defaults unchanged) into
    `data/hard_negatives/bright_light_textured_wall/` (neutral). New
    `train/check_leakage.py` (name + content md5) closes the standing
    leakage-guard open item; `prepare_data.py --clean` now required to
    rebuild, refuses to append, runs the check last. **The content check
    found 4 stock photos byte-identical between `stove_cooking`
    (neutral) and `gas_stove_flame*` (fire)** — 3 cross-class in v3's
    train, 1 straddling train/val; resolved per plan.md 6.4 (stove
    flame = fire) by moving the neutral copies to
    `hard_negatives_rejected/`. Split rebuilt with v3's exact extra-fire
    args: 21,914 images, leakage PASS. `eval/run_eval.py` now reports
    smoke WATCH events / smoke-frame % / max p_smoke per clip and takes
    `--extra-video`. v3 eval PNGs preserved as `eval/*_v3.png`. **All
    v4 metrics NOT YET MEASURED; v3 still production; promotion NOT
    DECIDED** — developer runs the command block in logs.md "Phase 2
    addendum — bright_light_textured_wall hard negatives folded in".
-15. **Smoke temporal voting added (2026-09-04, closes tonight's live
    finding):** even with the 0.45 gate, WATCH fired on isolated,
    unsustained frames against a patterned background (wall panels,
    ceiling grid). Code read confirmed smoke BYPASSED the Phase 4
    TemporalVoter entirely — `predict_smoothed()` voted only on
    p_fire and `main.py` fed the raw per-frame `smoke` flag straight
    into `fuse()`. Fix per info.md 4.2 step 2 (temporal smoothing, no
    data/retrain): `TemporalVoter.update()` split into `cast(vote)`
    (the N-of-M window) + threshold wrapper; a second instance of the
    SAME class votes on smoke's argmax-AND flag; `fuse()` now takes
    `smoke_sustained`. New `config.yaml vision.smoke_votes_needed: 5`
    (equal to fire — smoke is also on the rule-1 CRITICAL path, the
    failure was single frames so any N≥2 clears it, no smoke sweep
    exists to justify another value; separate key for future sweeps).
    Status line now prints `p_smoke`/`smoke_votes`. Pure-logic voter
    check passed; **live re-check on the same patterned wall PENDING**.
    See logs.md "Smoke temporal voting".
-14. **Smoke decision threshold added, closes the "smoke threshold
    untuned" open item (2026-09-04):** live testing showed spurious
    "WATCH: possible smoke" at p_smoke 0.28-0.44 on a neutral scene —
    argmax with no threshold let smoke win 3-way splits. New
    `eval/smoke_threshold_sweep.py` (sibling of the fire sweep) run by
    the developer on v3: argmax smoke recall 0.8295 / FP 107; val FPs are
    confident (median P 0.69, only 4/107 under 0.50), so val can measure
    the recall cost but not the live gain. **Goals conflict:** only
    thresholds LOOSER than argmax (prob ≥ 0.30-0.40) clear the 0.85
    recall bar and they add 26-78 FPs; every FP-reducing threshold drops
    recall further. Developer chose **0.45 with argmax-AND rule** (smoke
    must win argmax AND P ≥ 0.45; 0.50 was recommended) — cost 1 val
    smoke image (recall → 0.8284), val FP unchanged, all observed live
    0.28-0.44 states removed by construction. `config.yaml
    vision.smoke_decision_threshold`, `edge/vision.py predict()` only;
    no retrain, no fusion/main.py change. See logs.md "Smoke decision
    threshold".
-13. **Phase 11 live fusion-level feed (2026-09-04, edge + backend +
    frontend, closes the standing "live-vs-stale" open item):**
    developer asked why the System Health gauge was stuck at 0% and
    directed that SAFE/WARNING/CRITICAL "all logs" should update live
    on the UI. Root cause: `alert_feedback.csv` (`/api/incidents`) is
    the agent's CANCELLED/TIMEOUT outcome log — `edge/main.py`'s
    `notify_agent()` only fires `if level >= Level.WARNING`, so SAFE/
    WATCH never produce a row, and the old health gauge/stat-pill built
    on that data had no way to ever show recovery. **Did NOT make
    notify_agent fire on every frame** (it does a JPEG encode + network
    POST, gated to WARNING+/60s specifically to protect the 30 FPS
    safety requirement) — instead extended `edge/livelog.py`'s already-
    unconditional, already-cheap 1 Hz `record()` (built in an earlier
    Phase 11 pass specifically as the safe-for-the-hot-loop path) to
    also stamp the fused `level` (SAFE/WATCH/WARNING/CRITICAL, all
    tiers) onto each live sample — `level.name` passed through from the
    SAME `fuse()` call already made that iteration, no second fusion
    implementation. `/api/live-sensors` needed no backend change (reads
    the live-log JSON verbatim). `Overview.jsx`'s System Health hero and
    fusion-timeline stat pill now both prefer the freshest live sample's
    level when present, honestly labeling "current" (live) vs.
    "last incident" (fallback, no live feed) rather than guessing.
    `ast.parse` clean on all three touched Python files; `npm run build`
    + `oxlint` clean. **FPS/buzzer-latency re-verification REQUIRED
    before building further on this** — `edge/main.py`'s hot loop was
    touched (one extra string argument on an existing unconditional
    call), and this project's standing rule requires a live re-check
    after any edge-loop touch, not just a syntax check. See logs.md
    "Phase 11 live fusion-level feed — closes the live-vs-stale open
    item".
-12. **Phase 11 fusion-timeline layout bug fix (2026-09-04, developer
    caught via screenshot):** the prior chart-panel redesign left a
    stale `height: 100%` on the fusion timeline's card (a leftover from
    before it had a header row, when the panel was just a bare title +
    320px chart) — this forced the card to stretch to match the taller
    right-hand stack column while the chart itself stayed a fixed
    260px, producing a large dead gap below the plot and making the
    header+chart read as cramped at the top. Removed `height: 100%`;
    confirmed safe since the right column sizes independently via
    flex+gap. Also relabeled the header stat pill "current" →
    "last incident" — it was showing `mostRecent.level` (the latest
    logged incident), not a live status, so an old stale incident could
    misleadingly read as happening right now. **Real live-vs-stale
    fusion status is NOT yet implemented** — the backend has no live
    fusion-level endpoint (only raw mq2/mq135 via `/api/live-sensors`),
    so this needs either a new backend signal or a defined staleness
    rule before the pill can honestly say "LIVE: SAFE" vs. showing
    history; flagged as an open item rather than faked. `npm run build`
    + `oxlint` clean. **Visual result unseen — developer must
    re-verify.** See logs.md "Phase 11 fusion-timeline layout bug fix".
-11. **Phase 11 chart-panel redesign: fusion timeline + live sensor
    chart (2026-09-04, pure frontend):** developer feedback that these
    two Plotly panels still looked like generic chart-library
    containers and felt too heavy on Overview. Both panels gained a
    real header (icon+title + a compact live-stat pill — current
    fusion level; latest MQ-2/MQ-135 readings), a `.chart-glow-well`
    ambient radial glow behind the chart area (data-driven on the
    fusion chart — tracks the current level color live; steady
    steel-blue on the sensor chart, deliberately NOT data-driven since
    raw ADC values aren't themselves a hazard signal), a soft
    `fill: "tozeroy"` area tint under each line trace, and both charts'
    height cut 320px→260px to reduce visual weight. The sensor chart
    also swapped Plotly's default legend box for a hand-built
    `.chart-legend` (dot + small-caps label) and picked up
    `.glass--cool` (steel-blue border glow, same "instrument data, not
    hazard signal" language as the Fire Station cards). No new color
    hues introduced — reuses `levels.js` colors and the existing
    MQ2/MQ135 tones. `npm run build` + `oxlint` clean, zero new
    warnings. **Visual result unseen — developer must view in a
    browser.** See logs.md "Phase 11 chart-panel redesign — fusion
    timeline + live sensor chart".
-10. **Phase 11 accessibility fixes + card-level visual variety pass
    (2026-09-04, pure frontend, no backend/edge changes):** self-audit
    against `/frontend-audit-design`'s pre-delivery checklist found four
    accessibility gaps, all fixed: `Tabs.jsx` now has full WAI-ARIA tab
    semantics (`role="tablist"/"tab"/"tabpanel"`, `aria-selected`,
    roving tabindex, arrow-key navigation); `LiveIncidents.jsx` cards
    are keyboard-operable (`role="button"`, `tabIndex`, `onKeyDown`);
    `LevelBadge.jsx`'s WARNING/CRITICAL badges now carry an icon (not
    color/animation only); dead `.clickable-row` CSS deleted. Separately,
    developer feedback that every card looked visually identical despite
    the new ember palette drove a card-level variety pass: new
    `src/components/icons.jsx` (hand-written inline SVGs, no new
    dependency), per-card title icons everywhere, `.metric-card--priority`
    (CRITICAL count, conditional on >0) / `.metric-card--quiet` (Cancel
    rate) weight tiers, a horizontal `.panel-row` layout variant (Most
    Recent Event, Fire Station cards) replacing the repeated stacked
    label-above-value pattern, and a `.glass--cool` steel-blue accent for
    the Fire Station cards (non-hazard location data, deliberately
    distinct from ember data cards, still nowhere near `levels.js`'s
    fusion-status colors). `npm run build` + `oxlint` clean, zero new
    warnings. **Visual result unseen — developer must view in a
    browser.** See logs.md "Phase 11 accessibility fixes + card-level
    visual variety pass".
-9. **Phase 11 brand-identity pivot: warm ember palette + typography
    (2026-09-04, developer-requested, pure frontend):** replaced the
    dashboard's neutral chrome accent from blue-cyan to amber-ember
    (`#f59e0b`/`#dc2626`) across every tab — gradient card borders,
    tab/focus/hover glows, skeleton shimmer, chart gridlines, background
    radial glow — with base background moved from near-black navy to
    true warm charcoal/ash. Reasoning: "FireWatch" is a fire-safety
    product: cool blue-cyan chrome and the hazard vocabulary (already
    yellow/amber/red) had no thematic link; ember chrome unifies the
    whole interface under one warm identity while the hazard colors
    still visually out-escalate ambient warmth. **Fusion-level status
    colors in `levels.js` are completely unchanged** (SAFE green, WATCH
    yellow, WARNING/CRITICAL amber/red) — the one deliberately
    untouched piece, so hazard signal is never ambiguous with the new
    decorative chrome. Typography: Oswald added as a display face for
    the "FireWatch" wordmark only (body/data text unchanged); metric-
    number-to-label size/weight contrast increased dashboard-wide.
    `npm run build` + `oxlint` clean, no new warnings; full grep sweep
    confirms no leftover cool-toned literals outside comments. **Visual
    result unseen — developer must view in a browser.** See logs.md
    Phase 11 "brand-identity pivot" entry.
-8. **Phase 11 dashboard frontend design pass — Vision UI structure +
    liquid-glass execution (2026-09-03, pure frontend, no backend/edge
    changes):** full glass design system in `index.css` (blur(22px+)
    glass cards, gradient-ring border, specular top-highlight, large
    continuous radii, hover lift + glow, pulsing CRITICAL glow) applied
    across every tab. New: `LiveSensorChart` (mq2/mq135 from
    `/api/live-sensors` with dotted threshold lines, 3s poll, Overview
    tab only), `StateCard` (shared glass empty/error/offline state,
    replacing plain text everywhere), `CountUp` (metric-card number
    animation). `LiveIncidents` tab **replaced its filterable table with
    a feed-style card list** (developer decision: replace, not toggle) —
    filters unchanged. Overview gained a compact fire-station card
    reusing the existing `/api/fire-station` poll (no second lookup).
    Explicitly a synthesis, not a clone of either reference — see logs.md
    for the full breakdown. `npm run build` + `oxlint` clean, no new
    warnings. **Visual result unseen — developer must view in a browser**,
    see logs.md "How to verify".
-7. **Phase 11 dashboard bug fixes + live-sensors feed (2026-09-03):**
    (a) S3-archive "Unable to locate credentials" root cause:
    `dashboard/backend/main.py` never called `load_dotenv()` at all (the
    agent modules that proved AWS working each load .env themselves and
    none is imported by the dashboard) — fixed with
    `load_dotenv(_REPO_ROOT / ".env")`, `_REPO_ROOT` from `__file__`;
    config.yaml/CSV/live-log paths also anchored there (cwd-independent).
    (b) /api/fire-station "could not be determined" root cause: it DOES
    reuse `agent/locate.py` verbatim (live-confirmed working — Goregaon
    Fire Station, 1.35 km), but `_fire_station_cache` cached the first
    result unconditionally, so one transient Overpass failure stuck for
    the process lifetime — now caches only `found: True` results.
    (c) NEW `edge/livelog.py` + minimal `edge/main.py` wiring: 1 Hz
    mq2/mq135/p_fire samples via SimpleQueue → daemon writer thread →
    atomic-replace `data/live_sensors.json`, rolling 600 samples
    (config.yaml `live_log:` block). Main-loop cost measured 0.16 µs/frame;
    `record()` placed dead last in the iteration, after alarm+network.
    NEW `/api/live-sensors` returns `{ok, reason, readings[], thresholds{
    mq2_warn, mq2_danger, mq135_warn, mq135_danger}}`. **Developer
    re-verification of FPS (29.5-30) and buzzer latency REQUIRED and
    PENDING before this is safe to build on** — see logs.md Phase 11
    addendum "How to verify". Frontend live-chart tab not built.
-6. **Phase 11 trial-logging helper built, subprocess + stdout-parsing
    approach (2026-09-03, developer instruction to not touch
    `edge/main.py`):** `eval/run_trial.py` launches `python edge/main.py`
    as a real subprocess (cwd = repo root) and parses the fusion level off
    its own existing `format_status()` stdout lines — never imports or
    reimplements fusion/detection logic, never modifies main.py. CLI:
    `--label` (free text) + `--expected` (SAFE/WATCH/WARNING/CRITICAL);
    optional `--target-level` for latency-to-a-specific-level. Logs
    `trial_id, timestamp, trial_label, expected_outcome, actual_outcome,
    detection_latency_seconds, pass` to `eval/results.csv`, append-only,
    header written on first run only. `pass` allows a documented
    adversarial bound (info.md 4.2 TV-fire: WARNING acceptable, CRITICAL
    fails) via a small `ACCEPTABLE_BOUNDS` dict, not auto-derived.
    **Schema cross-checked against the dashboard** (developer instruction):
    `/api/trials` does a schema-free `csv.DictReader` passthrough, but
    `EvaluationTrials.jsx` had guessed `row.outcome ?? row.alarm` for its
    chart before this script existed — fixed the frontend to
    `row.actual_outcome` rather than rename the CSV; **`eval/run_trial.py`'s
    columns are now the schema source of truth**. No trials run yet — see
    logs.md Phase 11 trial-helper entry and §7 open items.
-5. **Phase 11 dashboard built as React + FastAPI, NOT Streamlit
    (2026-09-03, developer-instructed deviation from plan.md, flagged
    before building per info.md 1):** plan.md 4.3/8/9 all specify
    Streamlit for Day 11; developer explicitly asked for a thin
    read-only FastAPI backend (`dashboard/backend/main.py`, port 8001,
    a second independent FastAPI process from `agent/server.py`'s
    port 8000) plus a Vite+React frontend (`dashboard/frontend/`),
    reasoning: visual polish prioritized over build simplicity. Five
    tabs (Overview, Live Incidents, Historical Archive/S3, Evaluation
    Trials, Nearest Fire Station), dark Grafana/Datadog-style theme via
    hand-written CSS (no UI framework added), Plotly.js charts with a
    dark theme override, color language mirrors `edge/fusion.py`'s
    `Level` enum exactly (`src/levels.js`). `/api/fire-station` reuses
    `agent/locate.py`'s Overpass+101/112 logic unmodified — no second
    implementation. `/api/s3-archive` reads every `device_XX/` prefix,
    not hardcoded to `device_01/` (supports the Phase 10 close-out's
    fleet-monitoring idea). Poll cadences: incidents 5s, S3 30s,
    trials/fire-station on tab-focus (60s while active). `streamlit`
    removed from `requirements.txt`. **Verified so far:** Python
    `ast.parse` + import checks on the backend, a clean `npm run build`
    on the frontend (dist/ artifact deleted after). **NOT verified:**
    neither service has been started or viewed in a browser —
    developer will launch both themselves. See logs.md Phase 11.
-4. **Phase 10 CLOSED, developer-verified live (2026-09-03):** real S3
    console check confirmed a genuine CRITICAL incident object in
    `firewatch-dispatch-arnav` under `device_01/2026/09/02/...`, content
    matching `dispatch_log.jsonl` format, SIMULATED:true + no-real-contact
    note both correct. Cancelled-CRITICAL archival (both outcomes upload,
    cancelled events excluded from dispatch_log.jsonl but archived to S3
    with `owner_response: "cancelled by owner within window"`, exactly one
    upload per incident, WARNING never uploads) also confirmed working.
    Both of Phase 10's standing verification drills are done — no longer
    an open item. **File-length soft cap reviewed and deliberately NOT
    flagged as debt:** `agent/graph.py` at 325 lines exceeds info.md 3.3's
    ~200-line guideline, but on review a meaningful fraction of that
    length is docstrings/reasoning comments info.md 3.3 itself requires,
    and the file's actual responsibility (orchestrating agent response
    across Telegram/Twilio/Overpass/feedback/S3 through one fixed-edge
    state machine) was judged coherent enough not to warrant a forced
    split right now — a conscious decision, not an oversight. See logs.md
    Phase 10 closing entry.
-3. **Phase 10 CRITICAL upload extended to the cancelled path (2026-09-02,
    developer decision):** originally only `simulate()` (non-cancelled
    CRITICAL) uploaded to S3; developer asked to also cover
    `CRITICAL + cancelled` (false alarms at CRITICAL severity), since S3
    is the cloud log/retrain corpus and false alarms are exactly the hard
    cases worth having there for log review / model performance. Added
    `agent/graph.py`'s `_incident_packet()` (builds an S3-only packet, NOT
    routed through `tools.simulate_dispatch` — a cancelled event was never
    a dispatch, `dispatch_log.jsonl` still only gets genuine
    non-cancelled writes) and `_upload_critical()` (shared CRITICAL-gate +
    JPEG-read helper, called explicitly from both `cancelled()` and
    `simulate()` — two call sites, each still fires at most once per
    incident since the graph's terminal nodes are mutually exclusive).
    WARNING-level still never uploads, either outcome. See logs.md Phase
    10 addendum.
-2. **Phase 10 S3 upload gated to CRITICAL only (2026-09-02, developer
    decision):** plan.md's Day 10 prompt/original design implied
    uploading on every `simulate()` call (WARNING or CRITICAL timeout
    alike, matching `dispatch_log.jsonl`'s existing symmetry); developer
    explicitly chose CRITICAL-only for cost reasons — WARNING is frequent/
    expected (Phase 8's documented common template-fallback/timeout
    behavior), so it must never touch S3. Local dispatch log still fires
    for both levels unchanged. Four cost-safety measures built per
    developer's zero-tolerance requirement: single fire point (one call
    site in `simulate()`, unreachable more than once per incident — traced
    full graph, no back-edges/loops), session upload-count circuit breaker
    (`config.yaml` `aws.max_uploads_per_session: 50`), no retry (one
    attempt, log+return on failure), bounded file size (~700-900 byte JSON
    packet, single already-saved webcam JPEG, nothing accumulated). See
    logs.md Phase 10 for full detail.
-1. **Cancel window raised 30s -> 60s (2026-09-02, deliberate config
    change):** `config.yaml`'s `fusion.cancel_window_seconds` is now `60`
    — more realistic time to notice and respond to an alert across
    Telegram + SMS before simulated dispatch fires. The wait logic
    (`agent/graph.py` notify_owner/wait) already read this value from
    config dynamically, so no code change there; hardcoded "30-second"/
    "30s" text in `agent/compose.py`'s CRITICAL LLM prompt + deterministic
    template, and comments in `compose.py`/`locate.py`/`tools.py`/
    `server.py`, updated to "60" to match. SMS character budget
    re-confirmed unaffected (SMS templates never mentioned a duration).
    Developer live-timing verification PENDING. See logs.md "Cancel
    window: 30s -> 60s."
0. **Twilio voice call dropped from scope, SMS-only (2026-09-02, argued
   scope change, not silent removal):** live testing showed Twilio
   trial-tier accounts gate every call behind an interactive "press any
   key to accept" prompt before any custom TwiML plays — defeats the
   point of a one-way informational alert call; not worth a paid-account
   upgrade for a prototype. SMS is unaffected by this gate and stays in
   scope, fully working. `agent/escalate.py`'s call-placing code is
   commented out in place (not deleted) for a possible future revisit;
   `send_twilio_alerts()` now always returns `call: False`. The prior
   session's cancel-window extension (base 30s + estimated call-speech
   duration) is reverted — `agent/graph.py`'s `wait` node is back to the
   flat `fusion.cancel_window_seconds` (now 60s as of the 30s->60s change
   above), since no call is ever placed to extend it against. See logs.md
   Phase 8b addendum "Twilio voice call dropped from scope."
1. **Phase 8b BUILT, unverified (2026-09-02):** graph is now verify→locate→
   compose→notify_owner→escalate→wait→{cancelled|simulate}, feedback row
   appended in both terminal nodes.
   - `agent/locate.py`: Overpass `amenity=fire_station` lookup, once per
     incident, haversine-nearest, graceful fallback dict on ANY failure
     (including the still-placeholder 0.0/0.0 coordinates — it refuses to
     query Null Island). DISPLAY-ONLY: station name/number is alert
     content on all channels, NEVER a dial target (info.md 2.1). **406
     root-caused and fixed (Overpass blocks generic User-Agent strings;
     fix adds a descriptive UA + `raise_for_status()`), live-verified
     returning a real named station — see §4 item 0's neighboring
     addendum entries in logs.md.** On genuine lookup failure, the
     fallback line now cites real national emergency numbers (Fire 101 /
     Unified 112, from `config.yaml`'s `emergency_fallback` block) instead
     of bare prose — still never a fabricated station, still DISPLAY-ONLY.
   - `agent/escalate.py`: Twilio **SMS only** (voice call out of scope,
     see item 0 above) via REST/`requests` (no SDK dependency), strictly
     to TWILIO_TO_NUMBER (developer's own phone). One-way informational —
     **Telegram remains the ONLY cancel/confirm mechanism** (permanent
     decision; no IVR/`<Gather>`/webhook, ever). Reuses compose's text —
     no second LLM call. SMS explicitly states the system will not
     contact the fire station. Runs AFTER Telegram so a Twilio failure
     can never delay the primary channel. Real-cost service.
   - `agent/feedback.py`: append-only `eval/alert_feedback.csv`, schema
     METADATA/STATE/ACTION/OUTCOME+REWARD as designed 2026-08-31.
     **Reward mapping decided + flagged:** CANCELLED→−1, TIMEOUT→+1
     (implicit confirmation) — flagged that TIMEOUT is weak evidence and
     0 is arguably better; raw `outcome` column makes remapping lossless.
     Awaiting developer verdict. DATA COLLECTION ONLY — no RL built.
2. **Phase 8 CORE closed (2026-09-02):** both drills developer-confirmed
   live. WARNING: template fallback via strict time-phrase guard
   (expected, accepted design — frequent template fallback is NOT a bug),
   timeout → simulated dispatch. CRITICAL: complete urgent message,
   CANCEL correctly logged, no dispatch. Two bugs fixed same session:
   gpt-oss reasoning-token truncation (max_tokens 200→1024 +
   finish_reason guard) and vague "just now" timestamps (always concrete
   clock time now, required verbatim in LLM output).
3. **Groq model is `openai/gpt-oss-20b`** (llama-3.1-8b-instant deprecated
   2026-08-16; still free, 1,000 req/day). Telegram messages carry NO raw
   technical values — composed sentences + station line + cancel
   instruction only.
4. **Message-tone decision (2026-09-02, argued):** WARNING wording is
   honestly uncertain (real-early-fire vs TV false trigger
   indistinguishable), CRITICAL urgent/direct. Wording only — buzzer
   sounds on BOTH tiers.
5. **Fire station name/number IN alert content, both channels
   (2026-09-01):** Telegram body + Twilio TTS/SMS; never auto-dialed.

---

## 5. Real measured values (logs.md "Live values" + phase results)

| Value | Current |
|---|---|
| **Production model** | **v4 since 2026-09-05** (`models/fire_mnv3.onnx` == `fire_mnv3_v4.onnx`, sha `36de3559…`; `.data` `06e77cc5…`; `fire_mnv3_v4.pt` epoch 10/12). Own leak-free split train 18,678 / val 3,296 (neutral 1,522 / smoke 880 / fire 894). **val acc 0.9129; fire recall 0.9575 @ 0.30 (margin 0.75), precision 0.8664; smoke recall 0.8511 @ 0.45 argmax-AND (0.8545 argmax), smoke FP 109; macro F1 0.9065. ONNX diff 5.99e-05 PASS.** Training webcam negatives contain people in frame (disclosed, kept) |
| **Archived v3** (`fire_mnv3_v3_superseded.*`, sha `b15d96df…`; production 2026-08-30 → 2026-09-05) | val acc 0.9031, fire recall 0.9541 @ 0.30 (margin 0.41), smoke recall 0.8284 @ 0.45 argmax-AND (below bar). Measured on a split later found to hold 4 mislabelled stove images (≤1 in val). Rollback reference, never deleted |
| `fire_decision_threshold` / tau / M / N | 0.30 / 0.70 / 8 / 5 |
| **`smoke_votes_needed`** | **5** (2026-09-04): smoke's per-frame flag now needs 5-of-8 votes (same window as fire) before `fuse()` sees it. Live effect NOT YET MEASURED |
| **`smoke_decision_threshold`** | **0.45** (2026-09-04): frame is smoke only if smoke is argmax winner AND P(smoke) >= 0.45. **Production v4 at this rule: smoke recall 0.8511 — clears the 0.85 bar** (re-verified on v4's sweep; 0.45 stays). Archived v3 was 0.8284 (below bar). Val FP 109 (v4) / 107 (v3) |
| Adversarial (production v4) | sunset/steam/red-clothing 0 fire alarms PASS; TV fire 6 (documented limitation, bar ≤2 never met, rule-4 mitigated); candle 4 (expected to alarm); steam 5 smoke-WATCH events (documented limitation, down from 21); held-out bright-wall webcam clip 0.0% smoke frames, 0 WATCH (people in frame — disclosed) |
| Adversarial (archived v3, for comparison) | sunset/steam/red 0 alarms; TV fire 7; candle 3; steam 21 smoke-WATCH; bright-wall webcam clip 98.0% smoke frames, 4 WATCH (the live failure) |
| Inference FPS | 29.5-30.5 rolling |
| MQ-2 baseline/peak, warn/danger | 57.1 / 252; 115.57 / 174.04 (calibrated, live) |
| MQ-135 baseline/peak, warn/danger | 51.1 / 210 (196 live Test B); 98.77 / 146.44 (calibrated, live) |
| `gas_warmup_seconds` | 240 (2026-08-31 developer decision) |
| `notify_cooldown_seconds` | 60 — consumed by main.py notify_agent() (buzzer has NO cooldown) |
| **Agent config** | `agent:` block — incident_url 127.0.0.1:8000/incident, groq_model openai/gpt-oss-20b, dispatch_log dispatch_log.jsonl, snapshot_dir data/incidents, **8b: overpass_url/radius 7000 m/timeout 8 s, twilio_timeout 10 s, feedback_log eval/alert_feedback.csv** |
| `.env` | GROQ/TELEGRAM verified (@designexperience_bot); **all four TWILIO_* verified present 2026-09-02** (never printed); **AWS_* confirmed working 2026-09-03** (real S3 upload succeeded — see Phase 10 closing entry; values never printed) |
| Phase 8 drills | Both CONFIRMED live 2026-09-02 (WARNING timeout→dispatch, CRITICAL CANCEL→no dispatch). **Phase 8b drills NOT YET RUN** |
| Phase 10 drills | Both CONFIRMED live 2026-09-03 (CRITICAL timeout→S3 upload, CRITICAL CANCEL→S3 upload with cancelled owner_response, no dispatch_log.jsonl line) |
| Alarm protocol / serial | 'A'/'S' → D8; `/dev/cu.usbmodem141011` @ 9600, `mq2,mq135` 1 Hz |
| Buzzer | Fusion-triggered sounding confirmed live 2026-08-31 (WARNING + CRITICAL) |
| Hazard-to-buzzer / phone-alert latency, offline test | NOT YET MEASURED / NOT RUN (Phase 11) |
| `location.*`, `temp_rise_rate` | **PLACEHOLDER — real coordinates needed from developer for 8b Overpass** |

---

## 6. Hardware status

| Item | Status |
|---|---|
| Arduino Uno | Working; Phase 7 'A'/'S' alarm sketch confirmed live |
| MQ-2 (A0) / MQ-135 (A1) | Wired, calibrated 2026-08-31; MQ-135 confirmed undamaged post-incident |
| Buzzer (D8) | Confirmed; fusion-triggered sounding confirmed live |
| DHT22 | CUT — temp_spiking stubbed False |
| LEDs / breadboard | Ordered, not received/wired (H3 red LED not re-confirmed) |
| Webcam | MacBook built-in, confirmed through Phase 5 |

---

## 7. Standing open items (carried forward)

- `agent/graph.py` at 325 lines exceeds the 200-line soft cap — this is
  now a REVIEWED, deliberate decision (2026-09-03, see §4 item -4), not
  an open item requiring action. Noted here only so a future session
  doesn't re-flag it as an oversight.
- **Phase 8b verification pending, developer-run:** set real
  `location.latitude/longitude` in config.yaml, then
  `python -m agent.graph warning` (time out → call+SMS+station line+
  feedback row TIMEOUT/+1) and `python -m agent.graph critical` (reply
  CANCEL → feedback row CANCELLED/−1, no dispatch). Twilio is real-cost
  per run. Trial accounts: verified numbers only, trial-notice prefix.
- Timeout-reward verdict open: +1 shipped as instructed default, 0
  flagged as arguably better; `outcome` column keeps remapping lossless.
- Full-pipeline live test (uvicorn + edge/main.py + real flame) not yet
  run; hazard-to-phone-alert latency NOT MEASURED — Phase 11.
- TV/laptop-fire block-bar failure: documented limitation, rule-4
  mitigated — report as limitation, not fixed.
- Fire recall margin trend 1.11→0.88→0.41 pts on v1→v3 — **CLOSED,
  production v4 widened it to 0.75 pts.** Keep watching on any future
  retrain.
- Smoke recall below the 0.85 bar — **CLOSED 2026-09-05 by the v4
  promotion** (0.8511 at the 0.45 argmax-AND rule; v3 was 0.8284).
  Stays in the final report as history.
- **Smoke temporal-voter live re-check: DONE 2026-09-04, failure
  reproduced on v3** (smoke_votes saturated 8/8, WATCH locked) — voter
  and threshold were shown not to be the lever; the v4 retrain is the
  fix. Superseded by the v4 live re-check below.
- `edge/vision.py` 263 / `edge/main.py` 236 lines (soft cap ~200) —
  docstring growth; add no more logic to either.
- File-length soft cap elsewhere (unaffected by the graph.py review
  above): `edge/main.py` 212, `edge/sensors.py` 206 — don't grow either.
- **Phase 11 dashboard built, developer verification pending
  (2026-09-03):** run `uvicorn dashboard.backend.main:app --port 8001`
  and `cd dashboard/frontend && npm run dev`, then view in a browser —
  see logs.md Phase 11 "How to verify" for exact expected behavior per
  tab. Neither service has been started yet.
- **SAFETY-CRITICAL re-verification REQUIRED (2026-09-03, extended
  2026-09-04 — edge/main.py touched twice for the live log):** developer
  must personally confirm (1) FPS still 29.5-30 via main.py's
  rolling-FPS line, (2) WARNING/CRITICAL test still sounds the buzzer
  with no added delay, (3) `/api/live-sensors` returns real advancing
  data **including the new `level` field per sample**, (4) S3-archive
  and fire-station endpoints now work. The 2026-09-04 touch is
  mechanically small (one extra `level.name` string argument passed
  into `live_log.record()`, already an unconditional per-frame call),
  but per this project's own rule any edge-loop touch needs a live
  re-check, not just a syntax check — until then this change is NOT
  safe to build on. See logs.md Phase 11 addendum and "Phase 11 live
  fusion-level feed" entry.
- `edge/main.py` now ~225 lines (soft cap ~200) — do not grow further;
  new live-log logic deliberately lives in `edge/livelog.py` (~120).
- **Phase 11 frontend design pass done, visual review pending
  (2026-09-03, extended 2026-09-04):** run
  `uvicorn dashboard.backend.main:app --port 8001` and
  `cd dashboard/frontend && npm run dev`, open the Vite URL in a
  browser — see logs.md "How to verify" for what to expect per tab
  (glass cards, gradient borders, live sensor chart, feed-style
  incidents, compact fire-station card on Overview) and the 2026-09-04
  entry's "How to verify" for the accessibility/card-variety pass
  specifically (arrow-key tab navigation, keyboard-operable incident
  cards, icon-backed hazard badges, priority/quiet metric-card weight,
  horizontal panel rows, cool-tint Fire Station accent).
- **Phase 11 evaluation trials — NEXT PRIORITY (promotion settled):**
  info.md 4.4's ≥20 hazard + ≥20 non-hazard trials, latency per trial,
  `eval/results.csv` — the logging helper (`eval/run_trial.py`) is
  built and ready (`python eval/run_trial.py --label <name> --expected
  <LEVEL>`). All trials run on production v4. Do the live wall re-check
  first since it uses the same `edge/main.py` session setup.
- Optional seeded `device_02/` fleet-monitoring demo (carried forward
  from Phase 10 close-out) not acted on — `/api/s3-archive` already
  groups by any `device_XX/` prefix present, so it's ready whenever/if
  the developer seeds one. MUST be disclosed as synthetic if done
  (info.md 2.4).
- Use an activated shell, not `conda run`, for live edge-loop testing.
- **v4 PROMOTED 2026-09-05 — retraining detour closed except for the
  live wall re-check (developer-run, PENDING):** `python edge/main.py`
  in an activated shell, same wall / same bright ceiling light as the
  2026-09-04 failure; one background-only pass + one in-frame pass,
  ≥90 s each (Arduino unplugged is fine). Pass = SAFE throughout, or an
  isolated self-clearing WATCH with `smoke_votes` never reaching 5;
  FPS still 29.5-30.5. v3 showed p_smoke 0.44-0.66, `smoke_votes` 8/8,
  WATCH locked. If WATCH still locks on v4, record it as a new open
  item (keep v4 on its val/adversarial merits; do not tune thresholds
  on the spot). Paste observed values for a short follow-up addendum.
- **Final-report disclosure (from the v4 detour):** bright-wall webcam
  hard negatives (60 frames) and the held-out clip include the
  developer and 1-3 other people in frame — kept by developer
  decision, never to be described as "clean"/"controlled"; the 98%→0%
  result is on that clip, not a background-only test. Also report:
  steam sustained smoke-WATCH (v3 21 / v4 5 events), TV-fire unchanged
  limitation, candle expected-to-alarm.
- Leakage guard CLOSED 2026-09-04 (`train/check_leakage.py`, run by
  `prepare_data.py`). Scrape scripts still have no cross-category dedupe.
- MQ-135 weak real-CO2 sensitivity; adversarial clip durations deviate
  from the 30s assumption — report notes.
- Personal stove-flame photos uncollected. `location.address` "NOT SET".
  `.env` AWS keys empty. Twilio real-cost — flag in cost docs (done in
  plan.md/logs.md; repeat in final report).
- `setup.sh`/`setup.ps1` only syntax-checked; stray `anthropic` package
  in conda env (harmless).

---

For full detail, reason, and history, read plan.md, info.md, and logs.md — this file is a summary only and may be stale.
