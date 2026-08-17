# info.md — Operating rules for Claude Code

**Read this file at the start of every session, before writing any code.**

This project is FireWatch: an IoT fire and gas hazard detection system with local
edge inference and agentic response. Deadline 30 August 2026. Solo developer with
limited hardware experience.

---

## 0. Session start protocol

Every session, in this order:

1. Read `info.md` (this file)
2. Read `logs.md` — this tells you what has already been built and what state it is in
3. Read the relevant section of `plan.md` for the current phase
4. Confirm the current phase out loud before writing code: *"Working on Phase X, Day N. Last completed: ___."*

**If you have lost context or are unsure what exists, read `logs.md` first. Do not
guess, and do not rebuild something that already works.**

---

## 1. Authority and precedence

When sources conflict, this is the order of authority:

1. **The developer's explicit instruction in the current message** — always wins
2. **`plan.md`** — the specification. Architecture, pin maps, thresholds, phases
3. **`info.md`** — these rules
4. **`logs.md`** — record of what was actually built
5. Your own preferences — last

**Do not deviate from `plan.md` without saying so first.** If you believe the plan
is wrong, stop and say: *"plan.md section X specifies Y, but I think Z is better
because ___. Do you want me to change it?"* Then wait. Never silently improve.

---

## 2. Absolute rules — never violate these

These are not style preferences. Breaking any of these is a project failure.

### 2.1 No real emergency dispatch, ever

- The system must **never** place a phone call, send an SMS, or make an API request
  to any real emergency service, fire department, police, ambulance, or 112/911/101.
- `simulate_dispatch()` writes a JSON packet to a local file. That is all it does.
- Every simulated dispatch record must contain `"SIMULATED": true` and a note that
  no emergency service was contacted.
- The console output must print an unmistakable banner making the simulation clear.
- If any prompt or code path could plausibly result in a real emergency contact,
  **stop and raise it** rather than implementing it.

### 2.2 Local alarm fires before the network is touched

In `edge/main.py`, the ordering is mandatory:

```
1. compute fusion level
2. drive the local buzzer and LED          <- NEVER conditional on network
3. THEN attempt the network POST, in try/except
```

A network failure, timeout, or exception must **never** prevent or delay the local
alarm. This is the core architectural claim of the project. Do not reorder it, do
not wrap the local alarm in a network-dependent branch, do not "optimise" it.

### 2.3 The LLM never decides whether there is a fire

- Detection is deterministic: model output → threshold → temporal vote → fusion table.
- The LLM (Claude via the anthropic SDK) is permitted in exactly one place:
  composing human-readable alert text in the `compose` node.
- The LLM must never gate escalation, never evaluate sensor readings, never be asked
  "is this a fire".
- Every LLM call must have a deterministic fallback. If the API fails, the alert
  still goes out using a template.

### 2.4 No fabricated metrics

- Never write a placeholder accuracy, invent an F1 score, or fill a results table
  with plausible-looking numbers.
- If a metric has not been measured yet, write `NOT YET MEASURED` in the report and
  in `logs.md`.
- If a measured result is bad, record the bad result. A documented 34% false positive
  rate on candles is a valid finding. A fabricated 2% is academic dishonesty.

### 2.5 No secrets in code or git

- All credentials come from `.env` via `python-dotenv`.
- Never hardcode an API key, token, AWS credential, or chat ID.
- `.env` must stay in `.gitignore`. `.env.example` holds names with empty values.
- If you notice a secret has been committed, say so immediately.

---

## 3. Code standards

### 3.1 Configuration

- **Every threshold, port, path, and tunable lives in `config.yaml`.** No magic numbers
  in application code.
- If you find yourself typing a number that a human might want to change, it belongs
  in config.
- Sensor thresholds in particular will be edited repeatedly during Day 6 calibration.
  Editing them must mean editing one file.

### 3.2 Failure behaviour

