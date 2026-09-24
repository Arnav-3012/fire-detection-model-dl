import LiveSensorChart from "../components/LiveSensorChart";
import StateCard from "../components/StateCard";
import SecondOpinion from "../components/SecondOpinion";
import Reveal from "../components/Reveal";
import { ChartIcon } from "../components/icons";
import { backendUrl } from "../api";

// Stage 5 (2026-09-23): the live tab — gas chart and camera side by side,
// both fed by the WiFi paths built in Stages 3-4.
//
// The chart reuses LiveSensorChart unchanged: the WebSocket payload is
// identical to GET /api/live-sensors, which is exactly why no change was
// needed there.
//
// The camera <img> points at the RELAY (/api/camera/stream), never at the
// board directly. cam_node.ino serves ONE client at a time, so a direct
// <img src="http://<cam-ip>/stream"> here would take the board's only slot
// and lock out the edge loop — the precise failure Stage 4 exists to
// prevent. Every viewer of this tab is served from the relay's slot, so
// any number of open tabs still cost the board one connection.

// Matches Overview.jsx's convention so "offline" means the same thing on
// every tab.
const LIVE_STALE_MS = 12_000;

function isStale(readings) {
  if (!readings || readings.length === 0) return true;
  const latest = readings[readings.length - 1];
  if (!latest?.timestamp) return true;
  // Unix SECONDS (edge/livelog.py), hence * 1000 — without it every sample
  // parsed as January 1970 and this tab always read "sensor offline".
  return Date.now() - latest.timestamp * 1000 > LIVE_STALE_MS;
}

export default function LiveView({ liveSensors, error, loading }) {
  const readings = liveSensors?.ok ? liveSensors.readings ?? [] : [];
  const offline = isStale(readings);
  const latest = readings[readings.length - 1];

  return (
    <div className="live-view">
      <Reveal className="panel glass chart-panel">
        <div className="chart-panel-header">
          <h3 className="panel-title">
            <ChartIcon />Live gas readings
            {offline ? (
              <span className="panel-title-subtitle"> — sensor offline</span>
            ) : (
              <span className="panel-title-subtitle"> — streaming</span>
            )}
          </h3>
          {latest && !offline && (
            <div className="chart-panel-stat">
              <span className="metric-label">mq2</span> {latest.mq2 ?? "—"}
              {"  "}
              <span className="metric-label">mq135</span> {latest.mq135 ?? "—"}
            </div>
          )}
        </div>

        {loading && !liveSensors ? (
          <StateCard kind="empty">connecting to the live feed…</StateCard>
        ) : error ? (
          <StateCard kind="error">{error}</StateCard>
        ) : readings.length === 0 ? (
          <StateCard kind="empty">
            no live data yet — is edge/main.py running?
          </StateCard>
        ) : (
          <LiveSensorChart liveSensors={liveSensors} />
        )}
      </Reveal>

      <Reveal className="panel glass chart-panel">
        <div className="chart-panel-header">
          <h3 className="panel-title">Live camera</h3>
        </div>
        {/* Served by the Stage 4 relay, so this tab and the edge loop can
            both see the camera. A plain <img> is all an MJPEG stream
            needs — the browser handles multipart/x-mixed-replace natively.
            onError swaps in a message rather than leaving a broken-image
            icon when the camera is unconfigured or unreachable. */}
        <img
          className="live-camera"
          src={backendUrl("/api/camera/stream")}
          alt="live camera stream"
          onError={(e) => {
            e.currentTarget.style.display = "none";
            const note = e.currentTarget.nextElementSibling;
            if (note) note.style.display = "flex";
          }}
        />
        <div style={{ display: "none" }}>
          <StateCard kind="error">
            camera unavailable — check camera.stream_url in config.yaml and
            that the board is on this network
          </StateCard>
        </div>
      </Reveal>

      {/* Stage 6d. Spans both columns: it compares what the chart's gas
          event triggered against what the camera frame shows. */}
      <Reveal className="panel glass chart-panel second-opinion-panel">
        <div className="chart-panel-header">
          <h3 className="panel-title">
            Cloud second opinion
            <span className="panel-title-subtitle"> — advisory, never gates the alarm</span>
          </h3>
        </div>
        <SecondOpinion data={liveSensors?.second_opinion} />
      </Reveal>
    </div>
  );
}
