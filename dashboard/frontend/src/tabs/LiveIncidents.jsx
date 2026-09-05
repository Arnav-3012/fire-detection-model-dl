import { useMemo, useState } from "react";
import LevelBadge from "../components/LevelBadge";
import StateCard from "../components/StateCard";
import Reveal from "../components/Reveal";
import { SkeletonPanel } from "../components/Skeleton";
import { LEVEL_COLOR } from "../levels";

// Blog/feed-style presentation (design brief) — one card per incident,
// headline summary up front, full raw row on expand. Replaces the prior
// data-table view; filters carry over unchanged.
export default function LiveIncidents({ incidents, loading }) {
  const [levelFilter, setLevelFilter] = useState("ALL");
  const [outcomeFilter, setOutcomeFilter] = useState("ALL");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [expanded, setExpanded] = useState(null);

  const filtered = useMemo(() => {
    return incidents
      .filter((row) => {
        if (levelFilter !== "ALL" && row.level !== levelFilter) return false;
        if (outcomeFilter !== "ALL" && row.outcome !== outcomeFilter) return false;
        if (from && row.timestamp < from) return false;
        if (to && row.timestamp > to) return false;
        return true;
      })
      .slice()
      .reverse(); // most recent first, feed-style
  }, [incidents, levelFilter, outcomeFilter, from, to]);

  const outcomes = useMemo(
    () => [...new Set(incidents.map((r) => r.outcome).filter(Boolean))],
    [incidents]
  );

  if (loading) {
    return (
      <div className="tab-content">
        <SkeletonPanel height={90} />
        <SkeletonPanel height={140} />
        <SkeletonPanel height={140} />
      </div>
    );
  }

  return (
    <div className="tab-content">
      <div className="filters">
        <select value={levelFilter} onChange={(e) => setLevelFilter(e.target.value)}>
          <option value="ALL">All levels</option>
          {Object.keys(LEVEL_COLOR).map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <select value={outcomeFilter} onChange={(e) => setOutcomeFilter(e.target.value)}>
          <option value="ALL">All outcomes</option>
          {outcomes.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
        <input type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} />
        <span className="filter-sep">to</span>
        <input type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>

      {filtered.length === 0 ? (
        <div className="state-card-wrap">
          <StateCard kind="empty">No incidents match these filters.</StateCard>
        </div>
      ) : (
        <div className="incident-feed">
          {filtered.map((row, idx) => {
            const key = row.event_id ?? idx;
            const isOpen = expanded === key;
            const color = LEVEL_COLOR[row.level] ?? "#6b7280";
            return (
              <Reveal key={key} delay={Math.min(idx, 6) * 40}>
                <div
                  className="glass incident-card"
                  style={{ boxShadow: isOpen ? `0 0 0 1px ${color}55` : undefined }}
                  role="button"
                  tabIndex={0}
                  aria-expanded={isOpen}
                  onClick={() => setExpanded(isOpen ? null : key)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setExpanded(isOpen ? null : key);
                    }
                  }}
                >
                  <div className="incident-card__head">
                    <LevelBadge level={row.level} pulse />
                    <strong>{row.level === "CRITICAL" ? "Critical hazard event" : row.level === "WARNING" ? "Warning-level event" : `${row.level} event`}</strong>
                    {row.outcome && <OutcomePill outcome={row.outcome} />}
                    <span className="incident-card__time">{row.timestamp}</span>
                  </div>
                  <p className="incident-card__summary">
                    {summarize(row)}
                  </p>
                  <div className="incident-card__meta">
                    <span>p_fire {row.p_fire}</span>
                    <span>gas_high {row.gas_high}</span>
                  </div>
                  {isOpen && (
                    <div className="incident-card__expand">
                      <pre>{JSON.stringify(row, null, 2)}</pre>
                    </div>
                  )}
                </div>
              </Reveal>
            );
          })}
        </div>
      )}
    </div>
  );
}

function OutcomePill({ outcome }) {
  const variant =
    outcome === "CANCELLED" ? "positive" : outcome === "TIMEOUT" ? "negative" : "neutral";
  return <span className={`status-pill status-pill--${variant}`}>{outcome}</span>;
}

function summarize(row) {
  const parts = [];
  if (row.gas_high === "True" || row.gas_high === true) parts.push("gas-corroborated");
  if (row.outcome) parts.push(`resolved: ${row.outcome.toLowerCase()}`);
  const tail = parts.length ? ` — ${parts.join(", ")}.` : ".";
  return `Fusion reported ${row.level} at p_fire=${row.p_fire}${tail}`;
}
