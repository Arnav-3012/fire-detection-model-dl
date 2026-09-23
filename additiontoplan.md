# additiontoplan.md — two cloud additions (Lambda beyond the second opinion)

**Status: PROPOSAL, nothing built. Written 2026-09-23.**

This file adds two items to the cloud story. It does **not** replace
`plan.md`, `phase12.md`, or `tools/transport_plan.md`. Read
`tools/transport_plan.md` first — it holds the architecture these two items
sit on top of, and its Stage 6 is the Lambda endpoint both items reuse.

**Both items exist to answer one problem:** Lambda as currently specced in
`tools/transport_plan.md` Stage 6 runs *the same v4 model on the same frame*
as local inference. It therefore almost always agrees, and an opinion that
always agrees is an echo, not a second opinion. These two items make the
cloud verdict genuinely different from the local one, and give the cloud a
job local cannot do at all.

**Neither item requires retraining.** Both reuse `models/fire_mnv3.onnx`
unchanged. This was the developer's explicit constraint (2026-09-23 session):
no retraining, no new model artifact.

**Priority note:** both items depend on Stage 3 (WiFi transport) and Stage 6
(the Lambda endpoint), and neither exists yet. `tools/transport_plan.md`
already lists Stage 6 on its cut line. These are therefore **after** Stage 3,
and are the first things to cut if the deadline tightens. A documented
rejection on cost/effort grounds is an acceptable outcome for either.

---

## Item A — Make the cloud verdict non-redundant (no retraining)

Goal: Lambda answers a *different question* than local inference, using the
same weights, so a disagreement carries information instead of noise.

### A.0 Verified ONNX constraint — read before choosing a variant

Checked against `models/fire_mnv3.onnx` on 2026-09-23:

```
INPUT   input   ['batch', 3, 224, 224]   tensor(float)
OUTPUT  logits  ['batch', 3]
```

**Batch is dynamic. Spatial dims are LOCKED at 224x224.**

Two consequences, both confirmed by running the model:

- A batch of 5 crops in one `session.run()` call works — returns `(5, 3)`.
- A 320x320 input is **rejected** outright: `INVALID_ARGUMENT : Got invalid
  dimensions for input`.

This kills the "just run it at higher resolution" idea in its cheap form.
Higher-resolution inference would require a **re-export** from the training
checkpoint with a dynamic spatial axis (`train/export_onnx.py`), which is not
a retrain but is still a new model artifact to validate against
`eval/` — out of scope per the no-retraining constraint above.

**So variants A.1 and A.2 below are the ones that survive.** Both live
entirely inside the locked 224x224 shape.

### A.1 Multi-crop inference (preferred)

The camera captures 640x480. Local inference downscales the whole frame to
224x224 and throws the detail away — a small or distant flame can vanish in
that downscale. Lambda instead scores several 224x224 crops of the *native*
frame and aggregates.

- Take 5 crops from the 640x480 JPEG: centre plus four corners, each resized
  to 224x224 (or taken at native scale where the crop is already >=224).
- Stack into one `(5, 3, 224, 224)` batch — **one** `session.run()` call, not
  five. Confirmed working above.
- Aggregate: report **max** `p_fire` across crops alongside the mean. Max is
  the operative number — the question this variant answers is "does *any*
  region of the frame look like fire at full detail," which is precisely what
  the full-frame downscale cannot see.
- Preprocessing must reuse `edge/vision.py`'s `_preprocess()` logic verbatim
  (BGR->RGB, /255, ImageNet mean/std, HWC->CHW). Do **not** reimplement it —
  `phase12.md` step 7 already flags divergence here as the risk, and it is
  the classic silent-wrong-probabilities bug.

Why this is genuinely a different answer: local sees one downscaled view,
cloud sees five detailed views. Disagreement means "local's downscale hid
something" — informative, and it bears directly on the known TV-fire
limitation (`edge/fusion.py` rule 4) because a screen showing fire looks
fire-like at *every* crop scale, while a real distant flame does not.

### A.2 Test-time augmentation (cheaper fallback if A.1 is too much)

Same frame plus its horizontal flip, batched as `(2, 3, 224, 224)`, averaged.
Standard TTA, no retraining, one extra call's worth of compute. Weaker than
A.1 — it does not recover lost detail, it only smooths the decision — but it
is a few lines. Use only if A.1 does not fit the time budget.

### A.3 Surfacing it (required — not optional polish)

An opinion nobody sees is worth nothing. In Live View, show the cloud verdict
**next to** the local one with an explicit agree/disagree state:

- `LOCAL: WARNING  ·  CLOUD: agrees (p_fire 0.81 max / 0.62 mean over 5 crops)`
- `LOCAL: WARNING  ·  CLOUD: DISAGREES (p_fire 0.11) — check frame`

