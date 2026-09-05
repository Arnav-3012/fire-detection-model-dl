import { useRef, useState } from "react";
import Plot from "react-plotly.js";
import { LEVELS, LEVEL_COLOR, levelIndex } from "../levels";
import { darkLayout, plotlyConfig } from "../plotlyTheme";
import LevelBadge from "../components/LevelBadge";
import CountUp from "../components/CountUp";
import StateCard from "../components/StateCard";
import LiveSensorChart from "../components/LiveSensorChart";
import ChartTooltip from "../components/ChartTooltip";
import Reveal from "../components/Reveal";
import { SkeletonMetricCard, SkeletonPanel } from "../components/Skeleton";
import { FlameIcon, PinIcon, ClockIcon, ChartIcon, PercentIcon, AlertTriangleIcon } from "../components/icons";

export default function Overview({ incidents, liveSensors, station, loading }) {
  const [fusionHover, setFusionHover] = useState(null);
  const fusionChartRef = useRef(null);

  if (loading) {
    return (
      <div className="tab-content">
        <div className="grid-12">
          <div className="col-5">
            <SkeletonPanel height={140} />
          </div>
          <div className="col-7">
            <div className="card-grid">
              <SkeletonMetricCard />
              <SkeletonMetricCard />
              <SkeletonMetricCard />
              <SkeletonMetricCard />
            </div>
          </div>
        </div>
        <div className="grid-12">
          <div className="col-8">
            <SkeletonPanel height={320} />
          </div>
          <div className="col-4 stack-col">
            <SkeletonPanel height={140} />
            <SkeletonPanel height={140} />
          </div>
        </div>
        <SkeletonPanel height={320} />
      </div>
    );
  }

  const total = incidents.length;
  const warningCount = incidents.filter((i) => i.level === "WARNING").length;
  const criticalCount = incidents.filter((i) => i.level === "CRITICAL").length;
  const cancelled = incidents.filter((i) => i.outcome === "CANCELLED").length;
  const cancelRate = total ? ((cancelled / total) * 100).toFixed(1) : "0.0";
  const mostRecent = incidents.length ? incidents[incidents.length - 1] : null;

  const recentCritical =
    mostRecent?.level === "CRITICAL" &&
    Date.now() - new Date(mostRecent.timestamp).getTime() < 5 * 60 * 1000;

  // Shared live-level lookup (2026-09-04) — edge/livelog.py now stamps
  // every 1 Hz live sample with the fused level at every tier (SAFE/WATCH
  // included, not just WARNING+ like the incidents log), so the freshest
  // live sample is a genuine live status. Used by both the System Health
  // hero and the fusion timeline's header stat pill, so "live vs. last
  // incident" is computed once and can't drift between the two.
  const liveReadings = liveSensors?.ok ? liveSensors.readings ?? [] : [];
  const latestLive = liveReadings.length ? liveReadings[liveReadings.length - 1] : null;
  const isLiveLevel = latestLive?.level != null;
  const displayLevel = isLiveLevel ? latestLive.level : mostRecent?.level;

  const x = incidents.map((i) => i.timestamp);
  const y = incidents.map((i) => levelIndex(i.level));
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
    <div className="tab-content">
      {/* Row 1 — hero status anchor + compact metrics, side by side rather
          than the hero sitting alone full-width. */}
      <div className="grid-12">
        <div className="col-5">
          <SystemHealthHero
            mostRecent={mostRecent}
            recentCritical={recentCritical}
            total={total}
            isLive={isLiveLevel}
            liveLevel={latestLive?.level}
          />
        </div>
        <div className="col-7">
          <div className="card-grid">
            <MetricCard label="Total incidents" value={total} icon={ChartIcon} />
            <MetricCard label="WARNING count" value={warningCount} accent={LEVEL_COLOR.WARNING} icon={AlertTriangleIcon} />
            {/* Priority weight: an active CRITICAL count is the single most
                urgent number on this tab, so it gets a larger value and a
                visible glow rather than sitting at equal weight with the
                other three metrics. */}
            <MetricCard
              label="CRITICAL count"
              value={criticalCount}
              accent={LEVEL_COLOR.CRITICAL}
              icon={AlertTriangleIcon}
              priority={criticalCount > 0}
            />
            {/* Quiet weight: cancel rate is useful context, not something
                that needs to shout — smaller, dimmer value than its
                neighbors. */}
            <MetricCard label="Cancel rate" value={`${cancelRate}%`} icon={PercentIcon} quiet />
          </div>
        </div>
      </div>

      {/* Row 2 — fusion timeline (large, left) paired with a narrow
          right-hand column stacking the fire-station card on top of the
          most-recent-event detail, instead of either sitting alone
          full-width. */}
      <div className="grid-12">
        <div className="col-8">
          {/* height:100% removed (2026-09-04 bug fix) — it was stretching
              this card to match the tall right-hand stack column while the
              chart itself stayed a fixed 260px, leaving a large dead gap
              below the plot. The header/stat/chart now size to their own
              content, like every other panel. */}
          <Reveal className="panel glass chart-panel">
            <div className="chart-panel-header">
              <h3 className="panel-title"><ChartIcon />Fusion level timeline</h3>
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
                      ["Timestamp", timestamp],
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
        </div>
        <div className="col-4 stack-col">
          <Reveal delay={80}>
            <FireStationCard station={station} />
          </Reveal>
          <Reveal delay={140}>
            <RecentEventCard mostRecent={mostRecent} recentCritical={recentCritical} />
          </Reveal>
        </div>
      </div>

      {/* Row 3 — the live sensor chart earns full width: it's information-
          dense (two series + four threshold lines) and benefits from
          horizontal room. */}
      <Reveal>
        <LiveSensorChart liveSensors={liveSensors} />
      </Reveal>
    </div>
  );
}

