import { useRef, useState } from "react";
import Plot from "react-plotly.js";
import { darkLayout, plotlyConfig } from "../plotlyTheme";
import { LEVEL_COLOR } from "../levels";
import {
  SENSORS,
  BOARD_STATE,
  isPreBaseline,
  sensorThresholds,
  hazardIndex,
  runsWhere,
} from "../live";
import StateCard from "./StateCard";
import ChartTooltip from "./ChartTooltip";
import { GaugeIcon } from "./icons";

// Replaces LiveSensorChart (2026-09-24). Two views of the same 1 Hz feed:
//
//   hazard — each reading mapped onto its OWN sensor's thresholds at that
//            second (live.js hazardIndex), so both sensors share one axis
//            and a single warn / danger line is honest for both.
//   raw    — two stacked lanes (own y-scale each) with the thresholds drawn
//            as step traces that follow the firmware's EMA drift and
//            re-baselines, instead of flat lines stamped across the window.
//
// Thresholds come only from the per-sample `thr` the board published —
// never config.yaml — so a warming-up board shows a shaded "pending" span
// rather than stale lines that look real.

const WARN = LEVEL_COLOR.WARNING;
const DANGER = LEVEL_COLOR.CRITICAL;
const PENDING_FILL = "rgba(168,154,144,0.20)";
const TROUBLE_FILL = "rgba(157,139,214,0.12)";

const WINDOWS = [
  { sec: 60, label: "1m" },
  { sec: 300, label: "5m" },
  { sec: 600, label: "10m" },
];

const SOURCE_CHIP = {
  firmware: { text: "thresholds live from board", tone: "ok" },
  pending: { text: "thresholds pending — board warming up", tone: "pending" },
  none: { text: "board is not publishing thresholds", tone: "trouble" },
};

