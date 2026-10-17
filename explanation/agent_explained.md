# FireWatch Agent, Fully Explained (Beginner → Deep)

This is a from-scratch, function-by-function walkthrough of how the "agent" part of
FireWatch works — what an agent even is, why this project needed one, and exactly
what every function in `agent/*.py` (plus the `fuse()` function it depends on)
does and why. Written for someone who has never touched LangGraph, FastAPI, or
agent orchestration before.

Every section follows: **Intuition → Logic/Math → Code → Connection → Check
Yourself**. Read top to bottom the first time — later sections assume you
understood the earlier ones.

---

## Part 0 — The Big Picture Before Any Code

### 🧠 Intuition

Imagine you have a smoke detector at home, but instead of just beeping, it's
smart: it looks at a camera feed AND gas sensors, and when it thinks there's a
fire, it doesn't just scream immediately — it:

1. Decides how serious the situation is (a person, or rather, deterministic code,
   already did this part).
2. Looks up the nearest fire station so you have a phone number handy.
3. Writes you a calm, readable text message explaining what's happening.
4. Sends that message to your phone (Telegram) and also as a backup SMS.
5. Waits 60 seconds in case you say "false alarm, cancel."
6. If you don't cancel, it logs a **simulated** dispatch (this is a student
   project — it never calls real 911/112 services) and writes down what
   happened so future analysis can improve the system.

That entire six-step dance — locate, compose a message, notify, escalate,
wait, then branch into "cancelled" or "dispatch" — is what we call **the
agent**. It's not "AI that decides if there's a fire." The fire/no-fire
decision was already made by boring, predictable if/else code (`fuse()` in
`edge/fusion.py`). The agent's job starts *after* that decision, and its job
is entirely about **response**, not detection.

**Analogy:** Think of `fuse()` as a doctor who's already diagnosed a patient
("this is WARNING-level pneumonia"). The **agent** is the hospital's response
protocol staff — the one who calls the specialist, preps the room, notifies
the family, and follows a checklist. The response staff never re-diagnoses
the patient; they just execute a very reliable, ordered checklist once a
diagnosis is handed to them. If they went off-script and started
re-diagnosing patients on their own judgment, that would be dangerous — so by
design, they don't get that power. In this project, that's a hard rule
enforced in the code, not just a convention.

### 📐 Why "agent" and why "graph"?

In modern AI systems, an **agent** usually means: something that (a) holds
state, (b) takes actions in the world (send a message, call an API, wait for
input), and (c) makes some decisions along the way — sometimes with an LLM in
the loop, sometimes not. This project's agent barely uses an LLM at all — it
uses one, in exactly one place, for text *phrasing only* (never for
deciding). Almost everything else is deterministic Python functions wired
together as a **state machine**.

A **state machine** is just: a set of named steps ("nodes"), and rules about
which step comes after which ("edges"). You start in one step, state flows
through, and eventually you reach an "end" step. `LangGraph` is a Python
library this project uses to build exactly that kind of state machine, where
each node is a plain Python function that receives a dictionary of data
("state"), maybe changes it, and returns it.

**Why not just write one big Python function with a bunch of `if` statements
top to bottom?** You could! Functionally it would behave the same. The value
of the graph library is:
- It gives you a clean mental model: "state goes node → node → node."
- It makes branching explicit as a diagram-like structure (`add_conditional_edges`)
  instead of buried `if/else` logic.
- It's a step toward frameworks that DO support LLM-driven branching later,
  even though this project deliberately keeps branching fixed and non-LLM
  (more on that below — it's a safety decision, not a limitation of the
  library).

### 🔗 Connection

You'll see this pattern — "deterministic core, LLM only for polish, no LLM
in the decision path" — increasingly in real-world AI engineering, because
letting an LLM make safety-critical decisions (should we call emergency
services?) is risky: LLMs hallucinate, are non-deterministic, and can be
prompt-injected. This project's design is a good real example of "LLM for
UX, code for judgment."

### ❓ Check Yourself
Before reading on: if the agent never decides *whether* there's a fire, what
information does it actually need to be handed in order to do its job? (Hint:
look at what a hospital response team needs on the sheet handed to them by
the doctor.)

---

## Part 1 — `fuse()`: The Decision the Agent Trusts Blindly

This isn't technically part of `agent/`, but you cannot understand the agent
without understanding what it's reacting to. This lives in
`edge/fusion.py`.

### 🧠 Intuition

Picture two witnesses to a possible crime. One witness (the camera / vision
model) says "I think I saw fire." Another witness (gas sensors) says "I smell
gas." If only ONE witness is confident, you're suspicious but not certain —
maybe the camera got fooled by a TV showing a fire scene (this literally
happened during testing — Phase 5's "block-bar failure": a TV playing fire
footage triggered 7 false alarms). But if BOTH witnesses agree independently,
that's much stronger evidence, because it's unlikely that two unrelated
sensors would be wrong in the same way at the same time.

That's the entire design philosophy of `fuse()`: never trust one sensor
alone for the most serious response level. Only agreement between
**independent** signals earns the top severity tier.

### 📐 The Logic

`fuse()` takes four booleans and returns a `(Level, reason)` pair:

```
fuse(vision_fire, vision_smoke, gas_high, temp_spiking) -> (Level, reason)
```

- `vision_fire`: did the camera's ML model see flames?
- `vision_smoke`: did it see smoke?
- `gas_high`: are gas sensor readings (MQ2/MQ135) above a "warn" threshold?
- `temp_spiking`: is temperature rising fast? (Always `False` — no temp
  sensor exists in this build; more on that below.)

`Level` is an ordered scale:
```
SAFE (0) < WATCH (1) < WARNING (2) < CRITICAL (3)
```
It's an `IntEnum` — an enum whose members are also integers — specifically
*so that* code elsewhere can write `if level >= Level.WARNING` and get correct
ordering "for free," instead of maintaining a second lookup table that could
drift out of sync with this one. That's a subtle but important software
engineering habit: **don't duplicate an ordering; derive comparisons from a
single source of truth.**

The rules are checked in strict priority order — first match wins:

| # | Condition | Result | Why |
|---|-----------|--------|-----|
| 1 | `(vision_fire or vision_smoke) and gas_high` | CRITICAL | Two independent signals agree — the only path to CRITICAL in this hardware build |
| 2 | `vision_fire and temp_spiking` | CRITICAL | Disabled in practice (see below) |
| 3 | `gas_high` and no vision hazard | WARNING | Real hazard class (leak, smoke out of camera frame) but visually unconfirmed |
| 4 | `vision_fire` alone | WARNING (capped!) | Deliberately NOT critical — this is the TV/false-alarm mitigation |
| 5 | `vision_smoke` alone | WATCH | Early warning, not yet an alarm |
| — | none of the above | SAFE | Nominal |

**What happens at the extremes?** If every input is `False`, you fall through
every rule and land on `SAFE` — the function always terminates with an
answer, there's no "undefined" case. If everything is `True`, rule 1 fires
first and wins, because it's checked first — this is why "first match wins"
ordering matters: rule 1 must be checked before rule 4, or a genuine
double-confirmed fire could incorrectly be downgraded.

**Why is rule 2 "disabled"?** There's a `temp_spiking()` function that is a
**stub** — a placeholder function that always returns `False`:

```python
def temp_spiking() -> bool:
    return False
```

The project's hardware doesn't currently include a temperature sensor (it
was cut for cost reasons in an earlier build phase). Rather than deleting
rule 2 from `fuse()` entirely, the developer kept the rule *structurally
present* but made its only real-world input source always return `False`.
This is a nice pattern to learn: **when a feature is temporarily unavailable,
disable it at its narrowest input point, not by ripping out the logic that
depends on it.** That way, when a temperature sensor is added later, you
change ONE function (`temp_spiking()`) and rule 2 becomes live — `fuse()`
itself never needs to change.

### 💻 The Code

