// Shimmer skeleton shown in place of a card's real content while its
// first fetch is in flight (usePolling's `loading` flag) — replaces a
// blank flash / sudden pop-in with a tasteful placeholder that already
// hints at the shape of what's coming.
export function SkeletonMetricCard() {
  return (
    <div className="glass metric-card">
      <div className="skeleton skeleton-line" style={{ width: "50%", height: 10 }} />
      <div className="skeleton skeleton-metric-value" />
    </div>
  );
}

export function SkeletonPanel({ height = 220 }) {
  return (
    <div className="panel glass">
      <div className="skeleton skeleton-line" style={{ width: "40%", height: 14, marginBottom: 16 }} />
      <div className="skeleton skeleton-block" style={{ height }} />
    </div>
  );
}