// The single distinct visual anchor on Overview — a large status ring in
// the spirit of Vision UI's "Satisfaction Rate" gauge, breaking the
// pattern of "another glass card" that every other section still is.
// Live-health fix (2026-09-04): this used to derive health purely from
// `mostRecent` (the incidents log), which only ever contains WARNING/
// CRITICAL rows (edge/main.py's notify_agent gate) — a single old
// CRITICAL event permanently pinned this at 0% with no way to recover,
// since nothing ever logs "back to SAFE" as an incident. edge/livelog.py
// now stamps every 1 Hz live sample with the fused level at every tier
// (SAFE/WATCH included), so the freshest live sample is a genuine,
// self-recovering live status — preferred here whenever it exists.
// Falls back to the last-incident logic only when there's no live feed
// at all (edge/main.py not running), so the gauge never renders blank.
function SystemHealthHero({ mostRecent, recentCritical, total, isLive, liveLevel }) {
  const level = isLive ? liveLevel : mostRecent?.level ?? "SAFE";
  const color = LEVEL_COLOR[level] ?? LEVEL_COLOR.SAFE;
  const idx = levelIndex(level);
  const healthPct = Math.max(0, 100 - idx * (100 / 3));
  const r = 56;
  const circumference = 2 * Math.PI * r;
  const dash = (healthPct / 100) * circumference;
  const pulseCritical = isLive ? level === "CRITICAL" : recentCritical;

  return (
    <div className={`glass hero${pulseCritical ? " metric-card--alert" : ""}`} style={{ height: "100%" }}>
      <div className="hero-ring">
        <svg viewBox="0 0 132 132">
          <circle className="hero-ring-track" cx="66" cy="66" r={r} />
          <circle
            className="hero-ring-value"
            cx="66"
            cy="66"
            r={r}
            stroke={color}
            strokeDasharray={`${dash} ${circumference - dash}`}
          />
        </svg>
        <div className="hero-ring-label">
          <span className="value">{Math.round(healthPct)}%</span>
          <span className="caption">{isLive ? "system health" : "system health (last incident)"}</span>
        </div>
      </div>
      <div className="hero-body">
        <h2 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <FlameIcon width={17} height={17} style={{ color, flexShrink: 0 }} />
          System status
        </h2>
        <p>
          {isLive
            ? "Live fusion status from the edge feed, updated every 3s."
            : total === 0
              ? "No live feed and no incidents recorded yet — system nominal."
              : `No live feed — showing the last logged incident (${total} logged total).`}
        </p>
        <div className="hero-badges">
          <LevelBadge level={level} pulse={pulseCritical} />
          {isLive ? (
            <span className="app-subtitle">live</span>
          ) : (
            mostRecent && <span className="app-subtitle">{mostRecent.timestamp}</span>
          )}
        </div>
      </div>
    </div>
  );
}

