import { LEVEL_COLOR } from "../levels";
import { SENSORS, sensorThresholds, hazardIndex, hazardZone } from "../live";
import CountUp from "./CountUp";
import { PulseIcon } from "./icons";

// "Right now" panel: one bullet bar per sensor (reading marker on a
// baseline -> warn -> danger track) plus a 60 s p_fire sparkline. A single
// marker against its thresholds answers "how close are we?" faster than
// reading a line chart, which is why this sits beside the camera and the
// full history lives in GasChart below.

const ZONE_COLOR = { warn: LEVEL_COLOR.WARNING, danger: LEVEL_COLOR.CRITICAL };
const SPARK_SAMPLES = 60;

function headroomText(v, t) {
  if (v >= t.danger) return `${Math.round(v - t.danger)} above danger`;
  if (v >= t.warn) return `${Math.round(t.danger - v)} to danger`;
  return `${Math.round(t.warn - v)} to warn`;
}

function Bullet({ sensor, sample, offline }) {
  const v = sample?.[sensor.key];
  const t = sensorThresholds(sample, sensor.key);
  const idx = hazardIndex(v, t);
  const zone = hazardZone(idx);
  const color = ZONE_COLOR[zone] ?? sensor.color;
  const hasValue = typeof v === "number" && !offline;

  let pos = null;
  let seg = null;
  if (t) {
    const lo = Math.max(0, t.baseline - (t.warn - t.baseline) * 0.5);
    const hi = Math.max(t.danger + (t.danger - t.warn) * 0.8, hasValue ? v * 1.06 : 0);
    const pct = (x) => `${((Math.min(Math.max(x, lo), hi) - lo) / (hi - lo)) * 100}%`;
    seg = { baseline: pct(t.baseline), warn: pct(t.warn), danger: pct(t.danger) };
    if (hasValue) pos = pct(v);
  }

  return (
    <div className={`bullet${zone === "danger" ? " bullet--danger" : ""}`}>
      <div className="bullet-head">
        <div>
          <span className="bullet-name" style={{ color: sensor.color }}>{sensor.label}</span>
          <span className="bullet-gas">{sensor.gas}</span>
        </div>
        <div className="bullet-value" style={{ color: hasValue ? color : "var(--text-dim)" }}>
          {hasValue ? <CountUp value={v} /> : "—"}
          <span className="bullet-unit">adc</span>
        </div>
      </div>
      <div className={`bullet-track${t ? "" : " bullet-track--pending"}`}>
        {seg && (
          <>
            <span className="bullet-zone bullet-zone--warn" style={{ left: seg.warn, width: `calc(${seg.danger} - ${seg.warn})` }} />
            <span className="bullet-zone bullet-zone--danger" style={{ left: seg.danger, right: 0 }} />
            <span className="bullet-tick" style={{ left: seg.baseline }} />
          </>
        )}
        {pos && <span className="bullet-marker" style={{ left: pos, "--marker-color": color }} />}
      </div>
      <div className="bullet-foot">
        {t ? (
          <>
            <span>base {Math.round(t.baseline)} · warn {Math.round(t.warn)} · danger {Math.round(t.danger)}</span>
            {hasValue && (
              <span style={{ color: zone === "normal" ? "var(--text-dim)" : color }}>
                {headroomText(v, t)} · idx {idx.toFixed(2)}
              </span>
            )}
          </>
        ) : (
          <span>{offline ? "sensor feed offline" : "thresholds pending — board has no baseline yet"}</span>
        )}
      </div>
    </div>
  );
}

function PFireSpark({ readings, offline }) {
  const recent = readings.slice(-SPARK_SAMPLES).map((r) => r.p_fire ?? 0);
  const latest = recent.length && !offline ? recent[recent.length - 1] : null;
  const peak = recent.length ? Math.max(...recent) : null;
  const W = 240;
  const H = 80;
  const step = recent.length > 1 ? W / (SPARK_SAMPLES - 1) : 0;
  const x0 = W - (recent.length - 1) * step;
  const pts = recent.map((p, i) => [x0 + i * step, H - p * (H - 4) - 2]);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
  const area = pts.length ? `${line}L${W},${H}L${x0},${H}Z` : "";

  return (
    <div className="spark">
      <div className="bullet-head">
        <div>
          <span className="bullet-name" style={{ color: "var(--accent)" }}>
            <PulseIcon width={13} height={13} style={{ verticalAlign: -2, marginRight: 6 }} />
            p_fire
          </span>
          <span className="bullet-gas">vision model · last {SPARK_SAMPLES}s</span>
        </div>
        <div className="bullet-value" style={{ color: latest != null ? "var(--text)" : "var(--text-dim)" }}>
          {latest != null ? <CountUp value={latest} decimals={2} /> : "—"}
        </div>
      </div>
      <svg className="spark-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#f59e0b" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Quarter gridlines: the scale is fixed 0-1, so a quiet feed sits
            low on purpose — the lines make that read as scale, not a gap. */}
        {[0.25, 0.5, 0.75].map((g) => (
          <line key={g} x1="0" x2={W} y1={H - g * (H - 4) - 2} y2={H - g * (H - 4) - 2}
            stroke="rgba(214,180,154,0.12)" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" />
        ))}
        {area && <path d={area} fill="url(#spark-fill)" />}
        {line && <path d={line} fill="none" stroke="#f59e0b" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />}
        {pts.length > 0 && <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.6" fill="#f6f1ee" />}
      </svg>
      <div className="bullet-foot">
        <span>peak {peak != null ? peak.toFixed(2) : "—"}</span>
        <span>0 – 1 scale</span>
      </div>
    </div>
  );
}

export default function LiveReadout({ liveSensors, sample, offline }) {
  const readings = liveSensors?.ok ? liveSensors.readings ?? [] : [];
  return (
    <div className="panel glass glass--dense readout">
      <h3 className="panel-title">Right now</h3>
      {SENSORS.map((s) => (
        <Bullet key={s.key} sensor={s} sample={sample} offline={offline} />
      ))}
      <PFireSpark readings={readings} offline={offline} />
    </div>
  );
}
