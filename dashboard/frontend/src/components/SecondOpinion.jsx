import LevelBadge from "./LevelBadge";
import StateCard from "./StateCard";
import { LEVEL_COLOR } from "../levels";
import { formatTimestamp } from "../formatTimestamp";

// Stage 6d (additiontoplan.md A.3): the cloud verdict NEXT TO the local one,
// with an explicit agree/disagree state. Disagreement is the signal.
//
// Data is the sidecar cloud/second_opinion.py writes, riding on the live
// payload as `second_opinion`. Agreement is computed by the writer, not
// here, so this component never re-implements a decision rule.
//
// Colours reuse levels.js (phase12.md step 9: no new palette): agreement
// wears SAFE's colour, disagreement WARNING's — "look at this", not
// "alarm". The cloud never raises the alarm, so it never gets CRITICAL red.

const AGREE_COLOR = LEVEL_COLOR.SAFE;
const DISAGREE_COLOR = LEVEL_COLOR.WARNING;

const pct = (p) => (p == null ? "—" : p.toFixed(2));

function visualLabel({ fire, smoke }) {
  if (fire && smoke) return "fire + smoke";
  if (fire) return "fire";
  if (smoke) return "smoke";
  return "no visible hazard";
}

// Why the two sides can disagree at all is documented in
// cloud/lambda_infer/handler.py: local votes over a temporal window, the
// cloud scores ONE frame. These lines say what each direction means.
function disagreementNote(entry) {
  if (entry.cloud.visual && !entry.local.visual) {
    return "Cloud sees a hazard in this frame that local's temporal voter had not confirmed — check the camera.";
  }
  return "Local's visual verdict rests on frames other than this one — check the camera.";
}

function Pill({ color, children }) {
  return (
    <span
      className="level-badge"
      style={{ background: `${color}22`, color, borderColor: `${color}55` }}
    >
      {children}
    </span>
  );
}

function Latest({ entry }) {
  if (!entry.ok) {
    return (
      <StateCard kind="error">
        no cloud opinion for the {formatTimestamp(entry.timestamp)} gas event — {entry.error}.
        Local detection was unaffected.
      </StateCard>
    );
  }
  const { local, cloud, agree } = entry;
  const crops = cloud.crops;
  return (
    <>
      <div className="opinion-row">
        <div className="opinion-side">
          <span className="metric-label">Local</span>
          <LevelBadge level={local.level} />
          <span className="opinion-detail">
            {visualLabel(local)} · p_fire {pct(local.p_fire)}
          </span>
        </div>
        <div className="opinion-side">
          <span className="metric-label">Cloud</span>
          <Pill color={agree ? AGREE_COLOR : DISAGREE_COLOR}>
            {agree ? "agrees" : "DISAGREES"}
          </Pill>
          <span className="opinion-detail">
            {visualLabel(cloud)} · p_fire {pct(cloud.p_fire)} · p_smoke {pct(cloud.p_smoke)}
          </span>
        </div>
      </div>

      {!agree && <p className="opinion-note">{disagreementNote(entry)}</p>}

      {crops && (
        <p className="opinion-crops">
          <span className="metric-label">5-crop detail</span> max {pct(crops.max_p_fire)} /
          mean {pct(crops.mean_p_fire)} (spread {pct(crops.spread)}), hottest{" "}
          {crops.hottest_region}. Diagnostic only; the verdict above is full-frame.
        </p>
      )}
      <p className="opinion-meta">
        {formatTimestamp(entry.timestamp)} · round trip {Math.round(entry.round_trip_ms)} ms
        {cloud.inference_ms != null && ` · inference ${Math.round(cloud.inference_ms)} ms`}
      </p>
    </>
  );
}

export default function SecondOpinion({ data }) {
  if (!data) {
    return <StateCard kind="empty">no second-opinion state yet — is edge/main.py running?</StateCard>;
  }
  if (!data.enabled) {
    return (
      <StateCard kind="empty">
        off. Set aws.second_opinion.enabled in config.yaml to ask the cloud on each gas event.
      </StateCard>
    );
  }
  const history = data.history ?? [];
  if (history.length === 0) {
    return (
      <StateCard kind="empty">
        armed. Asks once on the next GAS_HIGH ({data.calls}/{data.max_calls} calls used this
        session).
      </StateCard>
    );
  }
  const latest = history[history.length - 1];
  const earlier = history.slice(0, -1).reverse();
  return (
    <div className="second-opinion">
      <Latest entry={latest} />
      {earlier.length > 0 && (
        <ul className="opinion-history">
          {earlier.map((e) => (
            <li key={e.call}>
              <span>{formatTimestamp(e.timestamp)}</span>
              {e.ok ? (
                <Pill color={e.agree ? AGREE_COLOR : DISAGREE_COLOR}>
                  {e.agree ? "agreed" : "disagreed"}
                </Pill>
              ) : (
                <span className="opinion-detail">no opinion</span>
              )}
              {e.ok && (
                <span className="opinion-detail">
                  local {e.local.level} · cloud p_fire {pct(e.cloud.p_fire)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
