# FireWatch: steps to a publishable paper (Path 1)

Status as of 2026-10-29. **Approach:** keep the deployed v4 model as-is and evaluate it on a new, independent
test set that v4 never saw, recorded with the deployment camera (ESP32-CAM) in real rooms. No retraining.

Every step has: **why**, **how**, **done when**. You run every script and command yourself; this file only lists them.

---

## 0. Why Path 1 is valid, and what it requires

**What's wrong today:** v4's numbers (95.75% fire recall, etc.) come from a validation split that also chose the
checkpoint and the threshold. They're optimistic and can't be reported as results.

**Why we don't use D-Fire's test split:** it was pooled into v4's training (`docs/data_provenance.md` §2a),
so v4 has seen those images.

**Why a new test set fixes it:** v4 never saw any ESP32-CAM frame, and the new recordings happen after
v4 was frozen. A score on them is an honest estimate of real deployment performance. That's arguably
more useful than a D-Fire score, because it measures the actual camera in the actual rooms.

**Path 1 holds only if:**
1. The test sources are truly unseen: own ESP32-CAM sessions (main), plus optional public **video** datasets
   checked for near-duplicates against D-Fire (§3.2).
2. The fire threshold 0.30, smoke rule 0.45 and voter 3-of-8 are committed in `eval/paper/frozen_v4.yaml` before the first
   test run, and never change afterwards.
3. ≥300 fire, ≥300 smoke and ≥600 neutral test frames (≈ ±3.4 pt CI at 90% recall).
4. The fallback is fixed in advance (§16): if fire recall on test set C is below ~85%, fine-tune on *separate*
   training sessions, then test on sessions the fine-tune never saw.

**What Path 1 gives up (disclose in the paper):**
- No score on D-Fire's official test split, so no direct number-to-number comparison with D-Fire papers.
- v4's training isn't fully reproducible: 447 of 21,974 training images (scraped + self-captured)
  were deleted. D-Fire (98%) is re-downloadable.
- Some v4 training frames contain people (developer + colleagues). No training images are released.

| Blocker today | Fixed in |
|---|---|
| No held-out test set | §3, §4, §5 |
| Raw data deleted, risk of it happening again | §1 |
| Adversarial clips deleted (`eval/adversarial/` is empty) | §4 (recordings replace them) |
| No baselines | §5.3 |
| Fusion benefit unmeasured | §6 |
| Fail-safe claim unmeasured | §7 |
| 12 live trials, 1 small-flame session | §4, §6 |
| No auth on sensor ingest | §9.1 |

---

## 1. Data safety: never lose data again

### 1.1 Storage
- Store the raw clips (`data/test_raw/`) and the extracted frames (`data/test/`). At QVGA (320×240) the
  ESP32-CAM clips are small: a few MB per minute. All sessions should fit in a few GB.
- **Back up after every session** to two places (external disk + Google Drive or similar). Write the backup paths here.

### 1.2 Manifest
- `eval/paper/test_manifest.csv`: `path, sha256, session, clip_id, cls, category, distance, room, lighting`.
- Commit the manifest; don't commit the images (they're too large and gitignored).
- **Done when:** the manifest is committed and both backups exist.

### 1.3 Test set is write-once
- The manifest is committed **before** the first evaluation run. That commit is the proof that the test set
  wasn't chosen after seeing results.
- After that, frames are never added, removed or relabelled. If something is wrong, document it and report both versions.

### 1.4 Consent and people
- New recordings: no faces in frame (shoot from behind or from the shoulders down), or written consent plus blurring.
- For the paper's ethics statement: v4 training includes frames of the developer and colleagues; no training data is released.

---

## 2. Freeze v4

- **Why:** everything after this point measures a fixed system. Any change after seeing test data invalidates the test.
- **Written:** `eval/paper/frozen_v4.yaml` (2026-10-29) is the real freeze file. It also holds the tau 0.70 gate and
  `smoke_votes_needed: 5`, which the sketch below omits, and a `declared_amendments` list. Use the file, not the sketch.
- **How (sketch only):**
  ```yaml
  model: models/fire_mnv3_v4.onnx
  model_sha256: <sha256 of the onnx file>
  checkpoint_pt: models/fire_mnv3_v4.pt   # for Grad-CAM only
  fire_decision_threshold: 0.30
  smoke_threshold: 0.45            # argmax-AND rule
  voter: {votes_needed: 3, window: 8}
  fusion: edge/fusion.py @ <git commit>
  firmware: sensor_esp32_node @ <git commit>, cam_node @ <git commit>
  frozen_on: <date>
  ```
  ```bash
  shasum -a 256 models/fire_mnv3_v4.onnx
  ```
- Check that `config.yaml` points at exactly this model and these values.
- **Do the §9 hardening changes first** (auth, darkness gate, mDNS), because they change the system. Then freeze, then record.
  The darkness gate's thresholds must be chosen on non-test data (§9.4).
- **Done when:** `frozen_v4.yaml` is committed and its commit is older than session S01.

---

## 3. Test sets

### 3.1 Test set C: own ESP32-CAM recordings (main)

| Class | Categories | Frames per category | Total |
|---|---|---|---|
| fire | candle, lighter, gas_stove, matchstick, paper_in_metal_tray, small_distant_flame (3 m) | 50 | 300 |
| smoke | incense, extinguished_candle, smouldering_paper | 100 | 300 |
| neutral | empty_room, person (no face), red_clothing, tv_fire_footage, laptop_fire_footage, phone_fullframe_spoof, steam_kettle, sunset_window, warm_lights, darkness, bright_textured_wall, cooking_no_flame | ~50 | 600 |

