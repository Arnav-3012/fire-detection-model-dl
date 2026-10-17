# The Physical Sensor Side, Fully Explained: Chemistry, Electronics, Calibration

Everything else in this project's documentation is about software — models,
agents, graphs, APIs. This document is the opposite: it's about the actual
physical hardware sitting on a breadboard, the chemistry inside a $2 gas
sensor, and the real calibration numbers this project measured with its own
hands. Zero machine learning appears anywhere in this document — this is
electronics and chemistry, and it deserves to be understood on its own
terms, not as an ML afterthought.

Following the sensei formula: intuition → math/logic → code/data → connection
→ check yourself, section by section.

---

## 1. What's Actually Inside an MQ Gas Sensor

### 🧠 Intuition

Imagine a tiny ceramic bead, about the size of a rice grain, sitting inside
a metal mesh dome (that dome, by the way, is a genuine safety feature — it's
a flame arrestor, the same principle as the mesh on an old miner's safety
lamp: it lets gas through but stops an actual flame from reaching the hot
element inside and igniting the surrounding air). Inside that bead is a
material called **tin dioxide (SnO₂)**, wrapped around a tiny heating coil,
like a miniature toaster element.

Think of the tin dioxide surface as a parking lot. When the air is clean,
oxygen molecules from the atmosphere "park" all over the lot's surface and,
in doing so, each one grabs and holds onto a free electron from the tin
dioxide material — like each parked car taking a shopping cart from the
lot and holding onto it. With lots of electrons "checked out" this way,
electricity has a harder time flowing through the material — this is
exactly what *resistance* means physically: how much the material resists
the flow of electric charge.

Now a combustible gas molecule — say, propane or methane from a stove leak,
or smoke particulates — drifts by. That gas molecule reacts chemically with
the oxygen that's parked on the surface, and in that reaction, the
electrons that oxygen was holding onto get **released back** into the tin
dioxide. All those "shopping carts" get returned at once. More free
electrons flowing around means electricity moves through the material more
easily — resistance drops.

**More gas in the air → more of this electron-releasing reaction happens →
lower resistance → and since the sensor module is wired to convert
resistance into a voltage, that means a higher voltage → which the Arduino
reads as a bigger number.**

### 📐 The Physical Chain, Step by Step

1. **The heater** raises the SnO₂ bead to roughly 300°C. This is not
   optional — at room temperature, this whole electron-transfer chemistry
   essentially doesn't happen at any useful rate. The heater is *why* the
   sensor draws continuous power and *why* it feels genuinely warm to the
   touch when it's been running a while — that warmth is a sign it's
   working correctly, not a malfunction.
2. **Oxygen adsorption** — at that operating temperature, oxygen from the
   surrounding air physically adheres to the bead's surface and pulls
   electrons out of the tin dioxide's conduction band. Baseline (clean-air)
   resistance is relatively **high** because of this.
3. **Gas reaction** — a flammable/reducing gas (LPG, methane, propane,
   smoke particulates for the MQ-2; a broader set including CO₂, ammonia,
   benzene-family vapors, and alcohol for the MQ-135) reacts with that
   surface-bound oxygen and releases the trapped electrons back into the
   material. Resistance **drops**.
4. **Voltage conversion** — the sensor module itself contains a simple
   voltage-divider circuit that turns "how much the SnO₂ bead's resistance
   just changed" into "a voltage between 0 and 5 volts" on the analog
   output pin. You never read resistance directly; you read this derived
   voltage.

**In one sentence:** more target gas in the air chemically frees up more
electrons in the sensing material, which lowers its electrical resistance,
which the module's circuitry converts into a higher output voltage.

### 🔗 Connection

This is a real, physical instance of a *transducer* — any device that
converts one form of energy or phenomenon (here: gas concentration, a
chemical property) into another (here: electrical voltage, something a
microcontroller can actually measure). Cameras, microphones, and even your
phone's touchscreen are all transducers in the same conceptual sense — they
just convert light, sound, and pressure/capacitance respectively, instead
of gas chemistry. Once you recognize the pattern "physical phenomenon →
electrical signal → digital number," you'll see it everywhere in
electronics and IoT.