```python
def compute_gas_high(mq2: float, mq135: float, thresholds: dict) -> bool:
    # True if EITHER gas sensor is at/above its "warn" threshold.
    # Uses warn (not the more severe "danger" threshold) because here
    # gas_high's job is corroboration — agreeing with a visual hazard
    # is already independent confirmation. Waiting for "danger"-level
    # gas would delay a CRITICAL alert during a real fire, and missing
    # a real fire is judged the worse failure mode.
    return mq2 >= thresholds["mq2_warn"] or mq135 >= thresholds["mq135_warn"]


def fuse(vision_fire, vision_smoke, gas_high, temp_spiking):
    if (vision_fire or vision_smoke) and gas_high:
        return Level.CRITICAL, "visual hazard confirmed by gas sensor"
    if vision_fire and temp_spiking:
        return Level.CRITICAL, "flame detected with rapid temperature rise"
    if gas_high and not (vision_fire or vision_smoke):
        return Level.WARNING, "gas concentration high, no visible flame"
    if vision_fire:
        return Level.WARNING, "visual flame, unconfirmed by sensors"
    if vision_smoke:
        return Level.WATCH, "possible smoke, monitoring"
    return Level.SAFE, "nominal"
```

Notice: no network calls, no ML inference happening *inside* this function,
no randomness. Give it the same four booleans twice, get the same answer
twice. That's what "deterministic" means, and it's called out explicitly in
the code comments as a safety property (`info.md 2.3`): **detection logic
must be predictable and auditable, not a black box.**

### 🔗 Connection

This is your first real-world example of **defense in depth** / **sensor
fusion** — a core concept in robotics, self-driving cars, and safety
systems generally: never let one imperfect sensor unilaterally trigger your
most severe action. You'll see the same idea called "multi-modal
verification" in security systems (e.g., requiring both a badge AND a PIN)
and in ML (ensembling multiple models and only trusting agreement).

This is also where the entire rest of the agent's "trust boundary" begins:
everything downstream — Telegram messages, SMS, simulated dispatch — treats
`fuse()`'s output as ground truth and never questions it again.

### ❓ Check Yourself
If a wildfire produced smoke but the camera was pointed away from the actual
flames (so `vision_fire=False`, `vision_smoke=True`) and gas sensors hadn't
yet risen (`gas_high=False`), what Level would `fuse()` return, and is that
the right call given the project's stated priority that "missing a real fire
is the worst failure"?

---

## Part 2 — What Is LangGraph, Concretely?

### 🧠 Intuition

Think of a flowchart you'd draw on a whiteboard for "what happens after
someone reports a fire": box 1 leads to box 2 leads to box 3, and at one
point there's a diamond (a yes/no branch) that sends you down one of two
paths. LangGraph is just a Python way of writing that flowchart so that:
- each **box** is a plain Python function taking a dictionary and returning
  a (possibly modified) dictionary,
- each **arrow** is code saying "after node A, go to node B,"
- diamonds (**branches**) are a function that looks at the current dictionary
  and returns the *name* of the next node.

### 📐 The Mechanics

Three building blocks, all used in `agent/graph.py`:

1. **State type** — a `TypedDict` describing what shape the dictionary has
   as it flows through the graph (this is just documentation + type-checking
   help; Python doesn't enforce it at runtime, but your editor and `mypy`
   would catch mistakes).

2. **Nodes** — `g.add_node("name", function)`. Each function's signature is
   always `(state: IncidentState) -> IncidentState`. It typically mutates a
   few keys and returns the whole state.

3. **Edges** — `g.add_edge("A", "B")` means "after A finishes, always go to
   B" (a **fixed edge** — no decision involved). `g.add_conditional_edges(
   "A", router_fn, {"x": "X", "y": "Y"})` means "after A, call `router_fn(state)`;
   whatever string it returns, look it up in this dict to find the next node."

### 💻 The Code (from `agent/graph.py`)

```python
def build_graph() -> Any:
    g = StateGraph(IncidentState)
    for name, fn in [("verify", verify), ("locate", locate), ("compose", compose),
                     ("notify_owner", notify_owner), ("escalate", escalate),
                     ("wait", wait), ("cancelled", cancelled), ("simulate", simulate)]:
        g.add_node(name, fn)
    g.set_entry_point("verify")
    g.add_edge("verify", "locate")
    g.add_edge("locate", "compose")
    g.add_edge("compose", "notify_owner")
    g.add_edge("notify_owner", "escalate")
    g.add_edge("escalate", "wait")
    g.add_conditional_edges(
        "wait",
        lambda s: "cancelled" if s.get("cancelled") else "simulate",
        {"cancelled": "cancelled", "simulate": "simulate"},
    )
    g.add_edge("cancelled", END)
    g.add_edge("simulate", END)
    return g.compile()
```

Read this like a sentence: "Start at `verify`. Always go to `locate`. Always
go to `compose`. Always go to `notify_owner`. Always go to `escalate`. Always
go to `wait`. AFTER `wait`, check `state["cancelled"]` — if `True`, go to
`cancelled`, else go to `simulate`. Either of those is the end."

`g.compile()` turns this description into an actual runnable object — an
"app" — with one method you care about: `.invoke(initial_state)`, which runs
the whole pipeline start to finish and returns the final state dictionary.

```python
def run_incident(payload: dict) -> dict:
    return dict(build_graph().invoke(payload))
```

That's it — this is the ENTIRE orchestration call. One line. Everything else
is what happens *inside* the nodes.

### 🔗 Connection

Why does the project bother with a graph library instead of just calling
eight functions in a row inside one Python function? Two real reasons stated
in the code comments:
1. **The branch is explicit and impossible to accidentally skip.** The
   comment says "notify_owner can never be skipped, and no LLM output can
   alter the route — compose writes text, the edges are wired at build
   time." If you wrote this as nested if/else by hand, a future refactor
   could accidentally reorder things or add a hidden early return. The graph
   makes the wiring a first-class, inspectable object.
2. It matches an industry-standard mental model (LangGraph is widely used
   for "agentic" LLM applications), so this pattern transfers directly to
   more complex agents you'll build later — ones where some nodes really are
   LLM calls that pick the next action.

### ❓ Check Yourself
Why do you think `notify_owner` (Telegram) is wired to run *before*
`escalate` (Twilio/SMS) rather than the other way around, or in parallel?
(Hint: re-read the comment "Twilio is informational only... a Twilio failure
can never block or delay the primary must-not-fail channel.")

---

## Part 3 — `agent/server.py`: The Front Door

### 🧠 Intuition

The camera/sensor loop (`edge/main.py`, running continuously on the edge
device) needs to hand off an incident to the agent and then *immediately go
back to watching the camera* — it cannot sit around waiting 60+ seconds for
the agent to finish sending messages and polling for a cancel reply. That
would mean the camera stops monitoring during every single alert, which is
obviously bad (what if a second, unrelated fire starts while it's waiting?).

The solution is a classic web-development pattern: a **fire-and-forget HTTP
endpoint with a background task**. The edge loop sends one HTTP POST request
and gets back an instant "ok, got it" response — the actual slow work (the
graph) runs afterward, off to the side, in the background.

### 📐 The Mechanics

FastAPI is a Python web framework. `@app.post("/incident")` means: "when
someone sends an HTTP POST request to `/incident`, run this function."
`BackgroundTasks` is FastAPI's mechanism for saying "do this extra work
*after* I've already sent my response back to the caller."

### 💻 The Code, Function by Function

**The `Incident` model** — this defines the exact JSON shape the edge device
must send:

```python
class Incident(BaseModel):
    level: str        # "WARNING" or "CRITICAL" — fuse()'s verdict, already decided
    reason: str        # fuse()'s reason string
    vision: dict       # p_fire, votes, alarm, smoke — raw model outputs
    sensors: dict       # mq2, mq135, gas_high, gated — raw sensor readings
    snapshot_b64: str | None = None   # the camera frame, base64-encoded
    timestamp: str | None = None
