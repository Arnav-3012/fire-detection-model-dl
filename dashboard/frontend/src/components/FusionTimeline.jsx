import { useRef, useState } from "react";
import Plot from "react-plotly.js";
import { LEVELS, LEVEL_COLOR, levelIndex } from "../levels";
import { darkLayout, plotlyConfig } from "../plotlyTheme";
import StateCard from "./StateCard";
import ChartTooltip from "./ChartTooltip";
import Reveal from "./Reveal";
import { ChartIcon } from "./icons";
import { formatTimestamp } from "../formatTimestamp";

// Fusion level timeline, moved out of Overview.jsx unchanged (2026-09-24)
// when the home page was rebuilt around the live feed. `displayLevel` is
// the live level when the edge feed is fresh, else the last incident's;
// `isLiveLevel` says which, for the header caption.
export default function FusionTimeline({ incidents, displayLevel, isLiveLevel }) {
  const [fusionHover, setFusionHover] = useState(null);
  const fusionChartRef = useRef(null);

  const x = incidents.map((i) => i.timestamp);
  const y = incidents.map((i) => levelIndex(i.level));
  // Date-once check (same fix as GasChart): only worth collapsing to
  // a single header date + time-only ticks when every visible incident
  // actually falls on the same calendar day — unlike the live sensor
  // chart's fixed short rolling window, this chart's span depends on how
  // many incidents exist and can legitimately cross days, in which case
  // Plotly's existing date+time tick format (see the tickpad comment
  // below) is the correct, already-working behavior and must stay.
  const incidentDates = incidents.map((i) => new Date(i.timestamp));
  const allSameDay =
    incidentDates.length > 0 &&
    incidentDates.every((d) => d.toDateString() === incidentDates[0].toDateString());
  const fusionDateLabel = allSameDay
    ? incidentDates[0].toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
    : null;
  const colors = incidents.map((i) => LEVEL_COLOR[i.level] ?? "#6b7280");
  // CRITICAL points get a visibly larger marker + a soft glow halo (via a
  // second, larger, translucent marker trace beneath) so the eye lands on
  // the events that matter most, not just any dot on the line.
  const sizes = incidents.map((i) => (i.level === "CRITICAL" ? 16 : i.level === "WARNING" ? 11 : 8));
  const criticalGlowX = incidents.filter((i) => i.level === "CRITICAL").map((i) => i.timestamp);
  const criticalGlowY = incidents.filter((i) => i.level === "CRITICAL").map((i) => levelIndex(i.level));

  // Faint per-level horizontal background bands — each band spans its
  // row's y-range so the chart carries depth even where no line/dot
  // currently sits. Rows are geometrically equal (confirmed via rendered
  // SVG: each band is exactly 62.5px tall at height:320/range:[-0.5,3.5]),
  // but a prior pass's "0a" (~4%) opacity made every band, SAFE included,
  // read as empty space rather than a real row — bumped to "12" (~7%) so
  // the zone is actually perceptible without becoming a wash.
  const levelBands = LEVELS.map((level, idx) => ({
    type: "rect",
    xref: "paper",
    x0: 0,
    x1: 1,
    yref: "y",
    y0: idx - 0.5,
    y1: idx + 0.5,
    fillcolor: `${LEVEL_COLOR[level]}12`,
    line: { width: 0 },
    layer: "below",
  }));

  // Explicit gridline at every row boundary, INCLUDING y=0 (SAFE/WATCH
  // border) and the plot's outer top/bottom edges. Real bug found by
  // inspecting the rendered SVG: Plotly always intercepts y=0 and draws
  // it via a separate "zerolinelayer" (zeroline: true is the library
  // default and cannot be suppressed by tickvals/range alone), NOT the
  // normal "gridlayer" the other three row boundaries use — so the
  // SAFE/WATCH boundary was structurally different from every other
  // gridline, not just visually fainter. `zeroline: false` below turns
  // that off; these four manually-drawn lines replace it uniformly so
  // SAFE's row boundary is drawn exactly like WATCH/WARNING/CRITICAL's.
  const rowGridlines = [-0.5, 0.5, 1.5, 2.5, 3.5].map((y0) => ({
    type: "line",
    xref: "paper",
    x0: 0,
    x1: 1,
    yref: "y",
    y0,
    y1: y0,
    // Warm-neutral gridline (brand pivot 2026-09-04 — was cool blue-gray
    // rgba(148,163,184,...)), matching plotlyTheme.js's darkLayout grid
    // tokens so this chart's manually-drawn boundaries don't read as a
    // different, cooler-toned layer from the rest of the UI.
    line: { color: "rgba(214,180,154,0.14)", width: 1 },
    layer: "below",
  }));

  // SAFE-level baseline: a solid, clearly-visible line through the SAFE
  // row's own center (not its boundary) so a stretch of no-events reads
  // as "the system held at SAFE," not just empty lower chart area.
  const safeBaseline = {
    type: "line",
    xref: "paper",
    x0: 0,
    x1: 1,
    yref: "y",
    y0: 0,
    y1: 0,
    line: { color: LEVEL_COLOR.SAFE, width: 2, dash: "solid" },
    opacity: 0.6,
    layer: "below",
  };

  return (
    <Reveal className="panel glass chart-panel">
      <div className="chart-panel-header">
        <h3 className="panel-title">
          <ChartIcon />Fusion level timeline
          {fusionDateLabel && <span className="panel-title-subtitle"> — {fusionDateLabel}</span>}
        </h3>
        {displayLevel && (
          <div className="chart-panel-stat">
            {/* "current" alone was misleading when this only ever
                showed the last logged incident (WARNING/CRITICAL
                only, could be arbitrarily stale). Now genuinely
                live when edge/livelog.py's feed has a sample
                (2026-09-04 — every level is now recorded, not just
                WARNING+), falling back to "last incident" only when
                there's no live feed at all. */}
            <span className="stat-caption">{isLiveLevel ? "current" : "last incident"}</span>
            <span className="stat-value" style={{ color: LEVEL_COLOR[displayLevel] ?? "var(--text)" }}>
              {displayLevel}
            </span>
          </div>
        )}
      </div>
      <div
        className="chart-container chart-glow-well"
        ref={fusionChartRef}
        style={{ "--chart-glow-color": `${LEVEL_COLOR[displayLevel ?? "SAFE"]}29` }}
      >
      {incidents.length ? (
        <Plot
          data={[
            // Step-line: level is discrete/categorical, so a staircase
            // connector (not a smooth interpolation) is the honest
            // representation of "the system held at WARNING, then
            // jumped to CRITICAL" rather than implying a gradual slide.
            {
              x,
              y,
              mode: "lines",
              type: "scatter",
              line: { shape: "hv", color: "rgba(214,180,154,0.5)", width: 1.75 },
              // Soft area-fill under the step line, tinted to the
              // current level — turns the plain line into something
              // that reads as "instrument trace" rather than a bare
              // default Plotly line chart.
              fill: "tozeroy",
              fillcolor: `${LEVEL_COLOR[displayLevel ?? "SAFE"]}14`,
              hoverinfo: "skip",
              showlegend: false,
            },
            // Soft glow halo beneath CRITICAL points only.
            {
              x: criticalGlowX,
              y: criticalGlowY,
              mode: "markers",
              type: "scatter",
              marker: { color: LEVEL_COLOR.CRITICAL, size: 30, opacity: 0.25 },
              hoverinfo: "skip",
              showlegend: false,
            },
            {
              x,
              y,
              mode: "markers",
              type: "scatter",
              marker: { color: colors, size: sizes, line: { color: "rgba(13,11,10,0.6)", width: 1 } },
              customdata: incidents.map((i) => [i.level, i.timestamp, i.p_fire, i.gas_high]),
              hoverinfo: "none",
              showlegend: false,
            },
            // Invisible, much larger hit-area markers on top — a real
            // human hovering the visible dot (often just 8-16px) with
            // a mouse routinely misses it and gets nothing. This trace
            // is what onHover actually binds to below (via its own
            // customdata), so the tooltip triggers reliably across a
            // generous radius around each point, not just its exact
            // pixel center.
            {
              x,
              y,
              mode: "markers",
              type: "scatter",
              marker: { color: "rgba(0,0,0,0)", size: 34 },
              customdata: incidents.map((i) => [i.level, i.timestamp, i.p_fire, i.gas_high]),
              hoverinfo: "none",
              showlegend: false,
            },
          ]}
          layout={{
            ...darkLayout,
            // Bug fix round 2 (2026-09-04): the 260px height from the
            // chart-panel redesign left this card visibly shorter
            // than the right-hand stack column, reading as a large
            // gap on the page rather than a deliberately compact
            // chart. Restored to a fuller 340px so the plot actually
            // fills its card instead of floating in whitespace.
            height: 340,
            hovermode: "closest",
            // Fix: "CRITICAL" (the longest of the four level labels)
            // was clipped at its left edge ("RITICAL") — darkLayout's
            // shared margin.l (50px) is narrower than the label
            // itself. Measured directly in headless Chrome by
            // rendering this exact chart config and reading the tick
            // label's actual left-edge position: clipping starts
            // below margin.l=55 (0.28px clearance at exactly 55,
            // negative — i.e. clipped — at 50). 72 (the first-pass
            // fix) over-corrected, leaving a visibly wide gap between
            // the labels and the plot; retightened to 60 — 5px of
            // real buffer past the measured 55px minimum, not the
            // 17px+ the prior value left.
            //
            // Bug fix round 2 (2026-09-04): developer screenshot
            // showed the row labels (CRITICAL/WARNING/WATCH/SAFE)
            // sitting cramped right against the plot's left edge —
            // 60px was enough to avoid clipping but not enough for
            // visual breathing room. Bumped to 78px (18px of real
            // extra clearance past the measured 55px clipping
            // threshold, not just the prior 5px).
            margin: { ...darkLayout.margin, l: 78, b: 54 },
            xaxis: {
              ...darkLayout.xaxis,
              // Matching tickpad on the x-axis so the "22:45 / Sep 2,
              // 2026"-style date ticks get the same breathing room
              // from the plot as the y-axis labels now do.
              tickpad: 12,
              // Date-once fix: when every incident falls on the same
              // calendar day, the date is already shown once in the
              // header subtitle above — force time-only ticks here so
              // the date isn't ALSO repeated on every tick. When
              // incidents span multiple days, omit this and let
              // Plotly's default date+time auto-format stand (still
              // correct in that case — see the tickpad comment above).
              ...(allSameDay ? { tickformat: "%H:%M:%S" } : {}),
            },
            shapes: [...levelBands, ...rowGridlines, safeBaseline],
            // range:[-0.5,3.5] was already correct in the prior pass —
            // confirmed via the rendered SVG that all four bands ARE
            // exactly 62.5px tall (equal). The actual bug was that
            // Plotly's own gridlayer skips y=0 and routes it through a
            // separate zerolinelayer instead (zeroline:true is the
            // library default, independent of tickvals/range), so
            // SAFE's row boundary rendered differently from the other
            // three and read as "not really a row." `zeroline: false`
            // below turns that off; `rowGridlines` (defined above,
            // drawn as explicit shapes at -0.5/0.5/1.5/2.5/3.5) draws
            // every row boundary — SAFE included — through the exact
            // same code path, so it's genuinely indistinguishable in
            // treatment from WATCH/WARNING/CRITICAL's boundaries.
            yaxis: {
              ...darkLayout.yaxis,
              tickvals: [0, 1, 2, 3],
              ticktext: ["SAFE", "WATCH", "WARNING", "CRITICAL"],
              range: [-0.5, 3.5],
              autorange: false,
              zeroline: false,
              showgrid: false,
              fixedrange: true,
              // Bug fix round 3 (2026-09-04): margin.l (78px) controls
              // the total space reserved for the label block, but not
              // the gap between the label text and the plot's own
              // left edge — that gap is Plotly's `tickpad`, which
              // defaults to a few px and read as "labels cramped
              // against the chart" in the developer's screenshot even
              // after the margin increase. Explicit tickpad opens
              // real breathing room between the two.
              tickpad: 14,
            },
          }}
          config={plotlyConfig}
          useResizeHandler
          style={{ width: "100%" }}
          onHover={(e) => {
            const p = e.points?.[0];
            if (!p || !p.customdata) return;
            const bounds = fusionChartRef.current?.getBoundingClientRect();
            const [level, timestamp, pFire, gasHigh] = p.customdata;
            setFusionHover({
              left: bounds ? e.event.clientX - bounds.left : e.event.clientX,
              top: bounds ? e.event.clientY - bounds.top : e.event.clientY,
              title: level,
              rows: [
                ["Timestamp", formatTimestamp(timestamp)],
                ["p_fire", pFire],
                ["gas_high", String(gasHigh)],
              ],
            });
          }}
          onUnhover={() => setFusionHover(null)}
        />
      ) : (
        <StateCard kind="empty">No incident data yet.</StateCard>
      )}
      <ChartTooltip point={fusionHover} containerRef={fusionChartRef} />
      </div>
    </Reveal>
  );
}