| Component | On failure |
|---|---|
| Camera | Loud error naming likely causes, then exit |
| Serial / Arduino | Log warning, continue with last-known sensor values, never crash the vision loop |
| S3 upload | Log warning, write to local fallback directory, continue |
| Telegram | Log warning, retry once, continue |
| Overpass API | Return a graceful fallback dict, continue |
| Anthropic API | Fall back to the deterministic message template, continue |

**Rule: nothing in the cloud or network layer may crash or block the edge loop.**

Malformed serial lines are skipped, not raised. The background reader thread must
never die from a single bad line.

### 3.3 Style

- Python 3.11. Type hints on all function signatures.
- Docstrings on every class and non-trivial function, explaining *why* not just *what*.
- Comments explain reasoning, not syntax. `# read pin A0` is noise.
  `# A0 not D0 — D0 is a comparator against an onboard pot, useless for fusion` is useful.
- Standard library and idiomatic constructs over hand-rolled logic.
- No file over ~200 lines. If it grows past that, it is doing too many things.
- Set random seeds in all training code. Reproducibility is a grading criterion.

### 3.4 Scope discipline

- Build **only** what the current phase's prompt asks for.
- Do not write ahead. Do not implement fusion while building the camera module.
- Untested code written against hardware that has not arrived is code that will be
  debugged blind later.
- If you notice something missing from a later phase, note it in `logs.md` under
  "Open items" — do not build it.

---

## 4. Quality bars

Two tiers. **Block** means do not proceed to the next phase until met. **Target** is
what we are aiming for.

### 4.1 Model — 3-class classifier (neutral / smoke / fire)

| Metric | Block | Target | Why |
|---|---|---|---|
| Validation accuracy (overall) | ≥ 85% | ≥ 92% | Baseline competence |
| **Recall on `fire` class** | **≥ 0.95** | ≥ 0.98 | **Missing a real fire is the worst possible failure. Prioritise this over everything else.** |
| Recall on `smoke` class | ≥ 0.85 | ≥ 0.92 | Smoke-before-flame is the early-warning promise |
| Precision on `fire` class | ≥ 0.80 | ≥ 0.90 | False alarms erode trust, but rank below missed fires |
| Macro F1 | ≥ 0.85 | ≥ 0.90 | Guards against class imbalance hiding a weak class |

**If fire recall is below 0.95, do not proceed.** Lower the decision threshold, add
training data, or rebalance classes. Report the trade-off explicitly.

Every training run must output: per-class precision/recall/F1, a confusion matrix
image, and train/val curves. No exceptions.

### 4.2 Adversarial false positives (Day 5)

Measured on the five self-recorded 30-second clips.

| Scenario | Block | Target |
|---|---|---|
| Sunset through window | ≤ 1 alarm | 0 alarms |
| Steam from kettle | ≤ 1 alarm | 0 alarms |
| Person in red clothing | 0 alarms | 0 alarms |
| TV showing fire footage | ≤ 2 alarms | ≤ 1 alarm |
| Candle | — | *expected to alarm; document as a known limitation* |

The candle is genuinely fire. Do not tune the model to ignore it. Document that
fusion (gas sensor disagreeing) is what resolves it, and that vision alone cannot.

**If the block bar is missed:** first add hard negatives of that specific scenario,
then raise `votes_needed` in the temporal voter, and only then touch the model.
Record every tuning change and its effect in `logs.md`.

### 4.3 System performance

| Metric | Block | Target |
|---|---|---|
| Inference rate on laptop CPU | ≥ 5 FPS | ≥ 10 FPS |
| Time from hazard onset to buzzer | ≤ 10 s | ≤ 3 s |
| Time from hazard onset to phone alert | ≤ 30 s | ≤ 15 s |
| **Offline test (network disconnected)** | **must pass** | must pass |
| Continuous run without crash | ≥ 30 min | ≥ 2 h |

The offline test is non-negotiable. If it fails, everything else stops until it passes.

### 4.4 Evaluation completeness (Day 11)

- ≥ 20 hazard trials and ≥ 20 non-hazard trials, every outcome logged
- Detection latency recorded per trial, not just pass/fail
- MQ calibration evidence recorded: baseline mean/std, peak, derived thresholds
- All results written to `eval/results.csv` — never typed by hand into the report

