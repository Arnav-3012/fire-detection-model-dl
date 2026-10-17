# Fusion Logic Explained: The Bridge Between Vision and the Agent

`edge/fusion.py`'s `fuse()` function is small — under 50 lines — but it is
the single most important piece of judgment in the entire FireWatch system.
It sits between two worlds that are documented separately elsewhere (the
vision model's outputs on one side, the response agent's inputs on the
other) and nothing else currently explains how they connect. This document
is that missing bridge.

Following the sensei formula throughout: intuition → math/logic → code →
connection → check yourself.

---

## 1. Where Fusion Sits in the Pipeline

```
 camera frame          gas sensors (MQ-2, MQ-135)
      |                          |
 vision model              compute_gas_high()
 (p_fire, smoke)                 |
      |                          |
      +----------> fuse() <------+
                     |
              (Level, reason)
                     |
        edge/main.py sends WARNING/CRITICAL
              to the agent via HTTP
```

Everything to the LEFT of `fuse()` is about *sensing* — cameras, ML models,
chemical gas sensors, analog-to-digital conversion. Everything to the RIGHT
of `fuse()` (the LangGraph agent covered in `agent_explained.md`) is about
*response* — composing messages, sending alerts, waiting for a cancel. `fuse()`
is the one function that converts raw, noisy, individually-unreliable
sensor signals into a single clean decision: `SAFE`, `WATCH`, `WARNING`, or
`CRITICAL`. Nothing downstream ever re-examines the raw sensor data again —
the agent trusts this verdict completely and irreversibly.

### 🧠 Intuition

You're a smoke alarm designer. You have two witnesses to a possible fire:
a camera that *looks* for flames, and a gas sensor that *smells* for smoke
and combustible gas. Each witness, alone, can be fooled:

- The camera can be fooled by a TV screen playing a fire scene, a sunset
  through a window, or a bright light reflecting off a wall — all of which
  visually resemble flame to an imperfect model. This project actually hit
  this failure in testing: Phase 5's "block-bar failure" saw a TV showing
  fire footage trigger 7 false alarms.
- The gas sensor can be fooled by cooking fumes, steam, alcohol-based hand
  sanitizer vapor, or a nearby car's exhaust — none of which are a fire.

But here's the insight that makes fusion powerful: **the ways a camera gets
fooled and the ways a gas sensor gets fooled are almost completely
unrelated to each other.** A TV playing fire footage releases no gas. A pot
of cooking food usually isn't visually on fire. So if BOTH signals fire at
once, that's no longer two independent 30%-likely false alarms — it's
extremely strong evidence, because you'd need two *unrelated* failure modes
to coincide by chance at the same moment.

This is exactly why you don't rely on a single smoke detector for a data
center, and why airport security often uses more than one detection method
in sequence (metal detector + X-ray + sometimes a pat-down) — agreement
between independent methods is worth far more than either method alone,
even if each method alone is decent.

---

## 2. The Four Signals

`fuse()` takes exactly four boolean inputs:

```python
def fuse(
    vision_fire: bool,
    vision_smoke: bool,
    gas_high: bool,
    temp_spiking: bool,
) -> tuple[Level, str]:
```

| Input | Where it comes from | What "True" means |
|---|---|---|
| `vision_fire` | The vision ML model | The model's confidence that flames are visible cleared a decision threshold |
| `vision_smoke` | The vision ML model | The model detected smoke (a separate class from flame) |
| `gas_high` | `compute_gas_high()` (below) | Either gas sensor reading is at/above its calibrated "warn" level |
| `temp_spiking` | `temp_spiking()` stub | Always `False` in this build — no temperature sensor exists (see Part 5) |

Each of these is already a yes/no answer by the time it reaches `fuse()` —
all the messy, continuous, uncertain measurement happened upstream (a
probability score `p_fire` got compared against a threshold, a raw ADC
reading got compared against a calibrated warn level). `fuse()` itself
works purely with clean booleans, which is exactly what makes it possible
to reason about with a simple truth table instead of statistics.

### `compute_gas_high` — turning two raw sensor numbers into one boolean

```python
def compute_gas_high(mq2: float, mq135: float, thresholds: dict[str, float]) -> bool:
    return mq2 >= thresholds["mq2_warn"] or mq135 >= thresholds["mq135_warn"]
```