```

`BaseModel` comes from Pydantic — FastAPI automatically validates any
incoming JSON against this shape and rejects malformed requests before your
code even runs. This is the boundary I mentioned earlier: the agent's
`verify` node still double-checks `level`, but the wire format itself is
already locked down here.

**`_save_snapshot`** — decodes the base64 image string back into real JPEG
bytes and writes it to disk:

```python
def _save_snapshot(snapshot_b64: str, event_stamp: str) -> str | None:
    snapshot_dir = Path(_CONFIG["agent"]["snapshot_dir"])
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{event_stamp}.jpg"
    try:
        path.write_bytes(base64.b64decode(snapshot_b64))
        return str(path)
    except (binascii.Error, ValueError, OSError) as exc:
        logger.warning("snapshot decode/save failed (%s) — alert continues without it", exc)
        return None
```

Why is the image sent as base64 text instead of a raw file upload? Because
it's simpler to bundle inside one JSON payload alongside the other fields —
base64 just means "represent binary bytes as printable text characters," at
the cost of the data being ~33% larger. Notice the `try/except`: if decoding
fails for any reason, the function returns `None` instead of crashing — the
comment says *"a bad snapshot never costs the alert."* That's a recurring
philosophy across this whole codebase: **a secondary feature failing must
never take down the primary safety feature (the alert itself).**

**`_run`** — the actual background work, wrapped in error handling:

```python
def _run(payload: dict) -> None:
    try:
        final = run_incident(payload)
        logger.info("incident %s handled: delivered=%s cancelled=%s", ...)
    except Exception:
        logger.exception("agent graph failed for incident")
```

Why catch a bare `Exception` here, which is usually considered bad practice?
Because this function runs inside a FastAPI `BackgroundTasks` job — if an
exception escapes a background task, FastAPI just silently swallows it; you'd
never know the graph crashed. So the comment explains: *"an unhandled error
here would vanish silently."* Catching and logging it is the only way to see
the failure at all.

**`incident` (the actual endpoint)**:

```python
@app.post("/incident")
def incident(inc: Incident, background: BackgroundTasks) -> dict[str, str]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = inc.model_dump(exclude={"snapshot_b64"})
    payload["snapshot_path"] = _save_snapshot(inc.snapshot_b64, stamp) if inc.snapshot_b64 else None
    if not payload.get("timestamp"):
        payload["timestamp"] = datetime.now().isoformat(timespec="seconds")
    background.add_task(_run, payload)
    return {"status": "accepted"}
```

Step by step:
1. Make a timestamp string to name the snapshot file uniquely.
2. `inc.model_dump(exclude={"snapshot_b64"})` — convert the validated
   Pydantic object back into a plain dict, but drop the giant base64 image
   string from it (it's been saved to disk already; no need to keep hauling
   it around in memory through the whole graph).
3. Attach the saved file *path* instead (much smaller, and every downstream
   node just needs the path to attach the photo to Telegram, not the raw
   bytes).
4. Fill in a timestamp if the caller didn't send one.
5. `background.add_task(_run, payload)` — schedule `_run(payload)` to
   execute *after* this function returns its HTTP response.
6. `return {"status": "accepted"}` — this happens **immediately**, before
   the graph has even started. The edge device gets its fast response and
   goes back to watching for the next frame.

**`health`** — a trivial endpoint (`GET /health` → `{"status": "ok"}`) used
to check the server process is alive. Standard practice in any deployed
service — you need a cheap way to ask "are you up?" without triggering real
work.

### 🔗 Connection

This "accept fast, process slow, in the background" pattern is everywhere in
real backend systems — e.g., when you upload a video to YouTube, the upload
endpoint returns instantly, but transcoding happens in a background job
queue afterward. You just learned a miniature, single-process version of
that same idea.

### ❓ Check Yourself
The docstring says the server "binds to 127.0.0.1 only... a same-machine
companion process, not an exposed service." What security risk would exist
if it instead bound to `0.0.0.0` (all network interfaces) on a device also
connected to the internet?

---

## Part 4 — `agent/graph.py` Nodes, One at a Time

Now the heart of the system. Recall the state dictionary (`IncidentState`)
flows through 8 nodes in this order:

```
verify → locate → compose → notify_owner → escalate → wait → {cancelled | simulate}
```

### `IncidentState` — the shared dictionary shape

```python
class IncidentState(TypedDict, total=False):
    level: str
    reason: str
    timestamp: str
    event_id: str
    vision: dict
    sensors: dict
    snapshot_path: str | None
    station: dict
    alert_text: str
    delivered: bool
    twilio: dict
    update_offset: int
    cancelled: bool
```

`total=False` means none of these keys are *required* to be present at
every point — different nodes fill in different keys as state progresses.
Think of it as a form that starts mostly blank and gets filled in field by
field as it passes through each department.

---

### Node 1: `verify`

**🧠 Intuition:** A bouncer at a club checking a wristband, not deciding
who's allowed in. The decision ("is this person allowed?") was already made
elsewhere; the bouncer's only job is refusing entry to someone who obviously
skipped that step.

**💻 Code:**
```python
def verify(state: IncidentState) -> IncidentState:
    if state.get("level") not in ("WARNING", "CRITICAL"):
        raise ValueError(
            f"agent invoked with level={state.get('level')!r} — the agent only "
            "runs on fuse()'s WARNING-or-above verdicts"
        )
    state.setdefault("event_id", str(uuid.uuid4()))
    state.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
    return state
```
- If `level` isn't `WARNING` or `CRITICAL`, it **raises an exception** —
  refuses to proceed. It never "corrects" a bad level or upgrades a `SAFE`
  incident to something else — that would be the agent making a
  fire/no-fire judgment, which is explicitly forbidden.
- `state.setdefault(key, value)` — a dict method that says "set this key to
  `value` ONLY IF it isn't already set." Used here to generate a random
  unique ID (`uuid.uuid4()`) for this incident, and a timestamp, but only if
  the caller didn't already provide them — useful both for real incidents
  (edge device usually sends a timestamp) and for the fire-drill test mode
  at the bottom of the file (which doesn't).

**🔗 Connection:** This is a **guard clause** / **fail-fast** pattern —
extremely common in production code: check your assumptions loudly and
immediately at the entry point, rather than letting bad data silently
propagate deep into a system where the eventual crash is confusing and far
from its root cause.

---

### Node 2: `locate`

**🧠 Intuition:** Before texting you "there might be a fire," it's useful to
also hand you the nearest fire station's phone number so you don't have to
Google it yourself while panicking. This node's ENTIRE job is that lookup —
nothing more.

**💻 Code:**
```python
def locate(state: IncidentState) -> IncidentState:
    cfg = _config()
    loc, agent_cfg, fallback_cfg = cfg["location"], cfg["agent"], cfg["emergency_fallback"]
    state["station"] = find_nearest_fire_station(
        float(loc["latitude"]), float(loc["longitude"]),
        int(agent_cfg["overpass_radius_m"]), agent_cfg["overpass_url"],
        float(agent_cfg["overpass_timeout_seconds"]),
        str(fallback_cfg["fire_number"]), str(fallback_cfg["unified_number"]),
    )
    return state
```
It reads config values (lat/lon of the house, search radius, a timeout, and
fallback emergency numbers) and delegates the actual lookup to
`find_nearest_fire_station` (in `agent/locate.py`, covered in Part 5). The
result — a dict — gets stored under `state["station"]`.

**🔗 Connection:** Notice the *separation of concerns*: `graph.py` doesn't
know or care HOW the lookup happens (an API call to OpenStreetMap, retries,
distance math) — it just calls a function and stores the result. This is
good software design: each file has one job, and `graph.py`'s job is
*sequencing*, not *implementing*.

---

### Node 3: `compose`

**🧠 Intuition:** Turning a robotic verdict ("CRITICAL, visual hazard
confirmed by gas sensor") into something a stressed human can read in two
seconds and understand. This is the ONE node that calls an LLM.

**💻 Code:**
```python
def compose(state: IncidentState) -> IncidentState:
    agent_cfg = _config()["agent"]
    state["alert_text"] = compose_alert_text(
        dict(state), agent_cfg["groq_model"], float(agent_cfg["groq_timeout_seconds"])
    )
    return state