### ❓ Check Yourself
If you blew ordinary room-temperature air (no combustible gas, just your
breath) across a *cold*, unpowered MQ sensor, would you expect the reading
to change much? Why does the heater specifically need to reach ~300°C for
the sensing chemistry to work at all?

---

## 2. Analog vs. Digital: Why This Project Uses A0, Never D0

### 🧠 Intuition

Every MQ sensor breakout board actually exposes TWO different output pins
for the same underlying physical sensor, and they answer two completely
different questions:

- **D0 (digital)** answers a yes/no question: "has the gas concentration
  crossed some fixed line?" That line is set by a tiny screw-adjustable
  potentiometer physically on the board — you turn a screw with a
  screwdriver until it "trips" at whatever level you decide, and after
  that, D0 just outputs either a clean HIGH or a clean LOW. It's like a
  home thermostat that either says "too cold" or "not too cold" with no
  in-between.
- **A0 (analog)** answers a much more useful question: "roughly how much
  gas, on a continuous scale?" It hands you back a real, granular number
  representing the actual voltage level.

### 📐 Why This Matters for Fusion Specifically

This project's entire safety architecture (see `fusion_explained.md`)
depends on being able to distinguish "slightly elevated, worth a WARNING"
from "way elevated, genuinely dangerous" — that's a **calibrated,
graduated** threshold system, not a single trip point. A digital D0 pin
physically cannot express that distinction: it only ever has two possible
states, decided once by a mechanical potentiometer screw that isn't even
under the software's control. The analog pin gives 1024 distinct possible
readings instead of 2, which is exactly the resolution needed to compute
two separate thresholds (`warn` and `danger`) rather than just one crude
trip point.

**This is why `plan.md`'s own hardware appendix says outright: "Always use
A0... crude, hand-tuned, useless for fusion" about D0.**

### 📐 The Math: What Do These Numbers Actually Mean? (The 10-bit ADC)

The Arduino Uno's analog input pins are connected to a component called an
**ADC — Analog-to-Digital Converter**. Voltage is a continuous,
infinitely-precise physical quantity in reality, but a microcontroller can
only store and manipulate discrete digital numbers — so the ADC's job is to
"snap" a continuous voltage onto the nearest value from a fixed set of
possible digital numbers.

The Uno's ADC is **10-bit**. A "bit" is a single binary digit (0 or 1); "N
bits" gives you 2ᴺ distinct possible values. With 10 bits:

```
2^10 = 1024 possible values, numbered 0 through 1023
```