**🧠 Intuition:** Either gas sensor alone crossing its "something's off" line
is enough to call `gas_high` — you don't need BOTH gas sensors to agree,
because they detect different (though overlapping) sets of gases: MQ-2 is
tuned toward LPG/methane/propane/smoke, MQ-135 toward CO2/ammonia/benzene/
general air quality. Requiring both to agree would make the system
*slower* to notice a real gas hazard that only one sensor type is sensitive
to.

**📐 Why the WARN threshold, not the more severe DANGER threshold?** This is
explained directly in the code's own comment, and it's worth internalizing
because it reveals the project's core risk philosophy:

> `gas_high`'s job in the fusion table is *corroboration* — a warn-level
> reading agreeing with a visual hazard is already independent
> confirmation. Waiting for danger-level gas would delay CRITICAL in a real
> fire, and missing a real fire is judged the worse failure mode.

In other words: `gas_high` isn't being used here to answer "is there
definitely a gas emergency on its own?" — it's being used to answer "is
there at least a second, independent signal agreeing with what the camera
saw?" Those are different questions with different appropriate thresholds.
Using the lower WARN bar means CRITICAL gets triggered *faster* when a real
fire is happening (good), at the cost of very slightly looser corroboration
evidence (an acceptable tradeoff given the stated priority that missing a
real fire is worse than a false alarm).

---

## 3. The `Level` Enum

```python
class Level(IntEnum):
    SAFE = 0
    WATCH = 1
    WARNING = 2
    CRITICAL = 3
```

**🧠 Intuition:** This is a severity scale, like a hurricane category or an
earthquake magnitude — each level is strictly worse than the one below it.

**📐 Why `IntEnum` and not plain `Enum`?** A plain Python `Enum` gives you
named constants (`Level.SAFE`, `Level.CRITICAL`) but does NOT let you
compare them with `<` or `>=` out of the box — you'd get a `TypeError`. An
`IntEnum` is *also* a real integer underneath (`Level.CRITICAL == 3` is
literally `True`), so ordering comparisons work for free:

```python
if current_level >= Level.WARNING:
    # trigger the agent
```

The alternative — maintaining a separate lookup table mapping level names to
severity ranks — would work too, but creates a duplicate source of truth
that could silently drift out of sync if someone edits one and forgets the
other. Deriving comparisons directly from the enum's own integer values
means there is exactly one place severity ordering is defined, ever.

**At the extremes:** `Level.SAFE` (0) compares less than everything;
`Level.CRITICAL` (3) compares greater than everything. This is precisely
why `agent/server.py`/`edge/main.py` can gate the entire agent behind a
single check: "only invoke the agent if `level >= WARNING`" — no separate
"is this bad enough" logic needs to exist anywhere else.

---

## 4. The Rule Table, Rule by Rule

### 📐 The Logic

Rules are checked **top to bottom, first match wins.** This detail matters
enormously — it is not just a style choice, it's what guarantees safety
correctness. Read it as a strict priority list, like a doctor's triage
protocol: check for the most life-threatening condition first, and only
consider less urgent explanations if the more urgent one has been ruled out.

```python
def fuse(vision_fire, vision_smoke, gas_high, temp_spiking):
    # Rule 1
    if (vision_fire or vision_smoke) and gas_high:
        return Level.CRITICAL, "visual hazard confirmed by gas sensor"

    # Rule 2 (structurally present, unreachable in production — see Part 5)
    if vision_fire and temp_spiking:
        return Level.CRITICAL, "flame detected with rapid temperature rise"

    # Rule 3
    if gas_high and not (vision_fire or vision_smoke):
        return Level.WARNING, "gas concentration high, no visible flame"

    # Rule 4
    if vision_fire:
        return Level.WARNING, "visual flame, unconfirmed by sensors"

    # Rule 5
    if vision_smoke:
        return Level.WATCH, "possible smoke, monitoring"

    return Level.SAFE, "nominal"
```