Disagreement is the signal. Reuse `src/levels.js` colours, do not introduce a
new palette (`phase12.md` step 9's existing rule).

### A.4 Hard constraint carried over

The cloud verdict **never** gates the local alarm and **never** feeds
`fuse()`. `edge/fusion.py:14` — *"No model, no LLM, no network"* — stays
true. `fuse()`'s four booleans stay local-only: vision from local ONNX, gas
from the board's own `GAS_HIGH` state, temp still stubbed False. Cut this
whole item and detection is byte-for-byte unchanged. That property is the
point.

---

## Item B — S3-triggered batch re-scoring

Goal: turn the incident archive into a measurable false-positive record.
This is the item that gives the cloud a job local genuinely cannot do —
the laptop is not always on, and this work is retrospective by nature.

### B.1 What it does

`cloud/uploader.py` already archives CRITICAL incidents to S3 and already has
a 50-upload circuit breaker. Every archived frame is a real-world trigger
that the system *thought* was CRITICAL. Nothing currently ever revisits them.

- Nightly (EventBridge schedule, or S3 `ObjectCreated` if per-frame is
  preferred), Lambda re-runs the **existing** v4 model over newly archived
  frames.
- Write results to a manifest in S3: frame key, timestamp, original local
  verdict, re-scored `p_fire`/`p_smoke`, and a `reviewed` flag for manual
  labelling.
- Surface the running count on the dashboard: archived incidents, re-scored,
  and — once frames are manually labelled — a **measured false-positive
  rate over real deployment triggers**.

### B.2 Why it is worth building

This is the only item here that produces something the project does not
currently have at all: `eval/results.csv` measures the model against a
*curated* val set and against 12 staged trials. It has no number for how
often the system false-alarms on **real ambient conditions over time**. That
number is an ML-project asset and it is the kind of thing that survives past
the deadline.

It also costs almost nothing: no new model, no retraining, and invocation
volume is bounded by how many CRITICAL incidents actually occur (very few).

### B.3 Honest scope warning

The false-positive *rate* requires **manual labelling** of archived frames —
the re-scoring alone only tells you what the model says, not what was
actually true. Without labelling, this item delivers the archive and the
manifest but not the headline number. Budget for the labelling or state
plainly in `report.md` that the rate is pending, per `info.md` 2.4 (no
metrics written until measured).

---

## What was considered and rejected

- **Higher-resolution cloud inference (320/384).** Rejected: the ONNX export
  locks spatial dims at 224x224 (verified A.0). Would need a re-export from
  the training checkpoint — not a retrain, but a new artifact requiring its
  own `eval/` validation. Out of scope per the no-retraining constraint.
- **MobileNetV3-Large in Lambda.** Rejected: requires retraining. This was
  the developer's explicit constraint.
- **Lambda as the authoritative detector.** Rejected on the same grounds
  `tools/transport_plan.md` already records — a WAN outage must never
  downgrade the detector, `plan.md` 2's offline claim depends on it, and
  `TemporalVoter`'s N-of-M window cannot live in a stateless Lambda
  (`phase12.md:164-170`).
- **Cloud-side gas trend analysis** (baseline drift over days). Not rejected,
  just not included here — it is a third, independent idea with no dependency
  on the Lambda endpoint. Revisit separately if time allows.

---

## Clarification worth recording — "everything is local" is too loose

Raised in the 2026-09-23 session and worth stating precisely, because the
offline demo claim depends on it. **Detection is local. Transport is not.**

Both ESP32 boards reach the laptop over WiFi: the sensor board POSTs JSON to
`/api/sensor-ingest` (Stage 3), the camera board serves JPEGs at
`http://<cam-ip>/stream` (Stage 4's relay). Every byte crosses WiFi before any
detection happens. WiFi is **not** the cloud — the router with its WAN cable
unplugged still carries the entire detection pipeline.

Three layers, and two distinct offline stories:

| Lose | What still works |
|---|---|
| Internet (WAN unplugged, WiFi up) | Everything except S3 / agent / Lambda. Boards reach the laptop, vision runs, `fuse()` runs, dashboard live, full CRITICAL detection. |
| WiFi as well | The sensor board's own buzzer — firmware owns its baseline, thresholds and buzzer, and has no `Serial.read()` at all (`edge/main.py:183`). Gas-only fallback. |

Both are already on the test list (`phase12.md` 10 and 11). State them
separately in `report.md` — the two-tier version is a stronger claim than
"everything is local," and it is the accurate one.

---

## Checklist

- [ ] A.1 Multi-crop inference in Lambda (5-crop batch, max + mean p_fire)
- [ ] A.3 Agree/disagree display in Live View
- [ ] B.1 S3-triggered nightly re-scoring + manifest
- [ ] B.3 Manual labelling pass (or documented as pending)
- [ ] Record in `plan.md` 10.6 that per-frame continuous inference was
      rejected, and that the cloud verdict is advisory only
