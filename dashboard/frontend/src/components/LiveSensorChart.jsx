import { useRef, useState } from "react";
import Plot from "react-plotly.js";
import { darkLayout, plotlyConfig } from "../plotlyTheme";
import StateCard from "./StateCard";
import ChartTooltip from "./ChartTooltip";
import { GaugeIcon } from "./icons";

// Brand pivot (2026-09-04): mq2/mq135 deliberately stay on cool tones
// (steel-blue / violet) rather than moving onto the new warm ember chrome —
// now that amber is the palette's *neutral* accent too, a raw instrument
// reading drawn in amber would risk reading as a hazard signal by
// association. Keeping these two lines cool is what actually preserves the
// original brief's intent (hazard colors reserved for status only): they
// contrast cleanly against both the new ember chrome AND the amber/red
// threshold lines, so nothing on this chart is ambiguous with a fusion
// status color. Retuned slightly from the pre-pivot blue/purple so they sit
// comfortably rather than clashing against the warmer background.
const MQ2_COLOR = "#5b8fd6";
const MQ135_COLOR = "#9d8bd6";
const WARN_COLOR = "#f0954a";
const DANGER_COLOR = "#f0453a";

function thresholdLine(y, color) {
  return {
    type: "line",
    xref: "paper",
    x0: 0,
    x1: 0.965, // stop short of the right edge so the label (below) has clear air
    y0: y,
    y1: y,
    line: { color, width: 1.5, dash: "dot" },
  };
}

// Threshold labels as separate annotations rather than Plotly's inline
// shape `label` — gives full control over size/placement so they read
// clearly and don't collide with the y-axis tick labels or each other.
function thresholdAnnotation(y, color, label) {
  return {
    xref: "paper",
    x: 1,
    xanchor: "left",
    y,
    yref: "y",
    yanchor: "middle",
    text: label,
    showarrow: false,
    font: { color, size: 12, family: "system-ui, sans-serif" },
    align: "left",
  };
}

