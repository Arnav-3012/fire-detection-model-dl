import { LEVEL_COLOR } from "../levels";
import LevelBadge from "../components/LevelBadge";
import CountUp from "../components/CountUp";
import StateCard from "../components/StateCard";
import Reveal from "../components/Reveal";
import StatusStrip from "../components/StatusStrip";
import CameraFeed from "../components/CameraFeed";
import LiveReadout from "../components/LiveReadout";
import GasChart from "../components/GasChart";
import FusionTimeline from "../components/FusionTimeline";
import SecondOpinion from "../components/SecondOpinion";
import { SkeletonMetricCard } from "../components/Skeleton";
import { PinIcon, ClockIcon, ChartIcon, PercentIcon, AlertTriangleIcon, BellRingIcon } from "../components/icons";
import { formatTimestamp } from "../formatTimestamp";
import { latestSample, isStale } from "../live";
import { useNow } from "../useNow";

// Home page, rebuilt live-first (2026-09-24). Absorbs the old Live View and
// Nearest Fire Station tabs, ordered by what an operator needs first:
//   1. status strip — the live verdict and whether to trust it
//   2. camera + right-now readout — what is happening, at a glance
//   3. gas history + fire station / most recent event
//   4. cloud second opinion
//   5. incident history (timeline + counts) — context, not live
// The live feed is the /ws/live socket (App.jsx); incidents still poll.

export default function Overview({ incidents, liveSensors, liveError, station, loading }) {
  const now = useNow(1000);
  const sample = latestSample(liveSensors);
  const offline = isStale(sample, now);
  const liveLevel = offline ? null : sample?.level ?? null;

  const total = incidents.length;
  const warningCount = incidents.filter((i) => i.level === "WARNING").length;
  const criticalCount = incidents.filter((i) => i.level === "CRITICAL").length;
  const cancelled = incidents.filter((i) => i.outcome === "CANCELLED").length;
  const cancelRate = total ? ((cancelled / total) * 100).toFixed(1) : "0.0";
  const mostRecent = incidents.length ? incidents[incidents.length - 1] : null;
  const recentCritical =
    mostRecent?.level === "CRITICAL" && now - new Date(mostRecent.timestamp).getTime() < 5 * 60 * 1000;

  return (
    <div className="tab-content">
      <StatusStrip
        sample={sample}
        offline={offline}
        liveSensors={liveSensors}
        lastIncident={mostRecent}
        now={now}
      />
      {liveError && !liveSensors && <StateCard kind="error">live feed: {liveError}</StateCard>}

      <div className="grid-12">
        <div className="col-7">
          <Reveal>
            <CameraFeed
              camera={liveSensors?.camera}
              level={liveLevel}
              pFire={offline ? null : sample?.p_fire}
              now={now}
            />
          </Reveal>
        </div>
        <div className="col-5">
          <Reveal delay={60} style={{ height: "100%" }}>
            <LiveReadout liveSensors={liveSensors} sample={sample} offline={offline} />
          </Reveal>
        </div>
      </div>

      <div className="grid-12">
        <div className="col-8">
          <Reveal>
            <GasChart liveSensors={liveSensors} />
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

      <Reveal className="panel glass chart-panel">
        <div className="chart-panel-header">
          <h3 className="panel-title">
            Cloud second opinion
            <span className="panel-title-subtitle"> — advisory, never gates the alarm</span>
          </h3>
        </div>
        <SecondOpinion data={liveSensors?.second_opinion} />
      </Reveal>

      <h2 className="section-heading">Incident history</h2>
      <div className="card-grid">
        {loading ? (
          <>
            <SkeletonMetricCard />
            <SkeletonMetricCard />
            <SkeletonMetricCard />
            <SkeletonMetricCard />
          </>
        ) : (
          <>
            <MetricCard label="Total incidents" value={total} icon={ChartIcon} />
            <MetricCard label="Warning" value={warningCount} accent={LEVEL_COLOR.WARNING} icon={AlertTriangleIcon} />
            <MetricCard
              label="Critical"
              value={criticalCount}
              accent={LEVEL_COLOR.CRITICAL}
              icon={AlertTriangleIcon}
              priority={criticalCount > 0}
            />
            <MetricCard label="Cancel rate" value={`${cancelRate}%`} icon={PercentIcon} quiet />
          </>
        )}
      </div>
      <FusionTimeline
        incidents={incidents}
        displayLevel={liveLevel ?? mostRecent?.level}
        isLiveLevel={liveLevel != null}
      />
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
              {formatTimestamp(mostRecent.timestamp)}
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

// Nearest fire station — absorbs the former dedicated tab (2026-09-24):
// name, distance, phone, and the display-only emergency numbers. Cool-tint
// chrome marks it as reference data, not a hazard signal.
function FireStationCard({ station }) {
  const mapsUrl = station?.found
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(station.name)}`
    : null;
  return (
    <div className="panel glass glass--cool station-card">
      <h3 className="panel-title"><PinIcon />Nearest fire station</h3>
      {!station ? (
        <StateCard kind="empty">Looking up the nearest station…</StateCard>
      ) : station.found ? (
        <>
          <div className="station-name">{station.name}</div>
          <div className="station-stats">
            <div>
              <span className="metric-label">Distance</span>
              <div className="station-stat">
                <CountUp value={station.distance_km} decimals={1} />
                <span className="bullet-unit">km</span>
              </div>
            </div>
            <div>
              <span className="metric-label">Phone</span>
              <div className="station-stat station-stat--sm">
                {station.phone ? <a href={`tel:${station.phone}`}>{station.phone}</a> : "not listed"}
              </div>
            </div>
          </div>
          {mapsUrl && (
            <a className="station-link" href={mapsUrl} target="_blank" rel="noreferrer">
              Open in Maps ↗
            </a>
          )}
        </>
      ) : (
        <p className="metric-sub">{station.line}</p>
      )}
      {station && (
        <div className="station-numbers">
          <BellRingIcon width={13} height={13} />
          <span>Fire <b>{station.fire_number ?? "101"}</b></span>
          <span>Unified <b>{station.unified_number ?? "112"}</b></span>
          <span className="station-note">display only · never auto-dialed</span>
        </div>
      )}
    </div>
  );
}
