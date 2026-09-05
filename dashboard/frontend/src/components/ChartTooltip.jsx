import { useLayoutEffect, useRef, useState } from "react";

// Structured glass-style hover tooltip for Plotly charts — replaces
// Plotly's plain browser-style default tooltip (hoverinfo stays "none" or
// "skip" on the traces themselves; this renders instead, driven by the
// chart's onHover/onUnhover events). `left`/`top` are the raw cursor
// position pre-computed by the caller (relative to its own chart
// container) — this component then clamps its own rendered box so it
// never renders outside that container, flipping below the cursor when
// there isn't room above (bug fix 2026-09-04: a point near a container's
// top-left corner, e.g. the earliest CRITICAL event on the fusion
// timeline, previously pushed the tooltip up and left past the container
// edge entirely, covering the row labels instead of sitting near the
// point it describes).
const GAP = 14;

export default function ChartTooltip({ point, containerRef }) {
  const tooltipRef = useRef(null);
  const [style, setStyle] = useState(null);

  useLayoutEffect(() => {
    if (!point || !tooltipRef.current) {
      setStyle(null);
      return;
    }
    const tip = tooltipRef.current.getBoundingClientRect();
    const bounds = containerRef?.current?.getBoundingClientRect();
    const containerWidth = bounds?.width ?? Infinity;
    const containerHeight = bounds?.height ?? Infinity;

    // Default: centered above the point. Flip below if there isn't
    // room above; clamp horizontally so the box never crosses either
    // edge of the container.
    let top = point.top - tip.height - GAP;
    let flipped = false;
    if (top < 0) {
      top = point.top + GAP;
      flipped = true;
    }
    top = Math.min(top, Math.max(0, containerHeight - tip.height));

    let left = point.left - tip.width / 2;
    left = Math.max(0, Math.min(left, containerWidth - tip.width));

    setStyle({ left, top, arrowOffset: point.left - left, flipped });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [point?.left, point?.top]);

  if (!point) return null;

  return (
    <div
      ref={tooltipRef}
      className={`chart-tooltip glass${style?.flipped ? " chart-tooltip--below" : ""}`}
      style={style ? { left: style.left, top: style.top } : { left: point.left, top: point.top, visibility: "hidden" }}
    >
      {point.title && <div className="chart-tooltip-title">{point.title}</div>}
      <dl className="chart-tooltip-rows">
        {point.rows.map(([label, value]) => (
          <div key={label} className="chart-tooltip-row">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