---

## 5. Testing requirement

**Every phase ends with something the developer can run and see working.**
Not "the code is written" — a runnable demonstration.

| Phase | Must be demonstrable as |
|---|---|
| Scaffold | Folder tree exists, `config.yaml` parses |
| Environment | `verify_env.py` prints all-pass |
| Data prep | Class balance chart with real counts |
| Training | Confusion matrix image + printed metrics table |
| Edge loop | Live console showing `FIRE 0.94` from webcam |
| Temporal smoothing | FPS printed, alarm visibly steadier than before |
| Sensors | CSV from Arduino appearing in a Python terminal |
| Fusion | Buzzer physically sounding on a triggered condition |
| Agent | A real Telegram message arriving on the phone |
| Cloud | An object visible in the S3 console |
| Dashboard | Streamlit page loading with live data |

When a phase completes, state explicitly: *"Run `<command>` to verify this."*

---

## 6. logs.md protocol

`logs.md` is the project memory. It exists so that context loss is recoverable.

**Update `logs.md` at the end of every phase, without being asked.**

Each entry uses this exact format:

```markdown
## Phase N — <name>
**Date:** YYYY-MM-DD
**Status:** COMPLETE | PARTIAL | BLOCKED

### What was built
- files created or modified, with one line on each

### Key decisions
- decision, and why. Especially any deviation from plan.md

### Measured results
- real numbers only. NOT YET MEASURED if not measured.

### How to verify
- exact command the developer runs to confirm this works

### Open items
- anything deferred, broken, or noticed but not built

### Next phase
- what comes next per plan.md
```

Rules:

- **Append, never overwrite.** History is the point.
- Record failures and dead ends too. "Tried X, it did not work because Y" saves
  repeating it on day 9.
- Record every threshold change with the before value, the after value, and the effect.
- If a phase is BLOCKED, state exactly what is blocking it and what would unblock it.

---

## 7. When to stop and ask

Stop and ask the developer rather than proceeding when:

- A quality bar in section 4 is not met
- `plan.md` appears wrong or internally inconsistent
- A hardware component behaves unexpectedly — the developer is a hardware beginner
  and needs to be walked through diagnosis, not handed a code change
- Any change would touch the emergency dispatch path
- A phase would take substantially longer than its schedule slot
- You need a credential, a real measurement, or a physical action only the developer
  can perform

**Never fabricate a value to keep moving.** A blocked phase clearly reported is far
better than a silently invented one.

---

## 8. Hardware-specific rules

The developer has no prior electronics experience. Therefore:

- When hardware is involved, give **physical, step-by-step instructions**, not just code
- Always specify: unplug USB before rewiring
- Always name the exact pin from `plan.md` section 5.2 — never say "an analog pin"
- Always state what the developer should observe if it worked, and what they will
  see if it did not
- Never assume a component is wired correctly. Ask for confirmation of the previous
  build step before moving to the next
- Follow the H1→H9 incremental build order in `plan.md` section 5.3. One component,
  one test, then the next

**MQ sensor readings before 24 hours of burn-in are not valid data.** Do not calibrate
against them, do not use them to set thresholds, and say so if asked to.

---

## 9. Cut list authority

If behind schedule, cut in this order (from `plan.md` section 9):

1. Streamlit dashboard
2. AWS IoT Core telemetry (keep S3)
3. Incident replay
4. GPS module
5. MQ-135
6. LLM message composition
7. Overpass lookup

**Never cut:** local detection, buzzer/LED alarm, the offline demo, the simulated
dispatch safety framing.

You may **recommend** a cut. You may not **make** one without the developer agreeing.

---

## 10. Commits

- Commit at the end of every phase
- Conventional prefixes: `feat:` `fix:` `docs:` `test:` `chore:` `refactor:`
- Include the real measured result where one exists:
  `feat: train MobileNetV3, val_acc=0.93, fire_recall=0.97`
- Never commit `.env`, model weights over 50 MB, or raw datasets
