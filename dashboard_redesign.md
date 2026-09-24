# Dashboard redesign — live-first replan

Date: 2026-09-24. Scope: `dashboard/frontend`, `dashboard/backend/main.py`, and a small change to `edge/livelog.py` / `edge/main.py`. No firmware changes are needed, except the optional M5.

---

## 1. Why the gas chart shows stale thresholds

The backend already puts the firmware thresholds on top of the config.yaml values (`_live_sensors_payload`, main.py:198). So the lines aren't hardcoded on purpose. The data around them is what goes stale:

| # | Problem | Where | Effect |
|---|---|---|---|
| A | **Fallback is silent.** The payload doesn't say whether the thresholds came from the firmware or from config.yaml. | main.py:214-233 | During WARMUP / BASELINE_CAPTURE, or with legacy firmware, the chart draws config's 10-bit numbers (MQ-2 warn 115, danger 174). The live 12-bit board has warn around 420. These lines use the same labels as real ones and look just as trustworthy. |
| B | **The sidecar is never cleared.** `live_sensors_thresholds.json` is written only when the values change. Nothing deletes it on edge restart or board reboot. | edge/main.py:143, 236 | After a board reboot, the board publishes nothing while it warms up. The dashboard keeps showing the **previous boot's** thresholds as if they were live. |
| C | **Thresholds are drawn as flat lines across the whole 10-min window.** The firmware's EMA baseline tracker moves them, and every boot starts from a new baseline. | LiveSensorChart.jsx `thresholdLine()` | Old samples get compared against today's threshold. You can't see drift or a re-baseline. |
| D | **Two sensors share one y-axis.** Their scales differ a lot: MQ-2 warn ~420 / danger ~760, MQ-135 warn ~210 / danger ~370. | LiveSensorChart.jsx | Four dotted lines interleave. The MQ-135 lines differ only in alpha, so you can't tell which line belongs to which sensor. |
| E | **Board state isn't shown** (WARMUP / BASELINE_CAPTURE / BASELINE_TROUBLE / GAS_HIGH). `livelog.record()` never receives it. | edge/livelog.py:64 | The chart can't explain why there are no thresholds, or say that the baseline is suspect. |
| F | **The hard ceilings aren't shown** (MQ-2 1400 / MQ-135 750). This is the one alarm path the EMA can't learn away. | firmware only | The most safety-relevant line is invisible. |

### Fix for the data (M1)
- **Record thresholds and state on every livelog sample**, not in a sidecar:
  `{"timestamp", "mq2", "mq135", "p_fire", "level", "state", "thr": {mq2_baseline, mq2_warn, mq2_danger, mq135_…}}`.
  `thr` is `null` when the board has none. 600 samples × 6 floats is about 50 KB, which is fine.
  This fixes B for free, because staleness now follows the sample timestamp, which is already checked. It also enables C, because thresholds become a time series. Retire `_publish_thresholds` and the sidecar.
- Payload gains `threshold_source: "firmware" | "none"` and `board_state`.
  **config.yaml thresholds are never drawn as lines again.** At most they set the y-axis range before the first sample arrives. This fixes A.

---

## 2. Redesigning the gas chart (M2)

**Two stacked lanes with a shared time axis** (small multiples), one per sensor, each with its own y-scale. This fixes D.

```
MQ-2   ┃░░░░░░░░░░░░░░░░░░░░░░░░░░ danger zone (red 8%) ░░░░░░░░░░
       ┃▒▒▒▒▒▒▒▒▒▒▒▒▒▒ warn zone (amber 8%) ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
       ┃    ╭╮      ___/‾‾‾ step-traced warn line (hv) drifts w/ EMA
       ┃╱╲_╱  ╲____╱            ── reading (steel blue)
       ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MQ-135 ┃ (same, violet)
       ┃▓▓▓▓ WARMUP (hatched: "thresholds pending") ▓▓▓▓│ live →
       └─ 14:02 ──── 14:04 ──── 14:06 ──── 14:08 ──── 14:10
```

- Draw thresholds as **step traces** (`line.shape: "hv"`) from the per-sample `thr`, not as layout `shapes`. Drift and re-baselines show up where they happen, and gaps appear where `thr` is null. This fixes C.
- Show **zones, not dotted lines**: fill warn→danger in amber and danger→top in red, both at low alpha. You read the zone at a glance. The line alone takes a legend lookup.
- **Shade the background by board state**: hatched gray for WARMUP/CAPTURE, a thin violet edge for BASELINE_TROUBLE. This fixes E.
- **Header chip**: `thresholds: firmware · live`, `thresholds: pending — board warming up`, or `no thresholds (legacy firmware)`. This states the answer to A in the UI.
- Add a **"Hazard index" toggle** with one shared axis. Each reading maps piecewise-linearly: baseline→0, warn→1, danger→2. Both sensors land on the same scale, so a single warn line and a single danger line are correct for both. This compact form suits the home page.
- Add `uirevision` so the 1 Hz updates don't reset zoom or hover. Remove the panel-in-panel: LiveView wraps LiveSensorChart, which already renders its own panel and title.