```
Delegates to `compose_alert_text` in `agent/compose.py` (Part 6) — the
important design point (covered in depth there) is that the LLM only
produces *text*, never a decision.

---

### Node 4: `notify_owner`

**🧠 Intuition:** This is the moment the actual alert message goes out to
your phone via Telegram — the single most important step in the whole
pipeline. Everything before this was preparation; this is the "must not
fail" action.

**💻 Code (annotated):**
```python
def notify_owner(state: IncidentState) -> IncidentState:
    vision = state.get("vision") or {}
    sensors = state.get("sensors") or {}
    logger.info(  # full technical detail goes to the SERVER LOG, not the phone
        "incident %s %s (%s): p_fire=%s votes=%s mq2=%s mq135=%s gas_high=%s",
        state.get("event_id"), state["level"], state["reason"],
        vision.get("p_fire"), vision.get("votes"),
        sensors.get("mq2"), sensors.get("mq135"), sensors.get("gas_high"),
    )
    base = float(_config()["fusion"]["cancel_window_seconds"])
    message = (
        f"{state['alert_text']}\n\n"
        f"{_station_line(state)}\n\n"
        f"{_emergency_numbers_line(state)}\n\n"
        f"Reply CANCEL within {base:.0f} seconds to stop escalation."
    )
    print(f"--- Telegram message ---\n{message}\n------------------------")
    state["update_offset"] = latest_update_id()   # <-- baseline BEFORE sending
    state["delivered"] = send_telegram(message, state.get("snapshot_path"))
    return state
```

Two subtle but important details:

1. **The message shown to the human contains ZERO raw numbers** —
   no `p_fire=0.91`, no `mq2=181`. Those numbers go into the *server log*
   (via `logger.info`) for the developer to debug with, but the actual
   Telegram text is composed entirely of human sentences. The comment
   explicitly calls this out: raw technical context must stay out of a
   message going to "the stressed person's phone."

2. **`state["update_offset"] = latest_update_id()` happens BEFORE
   `send_telegram(...)`.** This is a genuinely clever detail worth
   understanding deeply — it's explained fully in Part 7 (`poll_for_cancel`),
   but the short version: Telegram's API for reading messages
   (`getUpdates`) returns *all* messages including old ones unless you tell
   it "only messages after this ID." By recording the current latest
   message ID right before sending the alert, the later cancel-check can
   ignore anything the user typed *before* the alert existed — otherwise an
   old stray "cancel" message from last week could falsely cancel today's
   real fire alert.

---

### Node 5: `escalate`

**🧠 Intuition:** A backup notification channel (SMS via Twilio), sent to
the developer's OWN phone, purely as a redundant, one-way heads-up — in case
Telegram somehow fails or isn't checked. It is explicitly informational: no
cancel mechanism exists over SMS.

**💻 Code:**
```python
def escalate(state: IncidentState) -> IncidentState:
    agent_cfg = _config()["agent"]
    sms_text = compose_sms_text(
        dict(state), _emergency_numbers_line(state), _station_line(state),
        llm_text=state.get("alert_text"),
    )
    state["twilio"] = send_twilio_alerts(sms_text, float(agent_cfg["twilio_timeout_seconds"]))
    return state
```
Note it runs **after** `notify_owner`, never before — this ordering is
enforced by the fixed graph edges, and it exists so that if Twilio's network
call hangs or fails, it can never delay or block the Telegram alert, which
has already gone out by this point.

---

### Node 6: `wait`

**🧠 Intuition:** A countdown timer, like the "press CANCEL within 10
seconds" prompt on a microwave before it actually starts cooking —
except here it's "reply CANCEL on Telegram within 60 seconds or we assume
this is real."

**💻 Code:**
```python
def wait(state: IncidentState) -> IncidentState:
    cfg = _config()
    window = float(cfg["fusion"]["cancel_window_seconds"])
    print(f"--- cancel window open: reply CANCEL on Telegram within {window:.0f}s ---")
    state["cancelled"] = poll_for_cancel(
        window, float(cfg["agent"]["telegram_poll_seconds"]), state.get("update_offset", 0)
    )
    return state
```
Delegates the actual "keep checking Telegram every N seconds for a CANCEL
reply" loop to `poll_for_cancel` (Part 7). Stores the boolean result.

---

### The Branch

```python
g.add_conditional_edges(
    "wait",
    lambda s: "cancelled" if s.get("cancelled") else "simulate",
    {"cancelled": "cancelled", "simulate": "simulate"},
)
```
A one-line function inspects `state["cancelled"]` and routes accordingly.
This is the ONLY decision point in the entire graph, and notice: it's a
plain boolean check on data the deterministic `poll_for_cancel` function
already computed. No LLM call happens here. That's deliberate — re-read
the module docstring: *"no LLM output can alter the route."*

---

### Node 7a: `cancelled`

**🧠 Intuition:** The "false alarm" outcome. Someone said "stop" in time.

**💻 Code:**
```python
def cancelled(state: IncidentState) -> IncidentState:
    logger.info("event %s CANCELLED by owner — logged as false alarm, no dispatch", ...)
    print("--- owner replied CANCEL: false alarm, escalation stopped ---")
    cfg = _config()
    packet = _incident_packet(state, owner_response="cancelled by owner within window")
    _upload_critical(state, cfg, packet)
    append_feedback(dict(state), cfg, cancelled=True, path=cfg["agent"]["feedback_log"])
    return state
```
No dispatch is logged. But a feedback row IS still written (reward = -1,
"this alert was wrong or unwanted" — see Part 8) and, if the level was
CRITICAL, the incident is still uploaded to cloud storage for later human
review — because "the developer said false alarm" is itself useful data for
improving the model later, even though nothing was dispatched.

### Node 7b: `simulate`

**🧠 Intuition:** The "no one cancelled in time" outcome — the system
proceeds as if it would dispatch emergency services, but **it never actually
contacts anyone real.** It writes a JSON line to a local file and prints a
loud banner making that limitation impossible to miss.

**💻 Code:**
```python
def simulate(state: IncidentState) -> IncidentState:
    cfg = _config()
    packet = simulate_dispatch(dict(state), cfg["agent"]["dispatch_log"])
    _upload_critical(state, cfg, packet)
    append_feedback(dict(state), cfg, cancelled=False, path=cfg["agent"]["feedback_log"])
    return state