function Segmented({ options, value, onChange, label }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          className={`segmented-btn${o.value === value ? " segmented-btn--active" : ""}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// Shaded spans for board states the reader should know about: no baseline
// yet (no thresholds exist) and a baseline the firmware itself distrusts.
function stateShapes(samples) {
  const span = ([a, b], fill) => ({
    type: "rect",
    xref: "x",
    yref: "paper",
    x0: new Date(a * 1000),
    x1: new Date(b * 1000),
    y0: 0,
    y1: 1,
    fillcolor: fill,
    line: { width: 0 },
    layer: "below",
  });
  return [
    ...runsWhere(samples, (s) => isPreBaseline(s.state)).map((r) => span(r, PENDING_FILL)),
    ...runsWhere(samples, (s) => s.state === "ok(BASELINE_TROUBLE)").map((r) => span(r, TROUBLE_FILL)),
  ];
}

const headMarker = (x, y, color, yaxis) => [
  // Soft halo, then the solid dot: marks "now" on each live trace.
  { x: [x], y: [y], yaxis, type: "scatter", mode: "markers", hoverinfo: "skip", showlegend: false,
    marker: { color, size: 18, opacity: 0.22 } },
  { x: [x], y: [y], yaxis, type: "scatter", mode: "markers", hoverinfo: "skip", showlegend: false,
    marker: { color, size: 7, line: { color: "#0d0b0a", width: 1.5 } } },
];

const rightLabel = (y, text, color, yref = "y") => ({
  xref: "paper", x: 1, xanchor: "left", xshift: 6, y, yref, yanchor: "middle",
  text, showarrow: false, font: { color, size: 11 }, align: "left",
});

// Caption for each no-baseline span, so the grey block explains itself.
function pendingLabels(samples) {
  return runsWhere(samples, (s) => isPreBaseline(s.state)).map(([a, b]) => ({
    xref: "x", x: new Date(((a + b) / 2) * 1000), yref: "paper", y: 1, yanchor: "top",
    text: "no baseline yet", showarrow: false, font: { color: "#a89a90", size: 10 },
  }));
}

function hazardFigure(x, samples, series) {
  const idxMax = Math.max(2.6, ...series.flatMap((s) => s.index.filter((v) => v != null)).map((v) => v * 1.12));
  const band = (y0, y1, color, alpha) => ({
    type: "rect", xref: "paper", x0: 0, x1: 1, yref: "y", y0, y1,
    fillcolor: `${color}${alpha}`, line: { width: 0 }, layer: "below",
  });
  const rule = (y, color) => ({
    type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: y, y1: y,
    line: { color, width: 1.25, dash: "dot" },
  });
  const traces = series.flatMap((s) => {
    const lastIdx = s.index.findLastIndex((v) => v != null);
    return [
      {
        x, y: s.index, type: "scatter", mode: "lines", connectgaps: false, showlegend: false,
        line: { color: s.color, width: 2.25, shape: "spline", smoothing: 0.6 },
        hoverinfo: "none", customdata: samples.map((_, i) => i),
      },
      ...(lastIdx >= 0 ? headMarker(x[lastIdx], s.index[lastIdx], s.color, "y") : []),
    ];
  });
  return {
    traces,
    layout: {
      shapes: [
        band(1, 2, WARN, "14"),
        band(2, idxMax, DANGER, "14"),
        rule(1, WARN),
        rule(2, DANGER),
        ...stateShapes(samples),
      ],
      annotations: [rightLabel(1, "WARN", WARN), rightLabel(2, "DANGER", DANGER), ...pendingLabels(samples)],
      yaxis: {
        ...darkLayout.yaxis, range: [-0.12, idxMax], fixedrange: true, zeroline: false,
        tickvals: [0, 1, 2], ticktext: ["baseline", "warn", "danger"], tickpad: 10,
      },
    },
  };
}

function rawFigure(x, samples, series) {
  const domains = [[0.56, 1], [0, 0.44]];
  const traces = [];
  const annotations = [];
  const axes = {};
  series.forEach((s, i) => {
    const yaxis = i === 0 ? "y" : "y2";
    const axisKey = i === 0 ? "yaxis" : "yaxis2";
    const warn = s.thr.map((t) => t?.warn ?? null);
    const danger = s.thr.map((t) => t?.danger ?? null);
    const vals = [...s.raw, ...danger, ...s.thr.map((t) => t?.baseline ?? null)].filter((v) => typeof v === "number");
    const lo = vals.length ? Math.min(...vals) : 0;
    const hi = vals.length ? Math.max(...vals) : 100;
    const pad = Math.max((hi - lo) * 0.18, 10);
    const top = hi + pad;
    const topLine = danger.map((d) => (d == null ? null : top));
    const step = { shape: "hv" };
    traces.push(
      { x, y: warn, yaxis, type: "scatter", mode: "lines", hoverinfo: "skip", showlegend: false,
        connectgaps: false, line: { ...step, color: WARN, width: 1.25, dash: "dot" } },
      { x, y: danger, yaxis, type: "scatter", mode: "lines", hoverinfo: "skip", showlegend: false,
        connectgaps: false, fill: "tonexty", fillcolor: `${WARN}1f`,
        line: { ...step, color: DANGER, width: 1.25, dash: "dot" } },
      { x, y: topLine, yaxis, type: "scatter", mode: "lines", hoverinfo: "skip", showlegend: false,
        connectgaps: false, fill: "tonexty", fillcolor: `${DANGER}1a`, line: { ...step, width: 0 } },
      { x, y: s.raw, yaxis, type: "scatter", mode: "lines", connectgaps: false, showlegend: false,
        line: { color: s.color, width: 2.25, shape: "spline", smoothing: 0.6 },
        hoverinfo: "none", customdata: samples.map((_, j) => j) },
    );
    const lastIdx = s.raw.findLastIndex((v) => v != null);
    if (lastIdx >= 0) traces.push(...headMarker(x[lastIdx], s.raw[lastIdx], s.color, yaxis));

    axes[axisKey] = {
      ...darkLayout.yaxis, domain: domains[i], range: [Math.max(0, lo - pad), top],
      fixedrange: true, zeroline: false, tickpad: 8, nticks: 4,
    };
    const yref = i === 0 ? "y" : "y2";
    annotations.push({
      xref: "paper", x: 0, xanchor: "left", yref: "paper", y: domains[i][1], yanchor: "bottom",
      text: `<b>${s.label}</b>`, showarrow: false, font: { color: s.color, size: 11 },
    });
    const lastThr = s.thr.findLast((t) => t);
    if (lastThr) {
      annotations.push(
        rightLabel(lastThr.warn, `warn ${Math.round(lastThr.warn)}`, WARN, yref),
        rightLabel(lastThr.danger, `danger ${Math.round(lastThr.danger)}`, DANGER, yref),
      );
    }
  });
  return {
    traces,
    layout: {
      ...axes,
      xaxis: { anchor: "y2" },
      shapes: stateShapes(samples),
      annotations: [...annotations, ...pendingLabels(samples)],
    },
  };
}

export default function GasChart({ liveSensors }) {
  const [mode, setMode] = useState("hazard");
  const [windowSec, setWindowSec] = useState(300);
  const [hover, setHover] = useState(null);
  const chartRef = useRef(null);

  const readings = liveSensors?.ok ? liveSensors.readings ?? [] : [];
  const source = SOURCE_CHIP[liveSensors?.threshold_source ?? "none"];

  const header = (extra) => (
    <div className="chart-panel-header gas-header">
      <h3 className="panel-title">
        <GaugeIcon />Gas sensors
        <span className="panel-title-subtitle"> — live, 1 Hz</span>
      </h3>
      {extra}
    </div>
  );

  if (readings.length === 0) {
    return (
      <div className="panel glass glass--dense chart-panel">
        {header(null)}
        <StateCard kind="offline">
          {liveSensors?.reason ?? "Waiting for the live sensor feed…"}
        </StateCard>
      </div>
    );
  }

  const latestTs = readings[readings.length - 1].timestamp;
  const samples = readings.filter((r) => r.timestamp >= latestTs - windowSec);
  const x = samples.map((r) => new Date(r.timestamp * 1000));
  const series = SENSORS.map((s) => {
    const thr = samples.map((r) => sensorThresholds(r, s.key));
    const raw = samples.map((r) => (typeof r[s.key] === "number" ? r[s.key] : null));
    return { ...s, thr, raw, index: raw.map((v, i) => hazardIndex(v, thr[i])) };
  });
  const anyThr = series.some((s) => s.thr.some(Boolean));
  // The hazard index is undefined without thresholds; say so and show raw
  // rather than drawing an empty axis.
  const effective = mode === "hazard" && !anyThr ? "raw" : mode;
  const fig = effective === "hazard" ? hazardFigure(x, samples, series) : rawFigure(x, samples, series);

  return (
    <div className="panel glass glass--dense chart-panel">
      {header(
        <div className="gas-controls">
          <Segmented
            label="Chart view"
            value={mode}
            onChange={setMode}
            options={[{ value: "hazard", label: "Hazard index" }, { value: "raw", label: "Raw ADC" }]}
          />
          <Segmented
            label="Time window"
            value={windowSec}
            onChange={setWindowSec}
            options={WINDOWS.map((w) => ({ value: w.sec, label: w.label }))}
          />
        </div>
      )}
      <div className="gas-subbar">
        <span className={`chip chip--${source.tone}`}>{source.text}</span>
        {mode === "hazard" && !anyThr && (
          <span className="chip chip--pending">hazard index needs board thresholds — showing raw</span>
        )}
        <span className="gas-legend">
          {series.map((s) => (
            <span key={s.key} className="chart-legend-item">
              <span className="chart-legend-dot" style={{ background: s.color, color: s.color }} />
              {s.label}
            </span>
          ))}
          <span className="chart-legend-item chart-legend-item--muted">
            <span className="chart-legend-swatch" style={{ background: PENDING_FILL }} />
            no baseline
          </span>
        </span>
      </div>
      <div className="chart-container chart-glow-well" ref={chartRef} style={{ "--chart-glow-color": "rgba(91,143,214,0.14)" }}>
        <Plot
          data={fig.traces}
          layout={{
            ...darkLayout,
            height: 360,
            margin: { l: 64, r: 92, t: 18, b: 40 },
            hovermode: "x",
            showlegend: false,
            uirevision: `${effective}-${windowSec}`,
            ...fig.layout,
            xaxis: {
              ...darkLayout.xaxis, tickformat: "%H:%M:%S", fixedrange: true, tickpad: 8, nticks: 6,
              ...fig.layout.xaxis,
            },
          }}
          config={plotlyConfig}
          useResizeHandler
          style={{ width: "100%" }}
          onHover={(e) => {
            const p = e.points?.find((pt) => pt.customdata != null);
            if (!p) return;
            const s = samples[p.customdata];
            const bounds = chartRef.current?.getBoundingClientRect();
            const rows = SENSORS.map((sensor) => {
              const t = sensorThresholds(s, sensor.key);
              const v = s[sensor.key];
              const idx = hazardIndex(v, t);
              return [sensor.label, v == null ? "—" : `${v}${idx != null ? `  ·  ${idx.toFixed(2)}` : ""}`];
            });
            rows.push(["Board", BOARD_STATE[s.state]?.label ?? s.state ?? "—"]);
            setHover({
              left: bounds ? e.event.clientX - bounds.left : e.event.clientX,
              top: bounds ? e.event.clientY - bounds.top : e.event.clientY,
              title: new Date(s.timestamp * 1000).toLocaleTimeString(),
              rows,
            });
          }}
          onUnhover={() => setHover(null)}
        />
        <ChartTooltip point={hover} containerRef={chartRef} />
      </div>
    </div>
  );
}