// Horizontal row layout (icon + label left, value right) rather than the
// stacked "label above value" pattern most other cards use — deliberate
// rhythm break so consecutive cards in this column don't read as
// identical templates.
function RecentEventCard({ mostRecent, recentCritical }) {
  return (
    <div className={`glass panel${recentCritical ? " metric-card--alert" : ""}`}>
      <h3 className="panel-title"><ClockIcon />Most recent event</h3>
      {mostRecent ? (
        <div>
          <div className="panel-row">
            <div className="panel-row-label"><span>Level</span></div>
            <LevelBadge level={mostRecent.level} pulse={recentCritical} />
          </div>
          <div className="panel-row">
            <div className="panel-row-label"><span>p_fire</span></div>
            <div className="panel-row-value">{mostRecent.p_fire}</div>
          </div>
          {mostRecent.outcome && (
            <div className="panel-row">
              <div className="panel-row-label"><span>Outcome</span></div>
              <div className="panel-row-value">{mostRecent.outcome}</div>
            </div>
          )}
          <div className="panel-row">
            <div className="panel-row-label"><span>Time</span></div>
            <div className="panel-row-value" style={{ fontSize: "0.85rem", fontWeight: 500, color: "var(--text-dim)" }}>
              {mostRecent.timestamp}
            </div>
          </div>
        </div>
      ) : (
        <StateCard kind="empty">No incidents yet</StateCard>
      )}
    </div>
  );
}

function MetricCard({ label, value, accent, icon: Icon, priority = false, quiet = false }) {
  const cls = ["glass", "metric-card", priority && "metric-card--priority", quiet && "metric-card--quiet"]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls}>
      <div className="metric-label" style={{ display: "flex", alignItems: "center", gap: 7 }}>
        {Icon && <Icon width={12} height={12} style={{ color: accent ?? "var(--accent)", flexShrink: 0 }} />}
        {label}
      </div>
      <div className="metric-value" style={accent ? { color: accent } : undefined}>
        <CountUp value={value} />
      </div>
    </div>
  );
}

// Compact fire-station summary for Overview — reuses the same /api/fire-station
// poll App.jsx already runs for the dedicated tab; no second lookup.
// Cool-tint variant + horizontal rows: this card is locational/reference
// data, not a hazard signal, so it deliberately reads as a different
// category from the ember data cards around it (per-card accent
// variation) while staying nowhere near the fusion-level status colors.
function FireStationCard({ station }) {
  return (
    <div className="panel glass glass--cool">
      <h3 className="panel-title"><PinIcon />Nearest fire station</h3>
      {!station ? (
        <StateCard kind="empty">Looking up the nearest station…</StateCard>
      ) : (
        <div>
          {station.found ? (
            <>
              <div className="panel-row">
                <div className="panel-row-label"><span>Name</span></div>
                <div className="panel-row-value">{station.name}</div>
              </div>
              <div className="panel-row">
                <div className="panel-row-label"><span>Distance</span></div>
                <div className="panel-row-value">{station.distance_km} km</div>
              </div>
              {station.phone && (
                <div className="panel-row">
                  <div className="panel-row-label"><span>Phone</span></div>
                  <div className="panel-row-value">{station.phone}</div>
                </div>
              )}
            </>
          ) : (
            <div className="panel-row">
              <div className="panel-row-label"><span>Status</span></div>
              <div className="panel-row-value" style={{ fontSize: "0.85rem", fontWeight: 500, color: "var(--text-dim)" }}>
                {station.line}
              </div>
            </div>
          )}
          <div className="panel-row">
            <div className="panel-row-label"><span>Fire / Unified</span></div>
            <div className="panel-row-value">
              {station.fire_number ?? "101"} / {station.unified_number ?? "112"}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