```

**🔗 Connection — why does a student project bother "simulating" dispatch
instead of just skipping that step?** Because the whole point of the
project is to demonstrate an end-to-end pipeline that *could* eventually be
connected to a real dispatch API, without actually calling one — this is
standard practice when prototyping anything with real-world consequences
(imagine testing a self-driving car's braking logic in a simulator before
letting it touch a real road).

---

### Helper functions inside `graph.py`

- **`_config()`** — just re-reads `config.yaml` fresh every call. Simple,
  slightly wasteful (re-parses the file each time), but guarantees you never
  work with stale config if it changes between incidents.
- **`_station_line(state)`** / **`_emergency_numbers_line(state)`** — pull
  pieces of text (the fire station line, the 101/112 fallback numbers line)
  used in both the Telegram message and the SMS body, so both channels stay
  consistent in wording.
- **`_incident_packet(state, owner_response)`** — builds a dict describing
  the incident for logging/upload purposes, tagging it with what the human
  did (`"cancelled by owner within window"` etc.).
- **`_upload_critical(state, cfg, packet)`** — uploads to cloud storage
  (S3, via `cloud/uploader.py`) but ONLY for CRITICAL incidents, and reads
  the snapshot image bytes from disk first if one exists. This keeps the
  cheaper, more frequent WARNING incidents out of cloud storage while still
  capturing the most important CRITICAL ones (both dispatched and
  cancelled) for later model-quality review.

### ❓ Check Yourself (Part 4)
`_upload_critical` is called from BOTH `cancelled` and `simulate`. Given that
the graph always reaches exactly one of those two nodes per run (never
both), does calling `_upload_critical` from both places risk uploading the
same incident twice? Why or why not?

---

## Part 5 — `agent/locate.py`: Finding the Fire Station

### 🧠 Intuition

You want to tell the phone's owner "here's the number to call" without your
system ever being allowed to call it *for* them. This file's core rule,
repeated multiple times in the comments, is: **display-only.** The phone
number is text embedded in a message — it is NEVER used as a destination
for any outgoing call or message the system itself makes.

### 📐 The Math: Haversine Distance

To find the *nearest* station among several candidates, you need to compute
distance between two points given as (latitude, longitude). Straight-line
Euclidean distance ("Pythagorean theorem") doesn't work correctly on a
sphere — the Earth is curved, so two points 1 degree of longitude apart near
the equator are much farther apart than two points 1 degree apart near the
poles.

The **haversine formula** computes great-circle distance (the shortest path
along the surface of a sphere) between two lat/lon points:

```
a = sin²(Δφ/2) + cos(φ1)·cos(φ2)·sin²(Δλ/2)
distance = 2 · R · asin(√a)
```
Where:
- `φ1, φ2` = the two points' latitudes, in **radians** (not degrees — trig
  functions in most programming languages expect radians)
- `Δφ` = difference in latitude, `Δλ` = difference in longitude
- `R` = Earth's radius (~6371 km)
- `asin` = arcsine (inverse sine)

**What's it saying in one sentence?** It converts the angular separation
between two points on a sphere into an actual great-circle arc-length
distance, accounting for the fact that the sphere curves.

**At the extremes:** if the two points are identical, `Δφ = Δλ = 0`, so
`a = 0`, and `distance = 2·R·asin(0) = 0` — correct, zero distance. If the
two points are on opposite sides of the Earth, `a` approaches 1, `asin(1) =
π/2`, giving `distance = 2·R·(π/2) = π·R` — half the Earth's circumference,
which is indeed the maximum possible great-circle distance.

### 💻 The Code

```python
def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))
```
This is a direct line-for-line translation of the formula above. The
comment notes it's accurate to "~0.5%" — plenty precise for "which station
is closer," even though it's not perfectly accurate (Earth isn't a perfect
sphere; this ignores that, which is a totally reasonable simplification
here).

### `find_nearest_fire_station` — the main function

This function talks to **Overpass API**, a free public query service for
OpenStreetMap data (crowd-sourced map data — anyone can tag a building as
`amenity=fire_station`). The core query, built as a string:

```python
query = (f"[out:json][timeout:{int(timeout)}];"
         f'nwr["amenity"="fire_station"](around:{int(radius_m)},{lat},{lon});'
         f"out center tags;")
```
This is written in **Overpass QL**, Overpass's own query language (not SQL,
not Python) — roughly: "find any node/way/relation (`nwr`) tagged
`amenity=fire_station` within `radius_m` meters of `(lat, lon)`, and give me
back their center coordinate and tags."

The function then:
1. **Rejects `(0.0, 0.0)`** immediately — this is a placeholder value used
   before real GPS coordinates are configured (Null Island, a real point in
   the ocean at 0°,0° that shows up constantly as a bug indicator in mapping
   software when someone forgets to set real coordinates). Querying it would
   "succeed" with meaningless results, so the code fails loudly and falls
   back instead.
2. **Calls `_query_once`** — makes the actual HTTP POST to Overpass, with a
   descriptive `User-Agent` header. (A real bug was found here: Overpass's
   web server was rejecting requests using Python's default generic
   User-Agent string, interpreting it as bot/script traffic — adding an
   honest, identifying User-Agent string fixed it. This is a common
   real-world gotcha when calling public APIs.)
3. **Retries once** if the first attempt fails, waiting `_RETRY_DELAY_SECONDS`
   (2 seconds) — because live testing found Overpass occasionally returns a
   transient error that succeeds on retry seconds later. One retry, bounded,
   so total added delay is small and can never meaningfully threaten the
   60-second cancel window.
4. **Picks the closest result** by looping over all returned stations and
   calling `_haversine_km` on each, keeping the minimum.
5. **Falls back gracefully** (`_fallback(...)`) on any failure path — no
   station found, bad coordinates, network failure twice in a row — always
   returning the same dict shape so callers never need special-case
   handling for "it failed."

### 🔗 Connection

This function is a textbook example of **defensive network programming**:
timeouts on every request, a bounded retry (not infinite), graceful
fallback values instead of exceptions bubbling up, and detailed logging of
both successes and failures so a flaky real-world API's behavior is
diagnosable after the fact rather than a mystery.

### ❓ Check Yourself
Why does the code check for `(0.0, 0.0)` specifically, rather than just
letting the Overpass query run with those coordinates and trusting whatever
comes back?

---

## Part 6 — `agent/compose.py`: The Only Place an LLM Is Allowed

### 🧠 Intuition

Imagine a strict newspaper editor who is handed a fact-checked, already
verified story and told: "make this readable for a general audience — you
may not add facts, you may not change what happened, you may only choose
words." That's the LLM's entire job here. It's a copywriter, not a
journalist.

### 📐 Why keep the LLM out of decisions?

This is the single most important design idea in the whole codebase, so
it's worth dwelling on. LLMs are:
- **non-deterministic** (same input can give different output),
- **capable of being manipulated** (prompt injection),
- **capable of confidently stating wrong things** (hallucination).

None of those properties are acceptable for "should we treat this as a
fire emergency?" — but ALL of those properties are perfectly fine, even
desirable, for "phrase this calmly for a stressed reader," because the
worst-case failure of a bad *phrasing* is a slightly awkward sentence, while
the worst-case failure of a bad *decision* could be a missed real fire or a
false emergency dispatch.

So the code enforces a hard boundary: the LLM is given `level` and `reason`
as already-decided facts, is explicitly told in its system prompt never to
second-guess them, is never shown raw sensor numbers (so it *can't* leak
them into the message even by accident), and its output is used *only* as
message body text — **never parsed back into a decision**. If it fails or
times out, deterministic template text is used instead, so the alert
*always* goes out regardless of whether the AI provider is reachable.

### 💻 Code — `compose_alert_text`

```python
def compose_alert_text(state, model, timeout) -> str:
    level = state["level"]
    time_phrase = natural_time_phrase(state["timestamp"])
    template = TEMPLATES.get(level, TEMPLATES["CRITICAL"]).format(time=time_phrase)
    user_msg = (
        f"Tier: {level}\nHazard: {state.get('reason')}\n"
        f"Time phrase to use: {time_phrase}\n"
        f"Write the alert message."
    )
    try:
        client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=timeout)
        reply = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": user_msg}],
            max_tokens=1024,
            temperature=0.3,
        )
        choice = reply.choices[0]
        text = (choice.message.content or "").strip()
        if choice.finish_reason == "length":
            logger.warning("Groq output hit the token cap (truncated) — using template")
        elif text and time_phrase in text:
            return text
        elif text:
            logger.warning("Groq output missing the time phrase %r — using template", time_phrase)
        else:
            logger.warning("Groq returned empty text — using deterministic template")
    except Exception as exc:
        logger.warning("Groq compose failed (%s) — using deterministic template", exc)
    return template