- ≥6 sessions, ≥2 rooms (3 if possible), day and night. Every category appears in ≥2 sessions.
- How to record: §4. How to evaluate: §5.

### 3.2 Test set B: public video datasets (optional, cross-domain)
- **Why:** shows that results don't depend on one household and one camera.
- **Prefer self-recorded video datasets** (candidates: MIVIA fire/smoke videos, KMU fire & smoke). Avoid web-scraped image
  sets: they may share images with v4's deleted scraped images, which can no longer be checked.
- **Check licence and access** before using any of them. Record the dataset version and URL.
- **Leakage check:** re-download D-Fire (Kaggle `sayedgamal99/smoke-fire-detection-yolo`), compute `imagehash.phash`
  for D-Fire and for set B, and drop any set B frame within Hamming ≤ 6 of a D-Fire image. Report the count dropped.
  (D-Fire can be deleted again afterwards; keep only its hash list.)
- Map the dataset's labels to neutral/smoke/fire, and extract frames at ≤1 fps per video.
- **Done when:** set B has its own manifest, leakage report and frozen file list, like set C.

---

## 4. Recording runbook (test set C + system trials)

One recording serves three purposes: frame-level test set C, event-level detection and time-to-detection, and the
fusion ablation by replay (§6). Record it once, properly.

### 4.1 Rules that make the data valid
1. **Freeze first** (§2). No model, threshold, fusion or firmware changes until all evaluation is done.
2. **The edge loop runs during recording** (the sensor ingest lives in `edge/main.py`). You'll see live
   predictions on the dashboard. That's fine **as long as nothing is changed because of them**.
3. **Test sessions never feed training.** If the fallback (§16) needs fine-tuning data, record it in separate
   sessions named `T01, T02...`, never `S..`.
4. **TV/laptop fire footage must differ from training.** v4 trained on frames of one YouTube fireplace
   video (`IMG_6620.MOV`). Use ≥3 *other* videos (campfire, house fire news clip, candle video) and log their URLs.
5. **No faces in frame.**

### 4.2 One-time preparation (before session 1)

**Equipment**
- [ ] ESP32-CAM on a 5 V / 2 A supply (brown-outs corrupt frames); sensor board on its usual supply
- [ ] Fixed camera mount: tripod with a phone clamp, or tape it to a shelf. Same height every session (~1.2 m); note it
- [ ] Painter's-tape floor marks at **0.5 m, 1.5 m and 3 m** from the camera
- [ ] A phone light-meter app (lux per clip; nice to have)
- [ ] Safety: fire extinguisher or water bucket within reach, a metal tray or ceramic plate, a window you can open
- [ ] Props: 3+ candles, a lighter, matches, incense sticks, paper, a kettle, red clothing, a lamp, a laptop/TV with the fire videos ready, a phone showing a sunset photo

**Software**
```bash
pip install -q scikit-learn statsmodels imagehash
```
scikit-learn: ROC/PR/confusion/calibration. statsmodels: Wilson CI. imagehash: near-duplicate removal.
Add them to `requirements.txt` under an "evaluation" comment.

**Write `scripts/record_session.py`** (spec):
```
python scripts/record_session.py --session S03 --cls fire --category candle \
    --distance 1.5 --room bedroom --light lamp --seconds 45 [--lux 120] [--note "..."]
```
- Opens `cv2.VideoCapture("http://127.0.0.1:8001/api/camera/stream")` (the relay; same frames as live).
- Shows a preview window. **Press `e` at the moment of ignition or hazard start** (stores `event_start_ts`).
  Press `q` to stop early; otherwise it stops after `--seconds`.
- Writes into `data/test_raw/<session>/<cls>/<category>/`:
  - `<clip_id>.mp4` (`cv2.VideoWriter`, `mp4v`, at the measured stream FPS)
  - `<clip_id>_frames.csv` with `frame_idx, wall_ts` (needed to sync with gas readings; MJPEG FPS varies)
  - `<clip_id>_sensors.csv`: a background thread polls `GET http://127.0.0.1:8002/ingest` at 1 Hz →
    `wall_ts, mq2, mq135, state`
  - `<clip_id>.json`: every CLI argument, plus `start_ts, event_start_ts, end_ts, fps, n_frames`, the git commit and the firmware version
- Clip id format: `S03_fire_candle_d1.5_c02` (session_class_category_distance_clipnumber, auto-incremented).
- Dry-run it once at your desk: open the mp4 and check that the sensor CSV has ~1 row/s.

**Write `eval/paper/sessions.csv`** with the plan (session, date, room, lighting, planned categories); fill in actuals as you go.

### 4.3 Session plan

| Session | Room | Lighting | Focus |
|---|---|---|---|
| S01 | Room A | day (window light) | all categories, distances 0.5 / 1.5 m |
| S02 | Room A | night (lamp) | all categories, distances 1.5 / 3 m |
| S03 | Room B | day | all categories |
| S04 | Room B | night | all categories |
| S05 | Room A or C | mixed | categories still short of target |
| S06 | Room B or C | mixed | categories still short of target, plus darkness |

Kitchen sessions for gas_stove, steam_kettle and cooking_no_flame. After S02, count the frames per category and plan S05/S06 to fill gaps.

