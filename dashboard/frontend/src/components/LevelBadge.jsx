import { LEVEL_COLOR } from "../levels";
import { AlertTriangleIcon, BellRingIcon } from "./icons";

// CRITICAL and WARNING carry an icon alongside color + text label so the
// "pay attention now" signal isn't color/animation-only — a colorblind
// user or anyone glancing past the pulse still gets a distinct glyph, not
// just a hue difference between adjacent amber/red badges.
const LEVEL_ICON = {
  WARNING: BellRingIcon,
  CRITICAL: AlertTriangleIcon,
};

export default function LevelBadge({ level, pulse = false }) {
  const color = LEVEL_COLOR[level] ?? "#6b7280";
  const critical = pulse && level === "CRITICAL";
  const Icon = LEVEL_ICON[level];
  return (
    <span
      className={`level-badge${critical ? " level-badge--critical" : ""}`}
      style={{
        background: `${color}22`,
        color,
        borderColor: `${color}55`,
        boxShadow: critical ? `0 0 0 1px ${color}55` : undefined,
      }}
    >
      {Icon && <Icon width={12} height={12} style={{ marginRight: 5, verticalAlign: -1.5 }} />}
      {level}
    </span>
  );
}