```

Walking through the safety checks, because there are FOUR separate ways this
can fall back to the deterministic template, and each one matters:

1. **`except Exception`** — any network error, API error, or bug in the SDK
   call is caught. The alert still goes out via `template`.
2. **`finish_reason == "length"`** — this means the LLM's response got cut
   off mid-sentence because it hit the maximum token limit. A half-finished
   alert message reaching a phone would be confusing or alarming in the
   wrong way, so this is explicitly rejected in favor of the safe template.
   (There's a subtlety here worth knowing: Groq's `gpt-oss` models are
   *reasoning models* — they spend some of their token budget on invisible
   internal reasoning before producing the visible answer. `max_tokens=1024`
   is deliberately generous to leave room for both, after an earlier bug
   where a tighter cap truncated the visible message.)
3. **`time_phrase not in text`** — the code demands the LLM's output contain
   the *exact* clock-time phrase it was given (e.g., "at 9:29 PM"), verbatim.
   Why? Because LLMs are notoriously bad at "just now" vs. exact times, and
   a debugging developer needs to be able to correlate an alert with
   message history later using a real clock time. If the model ignored the
   instruction and wrote something vague instead, the response is rejected.
4. **Empty text** — obviously invalid, falls back too.

Notice the *shape* of this function: **try the enhanced path, verify its
output meets hard requirements, and only use it if it passes — otherwise
silently and safely degrade.** This "verify LLM output before trusting it"
pattern is extremely important and applicable to almost any real system that
puts an LLM in a user-facing pipeline.

### `natural_time_phrase` — turning an ISO timestamp into "at 9:29 PM"

```python
def natural_time_phrase(iso_timestamp: str) -> str:
    try:
        event = datetime.fromisoformat(iso_timestamp)
    except (ValueError, TypeError):
        event = datetime.now()
    clock = event.strftime("%-I:%M %p")
    if event.date() == datetime.now().date():
        return f"at {clock}"
    return f"at {clock} on {event.strftime('%b %-d')}"
```
`%-I:%M %p` formats a time as `9:29 PM` (12-hour clock, no leading zero,
AM/PM). If the event happened today, you just get "at 9:29 PM"; if it
happened on a different day, the date gets appended too ("at 9:29 PM on Sep
5"). If the input string can't even be parsed as a date at all, it silently
falls back to "now" rather than crashing — because per the file's stated
philosophy, a formatting hiccup must never cost the alert.

### `compose_sms_text` — a second, shorter message

**🧠 Intuition:** SMS has a hard length limit before it starts getting
expensive or outright rejected (especially on trial-tier Twilio accounts).
This function builds a SEPARATE, shorter version of the alert specifically
for SMS, distinct from the fuller Telegram message.

The comments describe a real debugging story worth understanding, because
it's a great example of empirical, evidence-based debugging: Twilio trial
accounts reject SMS bodies over a certain length with error code 30044
("Trial Message Length Exceeded"). The original code reused the full
Telegram text for SMS too, which ran to 4 message "segments" (SMS is
transmitted in ~160-character chunks called segments) and got rejected. The
developer confirmed via the Twilio console that a 3-segment message
succeeded and a 4-segment one failed — so the true limit sits somewhere
between them. Rather than tuning `SMS_CHAR_BUDGET` to sit right at that
observed edge (risky — the real limit is a guess bounded on one side only),
it was set deliberately well below it, trading a little brevity for margin
against future surprises.

```python
def compose_sms_text(state, numbers_line, station_line, llm_text=None) -> str:
    level = state["level"]
    time_phrase = natural_time_phrase(state["timestamp"])
    short_numbers = numbers_line.replace("For any real emergency, call ", "Emergencies: ") \
                                 .replace(" directly.", ".")
    base = SMS_TEMPLATES.get(level, SMS_TEMPLATES["CRITICAL"]).format(
        time=time_phrase, numbers=short_numbers
    )
    def _fits(body): return len(body) <= SMS_CHAR_BUDGET
    candidate = None
    if llm_text and time_phrase in llm_text:
        llm_body = f"{llm_text} {short_numbers}"
        if _fits(llm_body):
            candidate = llm_body
    if candidate is None:
        candidate = base
    with_station = f"{candidate} {station_line}"
    if _fits(with_station):
        return with_station
    return candidate
```

Reading this as a priority list — "try to include as much useful
information as fits, in order of importance":
1. Prefer the nicer LLM-composed text if it exists, contains the required
   time phrase, AND fits within budget alongside the numbers line.
2. Otherwise, fall back to the short deterministic SMS template.
3. THEN, try appending the fire station line too — but only if it still
   fits. If not, silently drop it from SMS specifically (the reader still
   gets that detail from the fuller Telegram message) — an explicit,
   logged tradeoff rather than an accidental truncation.

Also worth noting: **SMS deliberately has no "reply CANCEL" instruction at
all**, unlike Telegram. The comments explain why — actually receiving and
acting on an SMS reply would require standing up a webhook server (a public
URL Twilio can call back to when a reply arrives) plus a tunneling tool like
ngrok to expose a local dev machine to the internet. That's real
infrastructure work (~1-2 hours) for a feature this project's timeline
didn't justify. Rather than add a misleading "reply CANCEL" line on a
channel that can't actually process the reply (which would trick a user
into thinking they cancelled something when nothing happened), the team
explicitly removed it and made SMS purely one-way informational. This is a
mature engineering decision: **when you can't build a feature safely and
completely, don't fake it partially — cut it and be honest about the
narrower scope.**

### ❓ Check Yourself (Part 6)
If Groq's API were down for an entire evening, would any FireWatch alerts
fail to be sent during that time? Trace through `compose_alert_text` to
justify your answer.

---

## Part 7 — `agent/tools.py`: Telegram, the Cancel Window, and "Simulated" Dispatch

### 🧠 Intuition

This file is the "hands" of the agent — the functions that actually reach
out and touch external systems (or, for dispatch, deliberately pretend to).

### `_telegram_call` — the one low-level HTTP helper

```python
def _telegram_call(method, timeout=10.0, **params) -> dict | None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    try:
        resp = requests.post(TELEGRAM_API.format(token=token, method=method),
                             data=params, timeout=timeout)
        body = resp.json()
        if body.get("ok"):
            return body["result"]
        logger.warning("Telegram %s refused: %s", method, body.get("description"))
    except requests.RequestException as exc:
        logger.warning("Telegram %s failed: %s", method, exc)
    return None
```
Every other Telegram function in this file routes through here. It always
returns either the useful result, or `None` — never raises. This is the
single choke point where "Telegram might be down" gets absorbed, so every
caller just needs to handle "got `None` back" rather than catching
exceptions everywhere.

### `send_telegram` — sending the actual alert, with photo-first fallback

```python
def send_telegram(text, photo_path=None) -> bool:
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    for attempt in (1, 2):
        if photo_path and Path(photo_path).is_file():
            try:
                with open(photo_path, "rb") as f:
                    ...
                    resp = requests.post(..., data={"chat_id": chat_id, "caption": text[:1024]},
                                         files={"photo": f}, timeout=15)
                if resp.json().get("ok"):
                    return True
            except (requests.RequestException, ValueError) as exc:
                logger.warning(...)
        if _telegram_call("sendMessage", chat_id=chat_id, text=text) is not None:
            return True
    logger.warning("Telegram delivery failed after retry — alert NOT delivered")
    return False
```
Logic: try up to 2 attempts total. On each attempt, if a snapshot photo
exists, try sending it *with the alert text as the caption* (nicer — you see
the actual fire frame). Telegram captions are capped at 1024 characters,
hence `text[:1024]`. If the photo send fails for any reason, or there's no
photo at all, fall back to a plain text message on that same attempt. Only
after both attempts fail entirely does the function return `False`.

### `latest_update_id` — the cancel-window baseline trick

```python
def latest_update_id() -> int:
    result = _telegram_call("getUpdates", offset=-1, timeout=5)
    if result:
        return result[-1]["update_id"] + 1
    return 0