### 4.4 Session start checklist (~20 min)
1. Start the stack in separate terminals (the agent and the frontend aren't needed for recording):
   ```bash
   uvicorn dashboard.backend.main:app --port 8001
   python edge/main.py
   ```
2. Power the sensor board and **wait for its warm-up gate** to finish and capture a baseline
   (`curl -s http://127.0.0.1:8002/ingest` shows a normal state and published thresholds).
3. Check the camera: the relay stream is live and the image isn't tinted (GC2145 colour issue, `logs.md` 13a-2).
4. Photograph the setup with your phone: `S03_setup.jpg`.
5. Write the session row in `sessions.csv` (date, start time, room, lighting, lux, window open/closed).
6. Record a 30 s `neutral/empty_room` clip first: it's the session baseline.
7. Get the shuffled category order for the session (so time-of-day doesn't line up with category):
   ```bash
   python -c "import random; c=['candle','lighter','matchstick','paper_in_metal_tray','small_distant_flame','incense','extinguished_candle','smouldering_paper','person','red_clothing','tv_fire_footage','laptop_fire_footage','sunset_window','warm_lights','bright_textured_wall','darkness']; random.Random('S03').shuffle(c); print(c)"
   ```

### 4.5 Shot list (per session; each line = one clip of 30-60 s)

For hazard clips: start recording, wait ~5 s, then ignite or start and **press `e` at that moment**.
Move the object a little during the clip (position, angle) so the frames aren't all identical.

| Class | Category | What to do | Distances per session | Clips/session | Safety / notes |
|---|---|---|---|---|---|
| fire | candle | 1-3 candles on a plate, light on camera | 0.5, 1.5 | 2 | plate on a non-flammable surface |
| fire | lighter | hold lit, move slowly | 0.5, 1.5 | 2 | ≤10 s bursts, the lighter heats up |
| fire | matchstick | strike and hold until near the fingers, repeat | 0.5, 1.5 | 2-3 | drop into a water cup |
| fire | gas_stove | burner low → high | ~1.5 (kitchen) | 2 | kitchen sessions only |
| fire | paper_in_metal_tray | crumple A5 paper, light it in the tray | 1.5, 3 | 2 | **outdoors or a window open, water ready** |
| fire | small_distant_flame | a candle or lighter at 3 m | 3 | 2 | |
| smoke | incense | 2-3 sticks, smoke rising in view | 0.5, 1.5 | 2 | dark background helps; note it |
| smoke | extinguished_candle | blow out a candle on camera; record the smoke plume | 0.5 | 3 | short plume: several clips |
| smoke | smouldering_paper | paper tray fire smothered → smoke | 1.5 | 2 | **outdoors or ventilated** |
| fire | camphor_lit | one camphor tablet on a metal lid in camera view; **sensor board 0.5 m beside it, in its smoke path** | 1.5 (camera) | 3 | outdoors or very well ventilated; fumes irritate; ventilate to baseline between runs. Real fire + real smoke from one source: the CRITICAL test |
| neutral | camphor_unlit_control | an unlit tablet at the sensor for ~1 min | fixed | 1 | camphor vapour may move the MQ sensors on its own; report it |
| neutral | empty_room | nothing | fixed | 1 | the first clip each session |
| neutral | person | walk, sit, wave; no face | 1.5, 3 | 2 | |
| neutral | red_clothing | red or orange clothing, moving | 1.5 | 1-2 | |
| neutral | tv_fire_footage | a TV playing a fire video **not used in training** | 1.5, 3 | 2 | log the video URL in `--note` |
| neutral | laptop_fire_footage | the same, on a laptop screen | 0.5, 1.5 | 2 | another video |
| neutral | phone_fullframe_spoof | phone playing a real fire-disaster video, held so the screen fills the frame and no bezel shows | ~0.1-0.3 | 3 | **spoof test.** Expect vision alarms. Pass = fusion stays at WARNING, never CRITICAL, with no gas. Log the video URL; use a different phone distance each clip |
| neutral | steam_kettle | a boiling kettle, steam in view | ~1 (kitchen) | 2 | kitchen sessions |
| neutral | cooking_no_flame | an induction or electric hob, pan steaming | ~1.5 (kitchen) | 1 | kitchen sessions |
| neutral | sunset_window | a window at sunset, or a sunset photo on a phone/monitor | 1.5 | 1 | |
| neutral | warm_lights | warm bulbs, fairy lights, an orange lamp | 1.5 | 1-2 | |
| neutral | bright_textured_wall | a bright light on a textured wall or ceiling (v3's known failure) | 1.5 | 1 | |
| neutral | darkness | lights off, curtains closed | fixed | 1 | |

**Gas-only trials (for §6, not frame-level):** release lighter gas without a flame near the MQ-2 for ~5 s, with the camera on
an empty scene. 2 clips per session, category `gas_only`, class `hazard_gas`. Excluded from the frame-level test set.

**Between hazard clips:** ventilate until the sensor board is back to a normal state and MQ-2 is close to its baseline.
Note the wait in `--note`. Otherwise the next clip's gas readings are contaminated, and that ruins the fusion trials.

**Yield math:** 1 fps × ~40 s after the event ≈ 40 frames per clip. Near-duplicate removal cuts static scenes hard
(a still candle can lose 70%+). Plan for **2× the frames you need**: candle needs 50 → ~100 raw → ≥3 clips across ≥2 sessions.

**Time per session:** ~20 min setup, plus ~20 clips × ~1.5 min, plus ventilation waits ≈ **2-3 h**.

### 4.6 After each session (~10 min)
1. Copy `data/test_raw/<session>/` to both backups.
2. Count clips per category:
   ```bash
   find data/test_raw/S03 -name '*.mp4' | awk -F/ '{print $4"/"$5}' | sort | uniq -c
   ```
3. Fill in the actual end time and any problems in `sessions.csv`.
4. Don't run any evaluation yet. Evaluate once, after all sessions.

### 4.7 From clips to test set C (after all sessions)
1. **Extract frames.** Generalize `scripts/extract_tv_fire_frames.py` into `scripts/extract_test_frames.py`:
   - hazard clips (fire/smoke): only frames from `event_start_ts + 2 s` to the end, at 1 fps
   - neutral clips: the whole clip, at 1 fps
   - output: `data/test/<cls>/<category>/<clip_id>_<nnn>.jpg`
2. **Review** with `scripts/review_hard_negatives.py` (point it at `data/test/`). Rule: the label is what a human
   sees *in that frame*. Reject: flame or smoke not visible, smoke too faint to see, any face, corrupt frames.
   Rejects get moved to `data/test_rejected/`, never deleted. Count the rejects per category for the paper.
3. **Near-duplicates:** within each category, `imagehash.phash` Hamming ≤ 4 → keep the first.
4. **Count vs target** (§3.1). Short categories mean another session, before any evaluation.
5. **Manifest** (§1.2): commit it, and back up `data/test/` twice.
6. **Run the evaluation once** (§5).

---

## 5. Offline (frame-level) evaluation, metrics and figures

Inputs:
- `eval/test_set_results.csv` from `eval/test_set_eval.py` (`path, true_class, category, p_fire, p_smoke, pred_fire, pred_smoke`)
- `eval/paper/test_manifest.csv` (joined on `path` → session, distance, room, lighting)

Outputs: `eval/paper/figures/` (PDF for the paper, 300 dpi PNG for slides) and `eval/paper/tables/` (CSV + LaTeX).

### 5.1 Commands (you run)
```bash
python eval/test_set_eval.py --model-path models/fire_mnv3_v4.onnx
python eval/paper/make_figures.py --results eval/test_set_results.csv --manifest eval/paper/test_manifest.csv
python eval/paper/make_gradcam.py --checkpoint models/fire_mnv3_v4.pt --results eval/test_set_results.csv
```
Add a `--test-dir` / `--out` flag to `test_set_eval.py` so set C and set B each write their own results CSV.

### 5.2 What to produce

| # | Output | How | Note |
|---|---|---|---|
| T1 | **Main metrics table** | fire recall/precision, neutral FAR, smoke recall/precision, macro F1, accuracy. Each with a Wilson 95% CI **and** a session-bootstrap CI | the headline table |
| F1 | **Confusion matrix (3-class)** | predicted = fire if `pred_fire`, else smoke if `pred_smoke`, else neutral (check this precedence against `edge/vision.py`/fusion). `ConfusionMatrixDisplay`, counts plus a row-normalized version | |
| F2 | **ROC curves** | one-vs-rest: fire (`p_fire`), smoke (`p_smoke`); `roc_curve`, `roc_auc_score`. Frozen operating point (0.30 / 0.45) as a dot | AUC with a session-bootstrap CI |
| F3 | **Precision-recall curves** | `precision_recall_curve`, `average_precision_score`, operating point, plus a dashed line at the class prevalence | better than ROC under imbalance; main paper. ROC → appendix |
| F4 | **Reliability diagram + ECE** | `calibration_curve(y_fire, p_fire, n_bins=10)`; ECE = Σ (n_bin/N)·\|acc − conf\| | do the thresholds sit on meaningful probabilities? |
| F5 | **Per-category bar chart** | recall (fire/smoke categories) and FAR (neutral categories) with Wilson CI bars | the most informative figure: TV/steam/matchstick directly |
| T2 | Per-category table | the numbers behind F5, plus n | |
| T3 | Per-session / distance / lighting table | the metric grouped by manifest columns | robustness, or where it breaks |
| F6 | Threshold analysis | fire recall and FAR vs threshold on the test set, frozen 0.30 marked | label it **post-hoc analysis**; the reported result stays at 0.30 |
| F7 | **Grad-CAM grid** | §5.5 | qualitative only |
| T4 | Baselines table | §5.3 | |
| T5 | Model-history table | §5.4 | |

Repeat T1-F5 for set B if you use it.

### 5.3 Baselines (no training needed)

| Baseline | What | Why |
|---|---|---|
| Colour-rule detector | a classic RGB/HSV fire-pixel rule (fire if fire-coloured pixel fraction > k); fix k on the **v4 training-era val images or any non-test frames**, never on set C | shows a CNN is needed at all |
| v4 argmax | same model, plain argmax instead of the tuned 0.30 threshold / smoke rule | isolates the effect of the decision rule |
| Off-the-shelf public model (optional) | a published pretrained fire/smoke detector (e.g. a YOLO model trained on D-Fire with released weights). An image is positive if any box > its default confidence | an external reference point. Check the licence and note its training data |

Compare paired decisions with McNemar's test (`statsmodels.stats.contingency_tables.mcnemar`).

### 5.4 Model-history ablation (free: the old checkpoints exist)
- Run v1 (`fire_mnv3_v1_backup.onnx`), v2, v3 and v4 on set C with v4's frozen decision rule.
- Use `logs.md` and `docs/data_provenance.md` to state exactly what changed between versions (hard negatives,
  small-flame positives, webcam negatives). Then the table shows the measured effect of each data addition on
  independent data (e.g. matchstick recall v2 → v3, bright-wall FAR v3 → v4).
- This replaces a retraining ablation. Be clear that the versions differ in more than one thing if they do.

### 5.5 Grad-CAM (`eval/paper/make_gradcam.py`)
- Reuse `generate_gradcam()` and `save_gradcam_overlay()` from `eval/inspect_model.py` (the same pattern as
  `eval/scratch_stove_gradcam.py`). Grad-CAM needs gradients → use `models/fire_mnv3_v4.pt`, not the ONNX.
- First check that the .pt matches the ONNX (≤1e-4, as in the export parity check) on a few test images.
- Select automatically from the results CSV (no hand-picking, which would be cherry-picking):
  - True positives: the 2 highest-`p_fire` images per fire category
  - **False negatives**: the 4 lowest-`p_fire` fire images
  - **False positives**: the 4 highest-`p_fire` neutral images
  - Smoke: 2 true positives, 2 misses
- Target class: the predicted class for TP/FP; the fire class for FN (shows what the model looked at instead).
- One grid figure: rows = TP / FN / FP / smoke, each tile captioned with category and p.
- Say in the paper that Grad-CAM is a qualitative illustration, not evidence of causality.

### 5.6 Core of `make_figures.py`
```python
import numpy as np, pandas as pd
from sklearn.metrics import roc_curve, roc_auc_score, precision_recall_curve, average_precision_score, confusion_matrix
from sklearn.calibration import calibration_curve
from statsmodels.stats.proportion import proportion_confint

df = pd.read_csv(results).merge(pd.read_csv(manifest)[["path", "session", "distance", "lighting"]], on="path")
y_fire = (df.true_class == "fire").to_numpy()

def wilson(k, n):
    return proportion_confint(k, n, alpha=0.05, method="wilson")

def session_bootstrap(df, metric, n_boot=2000, seed=0):
    # frames within a session are correlated, so resample whole sessions
    rng = np.random.default_rng(seed)
    sessions = df.session.unique()
    vals = [metric(pd.concat([df[df.session == s] for s in rng.choice(sessions, len(sessions))]))
            for _ in range(n_boot)]
    return np.percentile(vals, [2.5, 97.5])

fire_recall = lambda d: d[d.true_class == "fire"].pred_fire.mean()
fpr, tpr, _ = roc_curve(y_fire, df.p_fire)
auc = roc_auc_score(y_fire, df.p_fire)
prec, rec, _ = precision_recall_curve(y_fire, df.p_fire)
ap = average_precision_score(y_fire, df.p_fire)
frac_pos, mean_pred = calibration_curve(y_fire, df.p_fire, n_bins=10)

pred = np.where(df.pred_fire, "fire", np.where(df.pred_smoke, "smoke", "neutral"))
cm = confusion_matrix(df.true_class, pred, labels=["neutral", "smoke", "fire"])
```
Repeat ROC/PR/calibration for smoke with `p_smoke`. Fix the seed and record it with the outputs.

### 5.7 Figure style (decide once)
- One colour per class (neutral / smoke / fire), the same in every figure, colourblind-safe.
- Single-column width 3.5 in, fonts ≥ 8 pt, vector PDF.
- Every caption states n, the test set and the session count.

---

## 6. System (event-level) evaluation: the paper's main result

### 6.1 Replay
- **Why:** the same recorded event gets replayed through different configurations, so the ablation is fair, and nothing
  depends on deleted clips any more.
- **How:** `eval/paper/replay.py` feeds each clip's frames (`.mp4` + `_frames.csv` timestamps) and its `_sensors.csv`
  through `edge/vision.py` + `TemporalVoter` + `fusion.fuse()`. Reuse `eval/run_eval.py`'s `build_model()`/`run_video()`;
  don't reimplement detection logic.
- **Done when:** replaying a clip reproduces the level sequence the live run printed for that clip (spot-check 3 clips).

### 6.2 Trials
- Every set C clip is a trial (whole clip, including the pre-event seconds), plus the `gas_only` clips.
- Ground truth: `event_start_ts` for hazard clips; neutral clips have no event.
- Aim for **≥15 clips per condition** across sessions (the §4.5 shot list × 6 sessions gets there for most conditions).

### 6.3 Fusion ablation (the main table)

| Config | What it is |
|---|---|
| Vision only, per frame | p_fire threshold, no voting |
| Vision + temporal voter | 3-of-8 |
| Gas only | board GAS_HIGH |
| Fusion (full system) | the actual `fuse()` table |

Per config: event detection rate, false-alarm rate (alarms per neutral clip, and per hour of neutral footage),
time-to-detection from `event_start_ts` (median, p95), and the highest level reached.
Use Fisher's exact test for FAR differences. Also report an N-of-M sweep (`eval/votes_needed_sweep.py`) as **post-hoc analysis**.

**Sample size reality:** with ~15 clips per arm, a FAR drop from 50% to 5% is detectable; from 20% to 10% it is not.
Report CIs and don't claim significance you don't have.

### 6.4 Long-run false-alarm test
- Run the full system for **≥24 h cumulatively** in normal rooms (cooking, people, TV on), with no hazards. Log levels.
- Report false alarms per 24 h at each level (WATCH / WARNING / CRITICAL).

### 6.5 Gas sensor characterization (partly done in `eval/calibration/`)
- Warm-up time to a stable baseline: curve plus median over ≥5 boots.
- Response time and peak ratio for lighter gas, incense smoke and cooking.
- Cross-sensitivity: breath, alcohol, perfume. MQ sensors are known not to be selective; show it in a table.
- Drift over ≥24 h and the drift-cap behaviour (`eval/test_drift_cap.py`).

---

## 7. Fail-safe evaluation: the novel claim

**Claim:** the local alarm happens before any network call, and no network or host failure can suppress it.

| Fault injected | How | Measure |
|---|---|---|
| None (baseline) | normal run | stimulus → buzzer / local alarm latency |
| Internet down | router WAN cable pulled mid-event | alarm latency; which notifications fail and how gracefully |
| WiFi down | AP off mid-event | the sensor-board buzzer still sounds; edge behaviour |
| Edge laptop killed | `kill -9` on `edge/main.py` mid-event | the sensor board's buzzer alone |
| LLM API blocked | bad key / firewall before the event | template fallback used; latency added |
| Telegram/Twilio blocked | before the event | the alarm is unaffected; error logged |
| Camera unplugged | before the event | gas-only path still escalates |

- Use lighter gas near the MQ-2 as the stimulus (repeatable, no open flame needed).
- ≥10 repetitions per row. Report median/p95 latency and success n/n with Wilson CI.
- Latency: log timestamps on both sides, or film the stimulus and buzzer together at 60 fps and count frames.
- Reuse and extend `eval/verify_stage*.py`.
- **Done when:** every row has n ≥ 10.

---

## 8. Performance profile

- Per-frame latency (mean, p50, p95), ONNX vs PyTorch, on the laptop. State the exact CPU, RAM and OS.
- End-to-end latency: camera frame → fused level, and fused level → phone notification.
- Model size (MB), params, FLOPs (`fvcore` or `thop`); CPU % and RAM of the edge process.
- Throughput (FPS) actually achieved from the ESP32-CAM stream (QVGA).
- Power draw of each ESP32 board (USB power meter).
- Bill of materials with prices (supports the "low-cost" claim).

---

## 9. Hardening (do before §2 freeze)

### 9.1 Sensor ingest authentication (HMAC-SHA256)

**Threat:** any LAN device can POST `GAS_HIGH` to :8002. With a vision smoke event, that reaches CRITICAL.
**Fix:** the board signs every body with a shared key; the edge verifies and rejects replays.
No new dependencies: `mbedtls` ships with the ESP32 core; `hmac`/`hashlib` are Python stdlib.

**1. Key (you run):**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Put it in `arduino/sensor_esp32_node/secrets.h` (gitignored) and in `.env` as `FIREWATCH_INGEST_KEY`.
Placeholder in `secrets.example.h`:
```cpp
const char *INGEST_HMAC_KEY = "PASTE_64_HEX_CHARS";
```

**2. Firmware (`sensor_esp32_node.ino`):**
```cpp
#include "mbedtls/md.h"
static uint32_t bootId;        // set once in setup(): bootId = esp_random();
static uint32_t postSeq = 0;

static void hmacHex(const char *msg, char out[65]) {
  uint8_t mac[32];
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),
                  (const uint8_t *)INGEST_HMAC_KEY, strlen(INGEST_HMAC_KEY),
                  (const uint8_t *)msg, strlen(msg), mac);
  for (int i = 0; i < 32; i++) sprintf(out + 2 * i, "%02x", mac[i]);
}
```
In `postReading()`:
- Grow `body` to 384 bytes.
- Prefix both `snprintf` formats with `"{\"boot\":%lu,\"seq\":%lu,` and pass `(unsigned long)bootId, (unsigned long)++postSeq`.
- After building the body:
```cpp
char sig[65];
hmacHex(body, sig);
http.addHeader("X-FW-Signature", sig);
```
Boot and seq sit inside the signed body, so they can't be altered.

**3. Edge (`edge/wifi_source.py`):**
- In `__init__`: `self._key = os.environ.get("FIREWATCH_INGEST_KEY", "").encode()`,
  `self._require_auth = bool(sensors.get("ingest_require_auth", True))`, `self._boot = None`,
  `self._last_seq = -1`, `self._seen_boots: set[int] = set()`.
- New method:
```python
def verify(self, raw: bytes, sig: str) -> bool:
    if not self._require_auth:
        return True
    if not self._key:
        return False  # fail closed; the board's own buzzer still covers gas
    expected = hmac.new(self._key, raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
```
- In `do_POST`: read `raw = self.rfile.read(length)` once, call
  `source.verify(raw, self.headers.get("X-FW-Signature", ""))` → `401` on failure, then `json.loads(raw)`.
- In `_ingest` (under `_require_auth`), reject replays:
```python
boot, seq = payload.get("boot"), payload.get("seq")
if not isinstance(boot, int) or not isinstance(seq, int):
    return False
if boot != self._boot:
    if boot in self._seen_boots:
        return False  # replay of an earlier boot's messages
    self._seen_boots.add(boot)
    self._boot, self._last_seq = boot, -1
if seq <= self._last_seq:
    return False
self._last_seq = seq
```
- At startup, if auth is required and the key is missing, print a loud warning.
- Add `ingest_require_auth: true` to `config.example.yaml`.

**4. Verify** (extend `eval/verify_stage3_transport.py`): unsigned → 401, wrong signature → 401, replayed body → 422,
valid → 200, reboot (new boot id) → 200.

**Residual risk (state it in the paper):** a replay captured before an edge restart can be accepted once after
the restart (seen boot ids live in memory). There's no confidentiality (HTTP, not TLS); readings are readable on the LAN but can't be forged.

### 9.2 Dashboard binding
Bind the dashboard backend to `127.0.0.1` by default (`uvicorn ... --host 127.0.0.1`); the relay and edge are local.
Add a bearer token only if remote access is needed. ~2 h.

### 9.3 Camera hostname
`MDNS.begin("firewatch-cam")` in `cam_node`, then `stream_url: http://firewatch-cam.local/stream`. ~1 h.

### 9.4 Darkness gate (fixes the total-darkness false WARNING)
- Vision abstains (casts no vote) when the frame is blind: mean luminance < t1 **and** 99th-percentile luminance < t2.
  A flame in the dark has bright pixels, so it still passes.
- Choose t1/t2 on **non-test frames**: record a few dark and dim clips in a session named `T00` (never part of set C), plus a
  candle in the dark to confirm it passes. Then freeze (§2).
- The dashboard shows "camera blind"; the gas path still covers. ~2 h.

### 9.5 Temperature rule
Fusion rule 2 (fire + temperature rise) can never fire without the DHT22. Describe fusion in the paper **without** rule 2
and state why. (Adding a DHT22 changes the hardware and the freeze; not worth it for Path 1.)

---

## 10. Optional: LLM alert evaluation (one paragraph, low priority)
- On ≥50 replayed incidents, check each alert: (a) the stated level matches the fused level, (b) no invented facts,
  (c) length/readability. Compare with the deterministic template.
- Report the fallback rate and added latency. Its role in the paper: "the LLM adds readability, and never affects detection or timing."
- `eval/alert_feedback.csv` (43 rows) is a starting point.

---

## 11. What is already paper-ready vs not

| Already usable (needs only writing) | Not usable as a result |
|---|---|
| Architecture: deterministic detection, local alarm before any network call, LLM only writes the message | Every v4 validation metric (selection bias); mention it once, as development history |
| Fusion rule table and vision-only → WARNING cap | 11/12 live trials (n too small; clips deleted); replaced by §6 |
| Firmware gas logic: warm-up gate, per-boot baseline, ratio thresholds, capped drift, hard ceilings | TV-footage "6 alarms" (clip deleted, n = 1); replaced by §5/§6 |
| ONNX vs PyTorch parity (5.99e-05) and local vs Lambda parity (3e-06) | "Bright-wall FP 98% → 0%" (frames tied to training); replaced by §5.4 |
| Data provenance record, including the scraping reject-rate finding | Fail-safe claim (designed, not measured); replaced by §7 |
| Calibration logs in `eval/calibration/`; add plots and n | Latency "~23 ms" (add p50/p95, hardware, n); replaced by §8 |
| Safety design: simulated dispatch, LLM never gates escalation | |

---

## 12. Limitations: fix vs keep

| Limitation | Action | Where |
|---|---|---|
| Sensor ingest has no auth | **Fix** | §9.1 |
| Dashboard :8001 has no auth | **Fix**: localhost binding | §9.2 |
| Hardcoded camera IP | **Fix**: mDNS | §9.3 |
| False WARNING in total darkness | **Fix**: darkness gate | §9.4 |
| Fusion rule 2 can never fire | **Fix**: describe fusion without it | §9.5 |
| No held-out test set | **Fix**: test set C | §3, §4 |
| Small-flame recall is an anecdote | **Fix**: measured via matchstick/lighter/distant categories | §4.5 |
| MQ sensors aren't selective | **Measure**: cross-sensitivity table | §6.5 |
| Single site | **Reduce**: ≥2-3 rooms; disclose one household | §4.3 |
| ESP32-CAM stream has no auth | **Mitigate**: isolated network or hotspot; disclose | — |
| TV/laptop fire footage alarms | **Keep, measure, disclose**: the fusion cap at WARNING is the mitigation | §5, §6 |
| Steam looks like smoke | **Keep, measure, disclose** | §5, §6 |
| Smoke recall is the weakest class | **Keep**: only retraining fixes it; report the set C number | §5 |
| v4 training not fully reproducible (447 images deleted) | **Keep, disclose** | §0 |
| People in v4 training data | **Keep, disclose**: no training images released | §1.4 |
| No D-Fire test comparison | **Keep, disclose**: the deployment-camera test is the stronger evidence | §0 |
| GPS hardcoded | **Reframe**: fixed installations have a fixed address | — |
| Cloud second opinion needs internet | **Reframe**: advisory by design; §7 shows losing it doesn't affect detection | §7 |

---

## 13. Reproducibility package
- Public repo tag `paper-v1`: code, `frozen_v4.yaml`, manifests, v4 weights (ONNX + .pt), firmware, wiring diagram, BOM with prices.
- Test set C clips plus sensor logs on Zenodo (gets a DOI) **if no faces appear**; otherwise release manifests and features only.
- One script per table/figure under `eval/paper/`; a single `eval/paper/run_all.sh` regenerates every number.
- Data card (from `docs/data_provenance.md`, with the deleted-data disclosure) and model card.
- `ENVIRONMENT.md`: exact Python, package and firmware versions.

---

## 14. The paper

### 14.1 Contribution (write this sentence first)
> A low-cost (≈$X) two-board edge system for indoor fire and gas hazard detection, evaluated on an independent,
> deployment-camera test set of N frames from S sessions, in which deterministic camera–gas fusion reduces false alarms
> from A% (vision-only) to B% at C% event detection, and whose local alarm path is shown, under K fault-injection trials,
> to be independent of network, host and LLM failure.

### 14.2 Structure (IEEE conference, 6-8 pages)
1. Introduction: problem, gap, 3 contributions
2. Related work: vision fire detection (CNN/YOLO, MobileNet on the edge), multi-sensor fusion, IoT fire systems, LLMs in emergency response
3. System design: architecture figure, the fail-safe ordering, the fusion table, firmware gas logic, auth
4. Model and data: v4 training data (provenance, incl. deleted-data disclosure), frozen decision rule
5. Evaluation protocol: test set C recording protocol, set B, leakage controls, freeze, statistics
6. Results: frame-level (§5), system/fusion (§6), fail-safe (§7), performance (§8), failure cases with Grad-CAM
7. Limitations and threats to validity: one household, small n per category, lab fires ≠ real fires, MQ selectivity, no D-Fire test
8. Ethics and safety: simulated dispatch, no faces, safe fire handling
9. Conclusion

### 14.3 Figures and tables checklist
- [ ] Architecture diagram
- [ ] Hardware photo and wiring
- [ ] Test-set composition table (per class, category, session)
- [ ] T1 main metrics with CIs (set C, set B)
- [ ] F5/T2 per-category
- [ ] F3 PR curves (+ F2 ROC in the appendix)
- [ ] F1 confusion matrix
- [ ] F4 reliability diagram
- [ ] T4 baselines, T5 model history
- [ ] Fusion ablation table (main result) + time-to-detection CDF
- [ ] Fault-injection table
- [ ] Gas sensor response, drift and cross-sensitivity
- [ ] F7 Grad-CAM grid
- [ ] Latency/resource table + BOM

### 14.4 Related work to read and cite (verify each before citing)
- D-Fire dataset paper (de Venâncio et al., Neural Computing and Applications, 2022)
- MobileNetV3 (Howard et al., ICCV 2019)
- Real-time fire detection on small embedded devices with MobileNetV3 + YOLOv4 (Fire Ecology, 2023)
- Fireframe: low-cost edge wildfire smoke detection (ISPRS Annals, 2025)
- Gas sensor array + thermal camera early fusion (arXiv 2106.06180)
- Lightweight smoke/fire detection on edge with sensor + vision (Preprints.org 202512.1685, not peer reviewed)
- Smart fire forecast + LLM-powered emergency response (Engineering, 2026)
- A recent survey of multi-sensor fire detection, plus a survey of vision fire detection
- Before writing: search IEEE Xplore and MDPI for "ESP32-CAM gas sensor fire fusion" to check that nothing near-identical exists.

### 14.5 Venue
- First target: an IEEE IoT/sensors conference or workshop, or a student research track.
- Journal option: MDPI *Sensors* or *Fire* (check the APC cost and scope).
- Post an arXiv preprint at submission. Check deadlines and page limits on the venue site.

---

## 15. Order of work

| # | Step | Section | Rough effort |
|---|---|---|---|
| 1 | Hardening: auth, dashboard binding, mDNS | §9.1-9.3 | 1-2 days |
| 2 | Record `T00` dark clips → darkness gate | §9.4 | 0.5 day |
| 3 | Write `record_session.py`, dry-run; prepare equipment | §4.2 | 1 day |
| 4 | **Freeze v4** (`frozen_v4.yaml` commit) | §2 | 1 h |
| 5 | Sessions S01-S06 (+ gas-only clips) | §4.3-4.6 | 6 × 2-3 h |
| 6 | Extract, review, dedupe, manifest commit | §4.7 | 1-2 days |
| 7 | Optional: set B download, leakage check, manifest | §3.2 | 1-2 days |
| 8 | Frame-level eval, baselines, model history, figures, Grad-CAM | §5 | 2-3 days |
| 9 | Replay + fusion ablation | §6.1-6.3 | 2 days |
| 10 | 24 h run + gas characterization | §6.4-6.5 | 2 days (mostly waiting) |
| 11 | Fault injection | §7 | 1-2 days |
| 12 | Profiling + BOM | §8 | 0.5 day |
| 13 | Reproducibility package | §13 | 1 day |
| 14 | Write, internal review, submit | §14 | 1-2 weeks |

Steps 7 and 10-12 can run in parallel with others. **Never run anything on set C/B before step 4's freeze commit and step 6's manifest commit.**

---

## 16. Fallback (decided in advance)

If fire recall on set C (at the frozen threshold) is **below ~85%**, or a whole fire category is near 0%:
1. Report the v4 result as it is. It's still a valid finding (domain shift from internet images to the ESP32-CAM).
2. Record **separate training sessions** `T01..T0n` (different days from S sessions; the same shot list).
3. Fine-tune v4 on those frames → v4.1. Choose its threshold on a held-out part of the `T` sessions.
4. Record **new test sessions** `S07..` and evaluate v4.1 only on those. Never evaluate v4.1 on S01-S06 for the headline,
   because they informed the decision to fine-tune.
5. Report both: v4 on S01-S06 and v4.1 on S07+.

---

## 17. What not to do

- Don't report any v4 validation number as a result.
- Don't score v4 on D-Fire's test split (it trained on it).
- Don't change the model, thresholds, voter, fusion or firmware after the freeze.
- Don't tune anything on set C or B. If you analyse thresholds on them, label it post-hoc.
- Don't hand-pick Grad-CAM or example images.
- Don't use `IMG_6620.MOV` or its source video in testing.
- Don't present the LLM agent as a contribution; present "the LLM never gates detection" as a design constraint.
- Don't claim real-world fire-safety readiness. The evaluation is lab-scale, in one household.