**"Right now" readout** (for the home page): bullet bars, not a chart.
```
MQ-2    [──baseline──|====warn====|####danger####|  ceiling ]   ▲ 312
MQ-135  [──baseline──|====warn====|####danger####|  ceiling ]  ▲ 88
```
One marker on a track shows headroom to each threshold more clearly than a line chart does.

---

## 3. Information architecture (M3)

**Today:** 6 tabs. The home page is incident history (KPIs, fusion timeline) with the gas chart at the bottom. The camera is buried in "Live View", which is also the only tab on the WebSocket; Overview polls REST every 3 s for the same data.

**Proposed:** 4 tabs. The home page answers one question in two seconds: *is something burning right now, and what am I looking at?*

```
┌─ STATUS STRIP (sticky) ──────────────────────────────────────────────────┐
│ ● SAFE   board: OK   camera: live   edge: 1s ago   thresholds: firmware   │
└──────────────────────────────────────────────────────────────────────────┘
┌─ LIVE CAMERA (col-7, 16:9) ───────────────┐ ┌─ RIGHT NOW (col-5) ─────────┐
│  [MJPEG via relay]                        │ │ MQ-2   bullet bar     312   │
│  overlay: ● LIVE 14:10:03   level chip    │ │ MQ-135 bullet bar      88   │
│           p_fire ▮▮▮▯▯ 0.41               │ │ p_fire sparkline (60s)      │
│  [fullscreen]                             │ │ Cloud 2nd opinion: agree ✓  │
└───────────────────────────────────────────┘ └─────────────────────────────┘
┌─ GAS LANES — last 10 min (col-8) ─────────┐ ┌─ col-4 ─────────────────────┐
│  MQ-2 lane / MQ-135 lane (§2)             │ │ Most recent event           │
│                                           │ │ Nearest fire station        │
└───────────────────────────────────────────┘ └─────────────────────────────┘
┌─ TODAY: KPIs strip + fusion timeline (full width, demoted) ──────────────┐
```

**Tabs:** `Command` (home, above) · `Incidents` (Live Incidents + fusion timeline + KPIs) · `Archive` · `Evaluation`.
"Live View" is removed because the home page is now live. "Nearest Fire Station" moves into the side card and incident detail.

**Behavior changes:**
- **Alarm state takes over the page.** At WARNING/CRITICAL the status strip fills with the level color and the camera frame gets the level glow. `prefers-reduced-motion` means no pulse. The level is always written as text, never shown by color alone.
- **Camera as a real component** with state: `live / stale / unconfigured / error`. Build it on `/api/camera/status`, not on the current `onError` + `nextElementSibling` DOM hack. An MJPEG `<img>` **freezes silently** when upstream dies, so the stale overlay has to come from status, not from the image. **Pause when hidden**: on `visibilitychange`, swap to `/api/camera/snapshot`.
- **One data path**: the home page always holds `/ws/live`. Remove the 3 s REST poll of the same payload. `LIVE_STALE_MS` and `isStale` currently live in both Overview and LiveView; move them into one module.
- **Mobile order**: status strip → camera → right-now → lanes → rest.

**Keep** the existing visual language: warm ember liquid glass, Oswald display type, and level colors reserved for status. It's sound. Reduce glass blur on dense data panels (lanes, bullet bars) so they keep contrast.

---

## 4. Milestones

**M1 — Data you can trust** (edge + backend, ~3h)
- [ ] `livelog.record()` takes `state` and `thr`. `main.py:425` passes `reader.thresholds() or None` and the board state (1h)
- [ ] Backend: current thresholds come from the latest sample. Add `threshold_source` and `board_state`. Delete the sidecar read/write (1h)
- [ ] Check: reboot the board mid-session. The chart shows "pending" during warmup and never shows the previous boot's lines (30m, you run it)

**M2 — Gas chart rework** (~6h)
- [ ] Split into `GasLanes.jsx`: two subplots, shared x, step threshold traces, zone fills, `uirevision` (3h)
- [ ] State shading and the threshold-source chip (1h)
- [ ] `ThresholdBullet.jsx` and the hazard-index mapping as a pure function (`hazardIndex(reading, thr)`) (2h)

**M3 — Command home page** (~6h)
- [ ] `CameraFeed.jsx` with a status-driven state machine, visibility pause, fullscreen (2h)
- [ ] `StatusStrip.jsx` with the alarm takeover (1h)
- [ ] New `Command.jsx` layout. Fold Live View in, merge the incident views, 6 → 4 tabs. Home page on the WebSocket only (3h)

**M4 — Polish** (~2h): reduced motion, mobile order, focus states, one shared stale-time constant, lint/build.

**M5 — optional, firmware:** publish `ceiling_mq2` / `ceiling_mq135` in the POST JSON so the lanes can draw the hard ceiling (F) without duplicating a firmware constant into config.

**Out of scope:** new charts for incident history, auth, multi-device support.

**Done when:** after a board reboot the dashboard never shows thresholds from another boot or from config; the camera and the live level are visible on page load; and the home page uses a single socket.
