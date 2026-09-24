// Shared live-feed helpers — the one place "offline", board states and the
// hazard-index mapping are defined, so the home page's status strip, gas
// chart, bullet bars and camera overlay can never disagree.

// A healthy feed has a sample under ~2s old (1 Hz samples, 1 Hz WebSocket
// push); 12s rides out a few missed pushes before calling the edge loop down.
export const LIVE_STALE_MS = 12_000;

export const SENSORS = [
  { key: "mq2", label: "MQ-2", gas: "LPG · smoke", color: "#5b8fd6" },
  { key: "mq135", label: "MQ-135", gas: "VOC · air quality", color: "#9d8bd6" },
];

// Firmware state strings (edge/sensors.py VALID_STATES) -> display.
export const BOARD_STATE = {
  WARMUP: { label: "Warming up", tone: "pending" },
  BASELINE_CAPTURE: { label: "Capturing baseline", tone: "pending" },
  ok: { label: "Board OK", tone: "ok" },
  "ok(BASELINE_TROUBLE)": { label: "Baseline trouble", tone: "trouble" },
  GAS_HIGH: { label: "Gas high", tone: "alarm" },
};

export const isPreBaseline = (state) => state === "WARMUP" || state === "BASELINE_CAPTURE";

export function latestSample(liveSensors) {
  const readings = liveSensors?.ok ? liveSensors.readings ?? [] : [];
  return readings.length ? readings[readings.length - 1] : null;
}

export function sampleAgeMs(sample, now = Date.now()) {
  // livelog timestamps are unix SECONDS.
  return sample?.timestamp ? now - sample.timestamp * 1000 : Infinity;
}

export const isStale = (sample, now) => sampleAgeMs(sample, now) > LIVE_STALE_MS;

// { baseline, warn, danger } for one sensor from a sample's firmware `thr`
// (keys like warn_mq2), or null while the board has published none.
export function sensorThresholds(sample, sensor) {
  const thr = sample?.thr;
  if (!thr) return null;
  const baseline = thr[`baseline_${sensor}`];
  const warn = thr[`warn_${sensor}`];
  const danger = thr[`danger_${sensor}`];
  if (![baseline, warn, danger].every((v) => typeof v === "number")) return null;
  return { baseline, warn, danger };
}

// Hazard index: piecewise-linear, 0 at baseline, 1 at warn, 2 at danger,
// continuing at the warn->danger slope above it. Because it is built from
// each sensor's OWN thresholds at that second, both sensors share one axis
// and one warn/danger line is correct for both — whatever formula the
// firmware used, and however far its EMA baseline has drifted.
export function hazardIndex(reading, t) {
  if (typeof reading !== "number" || !t) return null;
  const { baseline, warn, danger } = t;
  if (reading <= baseline) return 0;
  if (reading <= warn) return (reading - baseline) / Math.max(warn - baseline, 1e-9);
  return 1 + (reading - warn) / Math.max(danger - warn, 1e-9);
}

// Index -> zone name, matching the firmware's own warn/danger boundaries.
export function hazardZone(index) {
  if (index == null) return null;
  if (index >= 2) return "danger";
  if (index >= 1) return "warn";
  return "normal";
}

// Contiguous runs of samples matching `pred`, as [startTs, endTs] pairs in
// unix seconds — used to shade warm-up / baseline-trouble spans on charts.
export function runsWhere(samples, pred) {
  const runs = [];
  let start = null;
  samples.forEach((s, i) => {
    if (pred(s)) {
      if (start === null) start = s.timestamp;
      const next = samples[i + 1];
      if (!next || !pred(next)) {
        runs.push([start, next ? next.timestamp : s.timestamp]);
        start = null;
      }
    }
  });
  return runs;
}

export function formatAge(ms) {
  if (!Number.isFinite(ms)) return "never";
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ${m % 60}m ago`;
}
