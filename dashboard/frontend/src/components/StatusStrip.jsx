import { LEVEL_COLOR } from "../levels";
import { BOARD_STATE, formatAge, sampleAgeMs } from "../live";
import { FlameIcon } from "./icons";

// Sticky system-status strip, the first thing on the home page: the live
// fused level plus the four things that decide whether to trust it (board,
// camera, edge feed freshness, threshold source). At WARNING/CRITICAL the
// whole strip takes the level colour — the page's loudest signal is the
// one that matters.

const LEVEL_TEXT = {
  SAFE: "All clear",
  WATCH: "Watching — single signal",
  WARNING: "Warning — investigate now",
  CRITICAL: "Critical — fire likely",
};

const THRESHOLD_TEXT = { firmware: "live", pending: "pending", none: "none" };
const THRESHOLD_TONE = { firmware: "ok", pending: "pending", none: "trouble" };

function Item({ label, value, tone }) {
  return (
    <div className="strip-item">
      <span className="strip-label">{label}</span>
      <span className={`strip-value strip-value--${tone}`}>
        <span className="strip-dot" />
        {value}
      </span>
    </div>
  );
}

export default function StatusStrip({ sample, offline, liveSensors, lastIncident, now }) {
  const level = offline ? null : sample?.level;
  const color = level ? LEVEL_COLOR[level] : "#6b7280";
  const alarm = level === "WARNING" || level === "CRITICAL";
  const board = BOARD_STATE[sample?.state];
  const camera = liveSensors?.camera;
  const cameraTone = !camera || camera.configured === false ? "trouble" : camera.live ? "ok" : "alarm";
  const cameraText = !camera ? "—" : camera.configured === false ? "not set" : camera.live ? "live" : "no signal";
  const source = liveSensors?.threshold_source ?? "none";

  return (
    <div
      className={`glass strip${alarm ? " strip--alarm" : ""}${level === "CRITICAL" ? " strip--critical" : ""}`}
      style={{ "--level-color": color }}
      role="status"
      aria-live="polite"
    >
      <div className="strip-level">
        <FlameIcon width={22} height={22} style={{ color, flexShrink: 0 }} />
        <div>
          <div className="strip-level-name" style={{ color }}>{level ?? "OFFLINE"}</div>
          <div className="strip-level-text">
            {level ? LEVEL_TEXT[level] : "No live feed — is edge/main.py running?"}
          </div>
        </div>
      </div>
      <div className="strip-items">
        <Item
          label="Edge feed"
          value={offline ? `offline · ${formatAge(sampleAgeMs(sample, now))}` : formatAge(sampleAgeMs(sample, now))}
          tone={offline ? "alarm" : "ok"}
        />
        <Item
          label="Sensor board"
          value={offline ? "—" : board?.label ?? (sample?.state ?? "no state")}
          tone={offline ? "trouble" : board?.tone ?? "trouble"}
        />
        <Item label="Camera" value={cameraText} tone={cameraTone} />
        <Item label="Thresholds" value={THRESHOLD_TEXT[source]} tone={THRESHOLD_TONE[source]} />
        <Item
          label="Last incident"
          value={lastIncident ? formatAge(now - new Date(lastIncident.timestamp).getTime()) : "none"}
          tone={lastIncident ? "neutral" : "ok"}
        />
      </div>
    </div>
  );
}