Those 1024 values are spread evenly across the ADC's voltage range, which
on an Arduino Uno is 0V to 5V (the board's own logic voltage) unless you
reconfigure the reference voltage:

```
reading = round( (measured_voltage / 5.0V) * 1023 )
```

**What's this saying in one sentence?** The analog voltage gets divided
into 1024 equal-sized "buckets" spanning 0V to 5V, and `analogRead()`
returns which bucket number the current voltage fell into.

**At the extremes:**
- 0V in → reading of `0`.
- 5V in → reading of `1023` (the maximum representable value — this is why
  a sensor reading permanently pinned at `1023` in the troubleshooting table
  means "the voltage is maxed out," most often because the sensor is still
  burning in, or is miswired to the wrong pin).
- Roughly 2.5V (half the range) → reading of about `512` — this is `plan.md`'s
  own worked example.

**Resolution — how much voltage does one "step" represent?**
```
5.0V / 1024 ≈ 0.0049V per step  (about 4.9 millivolts per ADC unit)
```
This tells you the finest voltage difference the Arduino can actually
distinguish — anything smaller than ~4.9mV just isn't visible to the code
at all; it rounds to the same reading.

### 💻 The Code

On the Arduino side (`arduino/sensor_node/sensor_node.ino`), reading the
sensor is a single built-in function call:

```cpp
int mq2 = analogRead(A0);
int mq135 = analogRead(A1);
```

`analogRead()` handles the entire ADC conversion internally and just hands
back an `int` from 0 to 1023 — you never touch the raw voltage-sampling
hardware yourself; Arduino's core library abstracts that away completely.

These two integers get sent over the USB serial connection once per second,
formatted as a simple comma-separated line:

```cpp
Serial.print(mq2);
Serial.print(",");
Serial.println(mq135);
```

producing output like `423,187\n` — a tiny, easy-to-parse text protocol
that the Python side (`edge/sensors.py`, `eval/calibrate_mq.py`) reads back
with a simple `raw.split(",")`.

### 🔗 Connection

This 0–1023 scale, and the general idea of an ADC "quantizing" a continuous
signal into discrete steps, is completely universal across electronics —
you'll meet the exact same concept (just with different bit-depths) in
audio sampling (a 16-bit audio sample also snaps continuous sound pressure
onto one of 2¹⁶ possible values), digital cameras (each pixel's brightness
is quantized the same way), and virtually every sensor you'll ever wire to
a microcontroller.

### ❓ Check Yourself
If the Arduino Uno used an 8-bit ADC instead of a 10-bit one, how many
distinct reading values would be possible, and would that make it easier
or harder to set two well-separated thresholds like `warn` and `danger`
close together?

---

## 3. Burn-In: Why You Cannot Calibrate a Freshly-Powered Sensor

### 🧠 Intuition

Picture buying a brand-new cast iron skillet. The first time you heat it
up, it smokes and smells strange for a while — that's manufacturing residue
and packaging oils burning off. Nobody judges a cast iron pan's "true"
cooking behavior on that very first, smoky use; you season it and let it
settle in first.

MQ gas sensors have a near-identical phenomenon, just with electronics
instead of cookware. They sit in plastic packaging for months between
manufacture and use, and during that time, ambient moisture and volatile
packaging residues slowly settle onto the sensing bead's surface. The
instant you power one on for the very first time, the heater starts
cooking all of that contamination off — and while that's happening, the
sensor's baseline reading is not stable; it drifts, typically starting high
and gradually falling over many hours as the surface cleans itself.

**If you calibrate against numbers taken during that drift, your
thresholds are simply wrong the next day**, once the sensor has actually
settled into its true resting behavior. This is exactly the kind of subtle,
easy-to-miss mistake that produces flaky, hard-to-debug behavior later — a
sensor that seemed to work fine on day one but reports nonsense readings by
day three.

### 📐 The Procedure, and the Real Numbers

This project's own hardware appendix and build log document the exact
timeline used:

- **Connect only VCC and GND — no code needed, no Arduino sketch required.**
  Power alone is what drives the burn-in process; the sensor doesn't need
  to be actively read during this phase.
- **Leave it powered continuously: 24 hours minimum, 48 hours preferred.**
- **The sensor will get noticeably warm to the touch.** This is the heater
  doing its job correctly, not a malfunction (a genuinely important thing
  to know before you touch one and worry you've broken it).
- **After the minimum window, watch readings for 15 minutes.** If they stay
  stable within roughly ±20 ADC units, the sensor is considered settled and
  ready for calibration. If it's still visibly drifting, the answer is
  simply: leave it powered for another 24 hours and check again.

The project's actual build log records this exact timeline being followed
in practice:
```
MQ-2 original burn-in started:      2026-08-23, 12:40 AM
MQ-2 burn-in valid from (24h min):  2026-08-24, 12:40 AM
MQ-2 burn-in valid from (48h pref): 2026-08-25, 12:40 AM
Stability check: PASSED, Phase 6, 2026-08-24
```
MQ-135 was burned in on the exact same power-on window and passed the same
15-minute stability check.

**A real complication that actually happened:** partway through the
project, the hardware had to be physically rewired (to add a buzzer
component), which meant fully disconnecting and reconnecting power to the
MQ sensors. The build log is explicit that this invalidates the prior
burn-in's *stability confirmation* — a full power interruption isn't the
same as a brief brownout, and the team's own sourced guidance (from
component manufacturer documentation, Winsen/PCBSync) called for a fresh
**1-hour re-warm window** before trusting readings again post-interruption
(more conservative than a "2-5 minute" figure also found in sourcing, but
chosen deliberately for margin). This is worth noticing as good practice:
**when in doubt between two sourced figures, this team picked the more
conservative one rather than the more convenient one**, because getting
calibration wrong here means false alarms or missed fires later.

### 🔗 Connection

"Let the hardware settle before trusting its first readings" is a
near-universal principle across sensor engineering — camera sensors need a
brief auto-exposure settling period, some digital scales ask you to wait
after power-on before weighing, and precision lab equipment often has
documented warm-up times before results are considered valid. The specific
mechanism (contaminant burn-off) is unique to MQ-style gas sensors, but the
*shape* of the lesson — "new hardware needs time before its numbers mean
anything" — generalizes broadly.

### ❓ Check Yourself
The 15-minute post-24h stability check requires readings to stay within
±20 ADC units. Given the 10-bit ADC's ~4.9mV-per-unit resolution from
Section 2, roughly how many millivolts of drift does a ±20-unit window
actually correspond to? Does that seem like a strict or lenient bar,
relative to the sensor's full 0–5V range?

---

## 4. The Calibration Procedure and Formula

### 🧠 Intuition

Every individual sensor unit, even of the exact same model number, has a
slightly different "resting" reading in clean air — manufacturing tolerance,
slightly different heater output, environmental humidity on the day you
tested it, all of that shifts the baseline a bit. So you can't just hardcode
one universal magic number as "the" warn threshold across all sensors and
all rooms. Instead, this project calibrates **relative to each sensor's own
measured behavior**: first find out what "normal" looks like for THIS
specific sensor in THIS specific room, then find out what "clearly
triggered" looks like for the same sensor, and set thresholds as a
percentage of the way between those two.

**Analogy:** this is exactly like a doctor interpreting your heart rate
relative to *your own* resting baseline rather than a single number applied
to everyone — 100 bpm might be totally normal exertion for one person and
alarmingly high for another sitting still, so a good diagnostic asks "how
far above THIS person's normal is this reading," not "is it above X."

### 📐 The Formula

Two numbers get measured for each sensor:
- **`baseline`** — the average reading in a normal, unexposed room, over a
  sustained multi-minute window (this project used 15 minutes).
- **`peak`** — the maximum reading observed during a deliberate, controlled
  exposure test meant to simulate the kind of event you actually want to
  detect.

Then two thresholds are computed by **linear interpolation** between those
two points:

```
warn   = baseline + 0.30 * (peak - baseline)
danger = baseline + 0.60 * (peak - baseline)
```

**Define every symbol:**
- `baseline` — the sensor's own measured "quiet room" average, in raw ADC
  units (0–1023).
- `peak` — the sensor's own measured maximum during a real trigger event, in
  the same units.
- `0.30` / `0.60` — chosen fractions of the total distance between baseline
  and peak. `warn` sits 30% of the way from baseline toward peak; `danger`
  sits 60% of the way.

**What is this saying in one sentence?** Rather than picking absolute
threshold numbers out of thin air, each threshold is defined as "a fixed
fraction of how far this specific sensor's readings traveled during a known
real trigger event, measured from this specific sensor's own quiet-room
normal."

**What happens at the extremes?** If `peak == baseline` (the trigger test
somehow produced no change at all — a broken sensor or a failed test), then
`warn = danger = baseline` — both thresholds collapse to the resting value,
meaning the tiniest noise would trip them. This is actually a useful
sanity-check property: it would immediately reveal a bad calibration run
rather than silently producing meaningless thresholds. If `0.30` were
increased toward `1.0`, `warn` would slide closer and closer to `peak`
itself, making the system progressively less sensitive (requiring
near-peak-level gas before even a WARNING triggers) — so these fractions
are directly a sensitivity dial.

### 💻 The Real, Measured Numbers From This Project

These aren't illustrative — they're this project's actual calibrated values,
sitting in `config.yaml` today:

**MQ-2** (tuned toward LPG/methane/propane/smoke):
```
mq2_baseline = 57.1     (measured: quiet room, before an unlit gas-stove release test)
mq2_peak     = 252      (measured: unlit gas-stove release, ~20cm distance, ~5 seconds)

mq2_warn   = 57.1 + 0.30 * (252 - 57.1) = 57.1 + 0.30 * 194.9 = 57.1 + 58.47 = 115.57
mq2_danger = 57.1 + 0.60 * (252 - 57.1) = 57.1 + 0.60 * 194.9 = 57.1 + 116.94 = 174.04
```

**MQ-135** (tuned toward CO₂/ammonia/benzene-family/general air quality):
```
mq135_baseline = 51.1   (measured: quiet room, before an alcohol/hand-sanitizer vapor test)
mq135_peak     = 210    (measured: alcohol/hand-sanitizer vapor trigger)

mq135_warn   = 51.1 + 0.30 * (210 - 51.1) = 51.1 + 0.30 * 158.9 = 51.1 + 47.67 = 98.77
mq135_danger = 51.1 + 0.60 * (210 - 51.1) = 51.1 + 0.60 * 158.9 = 51.1 + 95.34 = 146.44
```

These are the exact `mq2_warn`, `mq2_danger`, `mq135_warn`, `mq135_danger`
values `edge/fusion.py`'s `compute_gas_high()` reads from `config.yaml` and
compares live sensor readings against — you can now trace a single
calibrated number all the way from "a real physical burn test on a real
kitchen stove" to "a boolean flowing into the fusion rule table."

**Why did each sensor get a different trigger test?** This is a real
methodological decision documented in the calibration script's own
docstring, and it's a good example of matching your test stimulus to what a
sensor is actually chemically sensitive to:
- **MQ-2** was tested with an **unlit gas-stove release** (LPG/methane) held
  near the sensor for ~5 seconds — a direct, relevant stimulus for a sensor
  literally tuned for combustible/flammable gases.
- **MQ-135** was tested with **alcohol/hand-sanitizer vapor**, not the same
  gas-stove test. The reasoning given: MQ-135 isn't primarily a combustible-
  gas sensor, so a lighter/stove test wouldn't strongly exercise its actual
  sensitivity range. A **breath test** (exhaling near the sensor, a CO₂
  source) was also considered but explicitly rejected as "too weak a
  stimulus" — not producing a strong enough, clearly distinguishable peak to
  calibrate confidently against. Alcohol vapor was chosen instead as a
  stronger, safe, easily repeatable trigger that MQ-135 is genuinely
  sensitive to.

This matters conceptually: **calibration is only meaningful if your test
stimulus actually exercises the same chemistry your sensor will encounter
in a real event.** Testing MQ-135 with a stimulus it barely responds to
would produce a `peak` value barely above `baseline`, which (per the
extreme-case analysis above) would collapse `warn`/`danger` toward
uselessly-sensitive thresholds.

### 💻 The Calibration Tool Itself (`eval/calibrate_mq.py`)

The actual measurement was performed with a small command-line tool with
two modes:

```python
def suggest_thresholds(baseline: float, peak: float) -> tuple[float, float]:
    warn = baseline + 0.30 * (peak - baseline)
    danger = baseline + 0.60 * (peak - baseline)
    return warn, danger
```
— a direct, one-to-one translation of the formula above.

**`--baseline` mode** logs both sensors continuously for a configurable
duration (15 minutes by default, matching the `plan.md`-specified
procedure) in a normal, unexposed room, then prints summary statistics:

```python
mean = statistics.mean(vals)
std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
print(f"{name}: mean={mean:.1f}  std={std:.1f}  min={min(vals)}  max={max(vals)}  n={len(vals)}")
```
`statistics.mean` is the arithmetic average — this becomes `baseline`.
`pstdev` is the **population standard deviation** — a measure of how spread
out the readings were around that average. A small `std` here is itself a
health check: if quiet-room readings are jumping around wildly, that's a
sign the sensor hasn't finished burning in yet or something else is wrong,
even before you get to the actual trigger test.

**`--peak` mode** logs continuously while you perform a physical trigger
test (holding a lighter's released-but-unlit gas near MQ-2, or exhaling/
spraying sanitizer near MQ-135) and tracks a running maximum:

```python
max_mq2 = max(max_mq2, r.mq2)
max_mq135 = max(max_mq135, r.mq135)
```
— a simple **running maximum**, updated once per new reading; you stop the
tool with Ctrl+C once the trigger test is done, and it reports the highest
value seen. The tool deliberately tracks BOTH sensors' maxima during any
single trigger test run and warns you which one is the "real" peak for that
test versus incidental cross-talk from the other sensor — because holding a
lighter near MQ-2 will often also nudge MQ-135's reading slightly, and that
side-effect reading must not be mistaken for MQ-135's actual calibration
peak.

### 🔗 Connection

This baseline-relative, fraction-of-the-way-to-a-known-event style of
threshold-setting is a general statistical technique that shows up under
many names across fields — in signal processing it resembles setting a
detection threshold as a fraction of a signal's dynamic range; in anomaly
detection it resembles defining "anomalous" relative to a rolling baseline
rather than a fixed global cutoff. The core idea — **measure your system's
own normal first, then define "abnormal" as a proportion of the gap between
normal and a known real event** — transfers directly to calibrating almost
any sensor-based detection system, not just gas sensors.

### ❓ Check Yourself
Given `mq2_baseline = 57.1` and `mq2_peak = 252`, verify by hand that
`mq2_danger = 174.04` using the formula. Then suppose a totally different
MQ-2 unit, sitting in a slightly more humid room, measured `baseline = 70`
during its own burn-in with the exact same peak-test stimulus producing
`peak = 260`. Would you expect its computed `warn`/`danger` thresholds to
be higher, lower, or about the same as this project's unit's — and why does
per-sensor calibration handle that difference automatically, where a single
hardcoded global threshold would not?

---

## 5. Putting the Whole Physical Chain Together

Trace one gas molecule's entire journey through this system, using
everything from this document:

1. A real gas leak begins near the stove. LPG molecules diffuse through the
   air and reach the MQ-2 sensor's exposed mesh dome.
2. Inside, at ~300°C, those LPG molecules react with oxygen sitting on the
   heated SnO₂ bead's surface, releasing trapped electrons back into the
   material (Section 1).
3. The bead's electrical resistance drops as a direct result.
4. The sensor module's onboard circuitry converts that resistance drop into
   a rising voltage on the A0 output pin.
5. The Arduino's 10-bit ADC samples that voltage once per second via
   `analogRead(A0)`, producing an integer somewhere in 0–1023 (Section 2).
6. That raw integer is streamed over USB serial as plain text
   (`"423,187\n"`) to the host computer.
7. `edge/sensors.py` parses that line and hands the raw `mq2` value to
   `compute_gas_high(mq2, mq135, thresholds)` in `edge/fusion.py`.
8. That function compares the live reading against `mq2_warn = 115.57` —
   the exact number measured and computed in Section 4, sitting in
   `config.yaml` — and returns `True` if the leak has pushed the reading
   above it.
9. That single boolean, `gas_high`, becomes one of the four inputs to
   `fuse()`, which (per `fusion_explained.md`) can now combine it with
   whatever the camera independently saw to decide the final alert level.

A physical chemical reaction on a $2 ceramic bead, six software layers
later, becomes one boolean in a life-safety decision table. That entire
chain — chemistry → electronics → calibration → software — is what this
document has walked you through end to end.

---

## Final Check Yourself

Someone suggests: "Why calibrate at all? Just hardcode `mq2_warn = 115`
directly in `fusion.py` and skip the whole `config.yaml` + calibration
script setup." Using everything from this document — burn-in variability
between individual sensor units, the baseline-relative calibration formula,
and the real measured numbers being sensor- and room-specific — explain
concretely what would break, and for which of this project's actual
hardware units, if that suggestion were followed.