export default function LiveSensorChart({ liveSensors }) {
  const [hover, setHover] = useState(null);
  const chartRef = useRef(null);

  if (!liveSensors) {
    return (
      <div className="panel glass glass--cool chart-panel">
        <div className="chart-panel-header">
          <h3 className="panel-title"><GaugeIcon />Live gas sensor readings</h3>
        </div>
        <StateCard kind="offline">Waiting for the live sensor feed…</StateCard>
      </div>
    );
  }

  if (liveSensors.ok === false) {
    return (
      <div className="panel glass glass--cool chart-panel">
        <div className="chart-panel-header">
          <h3 className="panel-title"><GaugeIcon />Live gas sensor readings</h3>
        </div>
        <StateCard kind="offline">
          {liveSensors.reason ?? "No live data yet — is edge/main.py running?"}
        </StateCard>
      </div>
    );
  }

  const readings = liveSensors.readings ?? [];
  const t = liveSensors.thresholds ?? {};
  const x = readings.map((r) => new Date(r.timestamp * 1000));
  const mq2 = readings.map((r) => r.mq2);
  const mq135 = readings.map((r) => r.mq135);
  const timeLabels = x.map((d) => d.toLocaleTimeString());
  const latestMq2 = mq2.length ? mq2[mq2.length - 1] : null;
  const latestMq135 = mq135.length ? mq135[mq135.length - 1] : null;

  const thresholdVals = [t.mq2_warn, t.mq2_danger, t.mq135_warn, t.mq135_danger].filter(
    (v) => typeof v === "number"
  );
  const dataVals = [...mq2, ...mq135].filter((v) => typeof v === "number");
  const allVals = [...thresholdVals, ...dataVals];

  // Fix for bug #1: the prior chart auto-fit tightly to whatever points
  // existed, so danger lines near the top of the data range sat flush
  // against the plot edge. Derive an explicit range instead: 20% headroom
  // above the highest danger threshold (or highest reading, if it happens
  // to exceed thresholds) and a floor comfortably below the lowest value,
  // so every threshold line sits clearly inside the visible area.
  //
  // Refinement: the floor used to fall out of whatever data happened to be
  // on screen, which let it drift down toward 0 and waste most of the
  // chart height on a 0-40ish range neither sensor's calibrated baseline
  // ever occupies (config.yaml Phase 6: mq2_baseline=57.1, mq135_baseline
  // =51.1). Anchor the floor to the lower of the two real baselines
  // instead, with headroom below it so both lines still have visible room
  // rather than sitting pinned to the bottom edge.
  const baselineVals = [t.mq2_baseline, t.mq135_baseline].filter(
    (v) => typeof v === "number"
  );
  let yRange;
  if (allVals.length) {
    const dataMax = Math.max(...allVals);
    const floor = baselineVals.length
      ? Math.max(0, Math.min(...baselineVals) * 0.85)
      : Math.max(0, Math.min(...allVals) - Math.max(dataMax - Math.min(...allVals), 1) * 0.15);
    const headroom = dataMax * 0.2;
    yRange = [floor, dataMax + headroom];
  }

  const shapes = [
    thresholdLine(t.mq2_warn, WARN_COLOR),
    thresholdLine(t.mq2_danger, DANGER_COLOR),
    thresholdLine(t.mq135_warn, `${WARN_COLOR}aa`),
    thresholdLine(t.mq135_danger, `${DANGER_COLOR}aa`),
  ].filter((s) => typeof s.y0 === "number");

  const annotations = [
    thresholdAnnotation(t.mq2_warn, WARN_COLOR, "MQ-2 warn"),
    thresholdAnnotation(t.mq2_danger, DANGER_COLOR, "MQ-2 danger"),
    thresholdAnnotation(t.mq135_warn, `${WARN_COLOR}dd`, "MQ-135 warn"),
    thresholdAnnotation(t.mq135_danger, `${DANGER_COLOR}dd`, "MQ-135 danger"),
  ].filter((a) => typeof a.y === "number");

  return (
    // Cool-tint chrome (steel-blue border glow) marks this as raw
    // instrument data, the same category language established for the
    // Fire Station cards — consistent "this isn't a hazard signal" cue
    // across the dashboard.
    <div className="panel glass glass--cool chart-panel">
      <div className="chart-panel-header">
        <h3 className="panel-title"><GaugeIcon />Live gas sensor readings</h3>
        {latestMq2 !== null && latestMq135 !== null && (
          <div className="chart-panel-stat">
            <span className="stat-caption">mq-2</span>
            <span className="stat-value" style={{ color: MQ2_COLOR }}>{Math.round(latestMq2)}</span>
            <span className="stat-caption">mq-135</span>
            <span className="stat-value" style={{ color: MQ135_COLOR }}>{Math.round(latestMq135)}</span>
          </div>
        )}
      </div>
      {readings.length === 0 ? (
        <StateCard kind="offline">Sensor feed connected, no samples yet.</StateCard>
      ) : (
        <>
          {/* Custom legend replacing Plotly's default legend chrome — dots
              + small-caps labels matching the rest of the UI's type
              language instead of Plotly's boxed default. */}
          <div className="chart-legend">
            <span className="chart-legend-item">
              <span className="chart-legend-dot" style={{ background: MQ2_COLOR, color: MQ2_COLOR }} />
              MQ-2
            </span>
            <span className="chart-legend-item">
              <span className="chart-legend-dot" style={{ background: MQ135_COLOR, color: MQ135_COLOR }} />
              MQ-135
            </span>
          </div>
          <div className="chart-container chart-glow-well" ref={chartRef} style={{ "--chart-glow-color": "rgba(91,143,214,0.16)" }}>
            <Plot
              data={[
                {
                  x,
                  y: mq2,
                  type: "scatter",
                  mode: "lines",
                  name: "MQ-2",
                  line: { color: MQ2_COLOR, width: 2, shape: "spline" },
                  fill: "tozeroy",
                  fillcolor: `${MQ2_COLOR}14`,
                  customdata: timeLabels.map((t, idx) => [t, mq2[idx], mq135[idx]]),
                  hoverinfo: "none",
                  showlegend: false,
                },
                {
                  x,
                  y: mq135,
                  type: "scatter",
                  mode: "lines",
                  name: "MQ-135",
                  line: { color: MQ135_COLOR, width: 2, shape: "spline" },
                  fill: "tozeroy",
                  fillcolor: `${MQ135_COLOR}10`,
                  customdata: timeLabels.map((t, idx) => [t, mq2[idx], mq135[idx]]),
                  hoverinfo: "none",
                  showlegend: false,
                },
              ]}
              layout={{
                ...darkLayout,
                // Bug fix round 2 (2026-09-04): 260px read as stretched-
                // thin with excessive gridline spacing once the header/
                // legend took over some of the vertical rhythm the old
                // taller chart used to carry. Restored to a fuller 340px
                // to match the fusion timeline's height.
                height: 340,
                shapes,
                annotations,
                hovermode: "x unified",
                showlegend: false,
                // Bug fix round 3 (2026-09-04): same tick-label-cramped
                // complaint as the fusion timeline — margin.l (left as
                // darkLayout's default 50px, plenty for short numeric
                // ticks like "200"/"150") wasn't the problem; the gap
                // between the tick text and the plot's own edge (Plotly's
                // `tickpad`) was too tight on both axes. Explicit tickpad +
                // a touch more left margin for real breathing room.
                margin: { ...darkLayout.margin, l: 58, r: 96, t: 12, b: 46 },
                xaxis: { ...darkLayout.xaxis, title: "", tickpad: 12 },
                yaxis: { ...darkLayout.yaxis, title: "ADC reading", range: yRange, tickpad: 12 },
              }}
              config={plotlyConfig}
              useResizeHandler
              style={{ width: "100%" }}
              onHover={(e) => {
                const p = e.points?.[0];
                if (!p || !p.customdata) return;
                const bounds = chartRef.current?.getBoundingClientRect();
                const [time, mq2Val, mq135Val] = p.customdata;
                setHover({
                  left: bounds ? e.event.clientX - bounds.left : e.event.clientX,
                  top: bounds ? e.event.clientY - bounds.top : e.event.clientY,
                  title: time,
                  rows: [
                    ["MQ-2", mq2Val],
                    ["MQ-135", mq135Val],
                  ],
                });
              }}
              onUnhover={() => setHover(null)}
            />
            <ChartTooltip point={hover} containerRef={chartRef} />
          </div>
        </>
      )}
    </div>
  );
}