Let's build a full truth table to see every possible combination and
understand *why* the priority order was chosen. (`temp_spiking` is left out
of most of this table since it's always `False` in production — see Part
5 — but it's included in the "if it existed" column for completeness.)

| vision_fire | vision_smoke | gas_high | Rule that fires | Level | Reasoning |
|---|---|---|---|---|---|
| T | * | T | 1 | CRITICAL | Vision + gas agree — strongest possible evidence |
| * | T | T | 1 | CRITICAL | Smoke + gas agree — same logic, smoke is still a vision-side signal |
| T | * | F | 4 | WARNING | Vision alone — could be a TV/false trigger, capped below CRITICAL |
| F | T | F | 5 | WATCH | Smoke alone, unconfirmed — early warning tier, not yet an alarm |
| F | F | T | 3 | WARNING | Gas alone — a real hazard class (leak, smouldering fire out of camera view) but visually unconfirmed |
| F | F | F | — (falls through) | SAFE | Nothing detected |

(`*` means "doesn't matter for this row, since the earlier `or` already
covers it.")

**What happens at the extremes?**
- **Everything `False`:** every `if` fails, execution falls all the way
  through to the final `return Level.SAFE, "nominal"`. The function always
  terminates with a definite answer — there is no "unknown" or `None` case,
  which matters a lot for downstream code that expects a real `Level` value
  every single time.
- **Everything `True`:** Rule 1 matches immediately and wins, `CRITICAL` is
  returned. This is the correct behavior — you'd never want the *most*
  confirmed, most dangerous combination of evidence to somehow be
  downgraded because a later, weaker rule also happened to be technically
  true. This is exactly why "first match wins, most severe rule first" is
  the right ordering discipline: **more specific / more severe conditions
  must always be checked before more general / weaker ones**, or a stronger
  case could get silently swallowed by a rule meant for a weaker one.

### 🔗 Why is Rule 4 (vision-only fire) capped at WARNING and not CRITICAL?

This is the single most important design decision in the whole file, and
it's explicitly called out as deliberate, not accidental:

> Rule 4 caps vision-only fire at WARNING — it is the designed mitigation
> for the TV/laptop-fire limitation, not an accident of ordering.

Recall the real, observed failure mode: a TV playing fire footage produced
7 false alarms during testing when vision alone was trusted for the top
severity tier. A TV emits no combustible gas, no smoke, and no genuine heat
signature strong enough to register on a gas sensor. So by *structurally*
requiring gas-sensor agreement before anything reaches CRITICAL, this
specific, real, previously-observed failure mode becomes physically
impossible to trigger a false CRITICAL alert — not just "less likely," but
mathematically ruled out by the rule table itself, regardless of how
convinced the vision model is.

This is a genuinely elegant piece of system design: rather than trying to
make the vision *model* smarter about telling real fire from TV fire (a
very hard ML problem — pixels look the same), the *system architecture*
sidesteps the problem entirely by never trusting vision alone for the
highest-stakes response. This is a recurring and valuable lesson: **when a
component has a known, hard-to-fix weakness, sometimes the right fix is
architectural (require corroboration) rather than trying to make that one
component perfect.**

### 🔗 Why does gas-alone (Rule 3) only reach WARNING, not CRITICAL either?

Symmetric reasoning, from the other direction: a gas sensor alone can be
triggered by cooking, steam, or an unrelated chemical vapor with zero
visual fire present. Real event, but not confirmed as *fire* specifically —
it could be a genuine but non-fire hazard (a gas leak) or a false trigger
(cooking). WARNING is the right tier: worth alerting a human about
immediately, but not worth invoking the full CRITICAL response (which,
downstream in the agent, changes the alert's tone and, in earlier design
iterations, was tied to more aggressive escalation).

---

## 5. `temp_spiking`: A Rule Kept Alive on Life Support

### 🧠 Intuition

Picture a recipe that calls for an ingredient your kitchen doesn't currently
stock. You don't rewrite the whole recipe to remove it — you just note "add
this back when you buy it" and substitute nothing for now. That's exactly
what happened to Rule 2.

### 📐 The Logic

```python
def temp_spiking() -> bool:
    """STUB — always False. No temperature sensor exists in this build."""
    return False
```

A **DHT22** temperature/humidity sensor was originally planned (it appears
in `plan.md`'s hardware appendix, complete with its own pull-up-resistor
wiring notes) but was cut early in the build ("Phase 0g") for cost and
availability reasons. That removed the *only* source of a `temp_spiking`
signal.

Rather than deleting Rule 2 from `fuse()` (`if vision_fire and temp_spiking:
return Level.CRITICAL, ...`), the decision was to keep the rule
*structurally present* in the table, and disable it at its single input
source instead — this `temp_spiking()` function, which is hardcoded to
always return `False`.

**Why keep dead code around at all?** Three concrete reasons:
1. **The rule table stays faithful to the original design spec** (`plan.md`)
   — anyone reading `fuse()` alongside the design doc sees the same table,
   not a mysteriously shortened one, which avoids confusing future
   maintainers into thinking the omission was an oversight.
2. **It's still testable.** The docstring notes: "Reachable in tests by
   forcing the parameter True" — since `fuse()` takes `temp_spiking` as a
   plain boolean *parameter* (not by calling the stub itself), a test can
   pass `temp_spiking=True` directly and verify Rule 2's logic works
   correctly, completely independent of whether real hardware exists yet.
3. **Re-enabling it later is a one-line change.** When a real temperature
   sensor is eventually wired up, only `temp_spiking()`'s body needs to
   change (read the real sensor, compute a rate-of-rise, compare to
   `config.yaml`'s `temp_rise_rate` placeholder) — `fuse()` itself needs
   zero changes, because the rule was never removed, just starved of a
   real input.

### 🔗 Connection

This is a specific instance of a broader and very useful engineering
pattern: **disable a feature at its narrowest possible input point, not by
scattering `if feature_enabled` checks throughout the code that depends on
it.** You'll see the same idea called a "feature flag" or "kill switch" in
production systems — the difference here is the flag is baked into a
function's return value rather than a config toggle, which is fine for a
feature with no real hardware to toggle yet.

---

## 6. Why Is All Of This Deterministic — No ML, No LLM, No Randomness?

### 🧠 Intuition

Recall from `agent_explained.md`: the whole system's design philosophy is
"deterministic core, AI only for polish." `fuse()` is the absolute center of
that deterministic core. If you fed `fuse()` the exact same four booleans a
thousand times, in any order, on any day, it returns the exact same
`(Level, reason)` every single time. There's no model weights, no
temperature parameter, no network call, nothing that could vary.

### 📐 Why does this matter so much for a *safety* system specifically?

Three properties fall directly out of determinism, and all three matter a
lot for something that might eventually gate a real emergency response:

1. **Auditability.** Given a specific incident's four input booleans, you
   can always reproduce and verify exactly why a given level was assigned
   — there's no "the model was 73% confident that day" ambiguity.
2. **Testability.** You can write a complete, exhaustive unit test suite —
   there are only 2⁴ = 16 possible input combinations total, so you can
   literally test every single one and know the function is 100% correct
   for all inputs that will ever occur, something you can never claim about
   a trained ML model.
3. **No adversarial surface.** A deterministic boolean table cannot be
   "prompt injected" or subtly nudged by unusual inputs the way a neural
   network or LLM sometimes can — the possible behaviors are enumerable and
   finite by construction.

### 🔗 Connection

This is the same reasoning that led the project to keep the LLM completely
out of the escalation decision in `agent/compose.py` — see
`agent_explained.md` Part 6. `fuse()` is the upstream half of that same
philosophy: **keep the highest-stakes decision as a small, complete,
provably-correct function, and reserve any AI/ML components for places
where imperfect, occasionally-wrong output is an acceptable cost** (like
phrasing a message, or generating an initial candidate fire/smoke
detection that then gets fused with an independent corroborating signal
before it's ever trusted alone).

---

## ❓ Check Your Understanding

1. Suppose a future hardware revision adds back a real temperature sensor
   and `temp_spiking()` starts returning real values. Walk through what
   would need to be true for Rule 2 to ever actually fire in the field
   (i.e., produce a CRITICAL result that Rule 1 didn't already cover). Is
   there a realistic scenario where Rule 2 fires but Rule 1 does not?

2. The reasoning for capping vision-only fire at WARNING (Rule 4) is "a
   screen showing fire produces no gas." Can you think of a real-world
   scenario where this specific safety argument would NOT hold — i.e., a
   genuine fire that also happens to produce very little detectable gas,
   at least initially? What would happen to that fire under this fusion
   table, and is that an acceptable tradeoff given the project's stated
   priorities?

3. `compute_gas_high` uses `or` between the two sensors (either one high is
   enough). If it instead used `and` (both must be high), what class of
   real hazard would become slower to detect, and why?