```
Telegram's `getUpdates` API is how a bot reads incoming messages — every
message has an increasing `update_id`. Calling it with `offset=-1` returns
just the single most recent update. Taking that ID and adding 1 gives you
"the next update ID that would appear, i.e. anything from this point
forward." Storing that number *before* the alert is even sent means: when
you later poll for a CANCEL reply, you can pass this number as your
`offset` and Telegram will only give you messages that arrived *after* this
baseline — completely ignoring any old chat history. Without this, a stray
"cancel" message from three days ago sitting unread in the chat could
incorrectly cancel today's real fire alert the instant polling starts.

### `poll_for_cancel` — the 60-second countdown

```python
def poll_for_cancel(window_seconds, poll_interval, offset) -> bool:
    chat_id = str(os.environ["TELEGRAM_CHAT_ID"])
    deadline = time.monotonic() + window_seconds
    while time.monotonic() < deadline:
        updates = _telegram_call("getUpdates", offset=offset, timeout=5) or []
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message") or {}
            if str(msg.get("chat", {}).get("id")) != chat_id:
                continue
            if "CANCEL" in (msg.get("text") or "").upper():
                return True
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
    return False
```

**📐 The Logic:**
- `time.monotonic()` — a clock that only ever moves forward and is immune to
  the system clock being changed mid-run (e.g., NTP sync, daylight saving,
  someone manually setting the time). For measuring a *duration* like this
  60-second window, `monotonic()` is the correct clock to use — `time.time()`
  could jump backward or forward and corrupt your countdown.
- The `while` loop keeps checking Telegram until `deadline` passes.
- For each new message since `offset`, it advances `offset` (so you never
  re-read the same message twice), checks the message came from the right
  chat (`chat_id`) — ignoring messages from anyone else — and checks whether
  the text contains "CANCEL" (case-insensitive, via `.upper()`). The check
  is a *substring* match, not an exact match — so "please CANCEL this" also
  works, which is a deliberately forgiving, human-friendly match.
- If found, returns `True` **immediately** (early return) — no need to wait
  out the rest of the window once cancelled.
- `time.sleep(min(poll_interval, ...))` — sleeps for the configured poll
  interval, but never sleeps *past* the deadline (the `max(0.0, ...)` guards
  against a negative sleep duration, which would raise an error).
- If the loop exits without ever returning `True`, the function returns
  `False` — no cancel was received in time.
- **Fail-safe design decision:** if `_telegram_call` fails mid-poll (network
  hiccup), it returns `None`, which `or []` turns into an empty list — the
  loop just treats that iteration as "no new messages" and keeps trying on
  the next iteration. The comment explains the reasoning explicitly: a
  network failure during polling must never be silently treated as "the
  user cancelled" — the safe default when uncertain is to proceed toward
  the (simulated) dispatch, not to drop a real hazard because of a flaky
  connection.

### `simulate_dispatch` — the deliberately fake "emergency call"

```python
def simulate_dispatch(state, log_path) -> dict:
    packet = {
        "SIMULATED": True,
        "note": "SIMULATION ONLY — no real emergency service was contacted...",
        "event_id": state.get("event_id", str(uuid.uuid4())),
        ...
    }
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(packet) + "\n")
    banner = "*" * 66
    print(f"\n{banner}\n***  SIMULATED DISPATCH — THIS IS NOT A REAL EMERGENCY CALL  ***")
    ...
    return packet
```
This literally just appends one line of JSON to a local file (this file
format — one JSON object per line — is called **JSONL** or "JSON Lines," a
common format for logs/datasets because you can append to it cheaply without
re-parsing or rewriting the whole file, and you can read it back one record
at a time). Then it prints a very hard-to-miss banner. That's it — no HTTP
request, no phone call, nothing that could reach a real emergency service.
This is stated as an "absolute rule" in the code comments (`info.md 2.1`):
if any future change would let this reach a real emergency service, "stop
and flag it instead" of implementing it. This is the single most important
safety boundary in the entire project, and it's enforced by simply never
writing the code that could cross it, rather than by a runtime check —
which is itself a lesson: **the strongest way to prevent a catastrophic
action is to never write code capable of taking it, not to rely on a
conditional guard that could have a bug.**

### ❓ Check Yourself (Part 7)
Suppose Telegram's API silently went down for the entire 60-second cancel
window (every `getUpdates` call fails). Walk through `poll_for_cancel` and
explain exactly what it returns, and whether that's the safe choice given
this project's stated priority "missing a real fire is the worst failure."

---

## Part 8 — `agent/escalate.py`: The Twilio SMS Boundary

Already covered its role in Part 4/6; here's what's mechanically new.

### `_twilio_post` — the low-level Twilio HTTP call

```python
def _twilio_post(resource, timeout, **params) -> bool:
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    to, frm = params.get("To"), params.get("From")
    logger.info("Twilio %s request: To=%s From=%s", resource, to, frm)
    try:
        resp = requests.post(TWILIO_API.format(sid=sid, resource=resource), data=params,
                             auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]), timeout=timeout)
        if resp.status_code < 300:
            ...
            return True
        logger.warning("Twilio %s refused (HTTP %d): %s", ...)
    except requests.RequestException as exc:
        logger.warning(...)
    return False
```
Twilio's API uses **HTTP Basic Auth** — `auth=(sid, auth_token)` — a simple
authentication scheme where the account ID and a secret token are sent with
every request. Notice the log line prints `To`/`From` (phone numbers) but
explicitly never the SID or auth token — logging secrets is a real security
mistake this code deliberately avoids.

### `send_twilio_alerts` — where the destination number is locked down

```python
def send_twilio_alerts(sms_text, timeout) -> dict[str, bool]:
    try:
        to = os.environ["TWILIO_TO_NUMBER"]        # the developer's own phone
        sender = os.environ["TWILIO_FROM_NUMBER"]
    except KeyError as exc:
        logger.warning(...)
        return {"call": False, "sms": False}
    body = sms_text
    call_ok = False   # voice call permanently disabled, code kept but commented out
    result = {"call": call_ok, "sms": _twilio_post("Messages", timeout, To=to, From=sender, Body=body)}
    return result
```
The critical safety property here: `to` comes from an environment variable
that is hardcoded to be the developer's own phone — the fire station's
number is never plugged into this `to` field anywhere in the codebase; it
only ever appears as text *inside* the message body. That's the difference
between "informational content" and "a destination" — worth understanding
precisely, since it's the exact same distinction that keeps this whole
system from ever being able to auto-dial 911/112.

Also notice the commented-out voice-call code, deliberately left in the
file rather than deleted, with an explanation of exactly why it's disabled
(Twilio trial accounts gate calls behind an interactive "press any key"
prompt, defeating a one-way informational call) and under what condition it
might be revisited (a paid account). This is a good habit: **when you
disable a feature for a documented, specific reason, leave a trail
explaining why, rather than deleting the code and losing that context.**

### ❓ Check Yourself
Why does `send_twilio_alerts` check for missing environment variables with a
`try/except KeyError` and return early, rather than letting Python's default
`KeyError` exception propagate up and crash the whole graph run?

---

## Part 9 — `agent/feedback.py`: Logging for a Future That Isn't Built Yet

### 🧠 Intuition

Imagine a scientist recording every experiment's setup and outcome in a lab
notebook — not because they're using the data yet, but because good
experimental practice means you never throw away data you might want later.
This file writes exactly one row per resolved incident to a CSV file. It
does NOT do anything with that data — no automatic threshold tuning, no
reinforcement learning happens here or anywhere else in this codebase, even
though the schema is clearly *designed* with a future RL system in mind.

### 📐 The Reward Mapping

```
CANCELLED (developer replied CANCEL)  -> reward = -1  (labeled false alarm)
TIMEOUT   (window expired, no reply)  -> reward = +1  (implicit confirmation)
```

This is the vocabulary of **reinforcement learning (RL)**: an agent takes an
action, the world gives back a reward signal, and (in a full RL system) the
agent would use that signal to adjust its future behavior. Here, only the
*data collection* half exists — think of it as "recording exam scores
without yet building the tutoring system that would use them to adjust
lesson plans."

**Why is a timeout worth `+1` (weaker evidence than an outright confirmation
would be) rather than something stronger?** Because a person not replying
doesn't necessarily mean "yes this was a real fire" — they might just not
have seen their phone. The comment is explicit about this nuance: a timeout
is *weaker* evidence than an active reply would be, which is exactly why the
raw `outcome` column (`"CANCELLED"` or `"TIMEOUT"`) is kept alongside the
numeric `reward` — so if you later decide timeouts should count as `0`
(neutral) instead of `+1`, you can recompute that from the stored `outcome`
column without needing to re-run a single real incident.

### 💻 The Code

```python
FIELDNAMES = [
    "timestamp", "event_id",
    "level", "p_fire", "mq2", "mq135", "gas_high", "votes",
    "mq2_warn", "mq2_danger", "mq135_warn", "mq135_danger",
    "fire_decision_threshold", "votes_needed",
    "outcome", "reward",
]

def append_feedback(state, config, cancelled, path) -> None:
    vision = state.get("vision") or {}
    sensors = state.get("sensors") or {}
    s_cfg, v_cfg = config["sensors"], config["vision"]
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event_id": state.get("event_id"),
        "level": state.get("level"),
        "p_fire": vision.get("p_fire"),
        "mq2": sensors.get("mq2"),
        "mq135": sensors.get("mq135"),
        "gas_high": sensors.get("gas_high"),
        "votes": vision.get("votes"),
        "mq2_warn": s_cfg["mq2_warn"],
        "mq2_danger": s_cfg["mq2_danger"],
        "mq135_warn": s_cfg["mq135_warn"],
        "mq135_danger": s_cfg["mq135_danger"],
        "fire_decision_threshold": v_cfg["fire_decision_threshold"],
        "votes_needed": v_cfg["votes_needed"],
        "outcome": "CANCELLED" if cancelled else "TIMEOUT",
        "reward": -1 if cancelled else +1,
    }
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        is_new = not p.exists() or p.stat().st_size == 0
        with open(p, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if is_new:
                writer.writeheader()
            writer.writerow(row)
        logger.info(...)
    except OSError as exc:
        logger.warning("feedback log write failed (%s) — data point lost, "
                       "alert pipeline unaffected", exc)
```

Notice the row records not just the outcome, but the **exact threshold
configuration that was active at the time** (`mq2_warn`, `mq2_danger`,
`votes_needed`, etc. — read live from `config.yaml`). This is the "ACTION"
part of the classic RL framing STATE → ACTION → REWARD: if thresholds get
tuned differently over time, this row-level snapshot means you can later
ask "did this particular threshold configuration produce more false alarms
than that one?" — a question you could never answer if you'd only recorded
the outcome without the config that was live when it happened.

Also notice, again, the `try/except OSError` around the file write — even
this purely-for-later analytics operation is guarded so that a disk error
can never take down the alert pipeline it's attached to. This "never let a
non-critical side effect break a critical path" philosophy has now shown up
in nearly every file — that repetition is intentional, not accidental; it's
the project's central engineering principle applied consistently.

### 🔗 Connection

This is a small, honest example of the difference between "building
infrastructure for a future feature" and "pretending a feature exists." The
schema is RL-shaped and ready, but the docstring is explicit: *"No RL, no
automated threshold adjustment, is built or implied by this file."* That
distinction matters a lot in engineering communication — it's very easy to
accidentally overstate what a system does, and this codebase consistently
avoids that.

### ❓ Check Yourself
If you wanted to eventually build a real RL policy that automatically
adjusts `mq2_warn`/`mq2_danger` thresholds based on this feedback log, what
is the minimum additional piece of code you'd need to write, given that the
data collection already exists?

---

## Part 10 — Tying It All Together: One Incident, Start to Finish

Let's trace a single CRITICAL incident through the entire system, now that
you understand every piece:

1. **Edge device** (`edge/main.py`, not covered here) captures a camera
   frame, runs a vision model, reads MQ2/MQ135 gas sensors, and calls
   `fuse(vision_fire=True, vision_smoke=False, gas_high=True, temp_spiking=False)`.
   Rule 1 matches → `(Level.CRITICAL, "visual hazard confirmed by gas sensor")`.
2. Edge device POSTs a JSON payload to `http://127.0.0.1:8000/incident` —
   level, reason, vision dict, sensors dict, base64 snapshot — and gets back
   `{"status": "accepted"}` within milliseconds. It immediately resumes
   watching the camera.
3. In the background, `agent/server.py`'s `_run` calls `run_incident(payload)`.
4. **`verify`** confirms `level` is CRITICAL (valid), assigns an `event_id`
   and `timestamp` if missing.
5. **`locate`** calls Overpass, finds "Station 12, 1.3 km away, phone
   555-0100," stores it under `state["station"]`.
6. **`compose`** calls Groq with the system prompt + `{level: CRITICAL,
   reason: ..., time_phrase: "at 9:29 PM"}`; Groq returns a 2-3 sentence
   urgent message containing "at 9:29 PM" verbatim; it passes validation and
   is stored as `state["alert_text"]`.
7. **`notify_owner`** logs the full technical detail to the server console,
   builds the human-readable Telegram message (alert text + station line +
   emergency numbers + "reply CANCEL within 60 seconds"), records
   `latest_update_id()` as the cancel-window baseline, and sends it via
   Telegram — with the snapshot photo attached as the caption image.
8. **`escalate`** builds a short SMS variant under 300 characters and sends
   it via Twilio to the developer's own phone — informational only, no
   cancel instruction.
9. **`wait`** polls Telegram every few seconds for up to 60 seconds, looking
   for a reply containing "CANCEL" from the correct chat, arriving after the
   baseline offset.
10. **Branch:** say nobody replies in time → `cancelled=False` →
    routes to **`simulate`**.
11. **`simulate`** writes a `SIMULATED: true` JSON line to
    `dispatch_log.jsonl` and prints the unmissable banner. Because level is
    CRITICAL, `_upload_critical` also uploads the packet + snapshot to S3.
    `append_feedback` writes one CSV row with `outcome=TIMEOUT, reward=+1`.
12. Graph reaches `END`. `run_incident` returns the final state dict.
    `agent/server.py`'s `_run` logs "incident handled: delivered=True
    cancelled=False."

That's the entire lifecycle, and now every single line of it should make
sense to you, not just what it does but *why* it's built that particular
way.

### ❓ Final Check Yourself
Someone proposes a "helpful" change: let the LLM in `compose.py` also decide
whether the cancel window should be extended if it judges the situation
"seems less urgent" from the reason text. Using everything you've learned
about this codebase's design philosophy, explain in your own words the
specific, concrete reasons this change should be rejected — and name the
exact code location(s) that would have to change to make it possible (which
should tell you how deliberately that door is currently closed).

---

## Where To Go Next

You now understand:
- Deterministic sensor fusion (`fuse()`)
- State machines / graph orchestration (LangGraph nodes and edges)
- Fire-and-forget background HTTP processing (FastAPI `BackgroundTasks`)
- Real-world API integration with retries, timeouts, and graceful fallback
  (Overpass, Telegram, Twilio, Groq)
- The haversine distance formula
- Safe LLM integration patterns (verify output, deterministic fallback,
  narrow scope of what the LLM is allowed to influence)
- RL-shaped data logging without building RL itself

If you want to go deeper, good next questions to explore with sensei mode:
- "Explain the ReAct pattern and how it differs from this project's fixed-edge graph."
- "What is prompt injection, and could it apply anywhere in this codebase?"
- "How would you actually build the RL policy this feedback log is designed for?"
- "Explain HTTP status codes and why `resp.status_code < 300` is the right check here."
