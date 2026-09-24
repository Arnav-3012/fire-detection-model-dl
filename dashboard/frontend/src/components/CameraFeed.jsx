import { useEffect, useRef, useState } from "react";
import { backendUrl } from "../api";
import { LEVEL_COLOR } from "../levels";
import LevelBadge from "./LevelBadge";
import CountUp from "./CountUp";
import { CameraIcon, ExpandIcon } from "./icons";

// Home-page camera (2026-09-24, replaces the Live View tab's bare <img>).
//
// Always served from the backend RELAY (/api/camera/stream), never the
// board: cam_node.ino serves one client, and the relay fans that single
// connection out to every viewer and the edge loop.
//
// Liveness comes from the payload's `camera` block (relay stats), not the
// <img>: an MJPEG image whose upstream died just freezes on its last frame
// and looks perfectly live. The stream is dropped while the browser tab is
// hidden so an idle dashboard is not pulling ~8 fps of JPEGs.

const RETRY_MS = 5000;

function usePageVisible() {
  const [visible, setVisible] = useState(() => document.visibilityState !== "hidden");
  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);
  return visible;
}

export default function CameraFeed({ camera, level, pFire, now }) {
  const frameRef = useRef(null);
  const visible = usePageVisible();
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);

  const configured = camera?.configured !== false;
  const live = Boolean(camera?.live);

  // Retry a failed stream on a timer, and immediately when the relay
  // reports frames flowing again.
  useEffect(() => {
    if (!failed) return;
    const id = setTimeout(() => {
      setFailed(false);
      setAttempt((a) => a + 1);
    }, live ? 0 : RETRY_MS);
    return () => clearTimeout(id);
  }, [failed, live]);

  const alarm = level === "WARNING" || level === "CRITICAL";
  const status = !configured ? "unconfigured" : failed ? "offline" : live ? "live" : camera ? "stale" : "connecting";
  const statusText = {
    live: "LIVE",
    stale: camera?.age_seconds != null ? `SIGNAL LOST · ${Math.round(camera.age_seconds)}s` : "NO SIGNAL",
    offline: "RECONNECTING",
    connecting: "CONNECTING",
    unconfigured: "NOT CONFIGURED",
  }[status];

  return (
    <div
      ref={frameRef}
      className={`glass camera${alarm ? " camera--alarm" : ""}`}
      style={alarm ? { "--alarm-color": LEVEL_COLOR[level] } : undefined}
    >
      <div className="camera-stage">
        {configured && visible && !failed && (
          <img
            key={attempt}
            className="camera-img"
            src={backendUrl(`/api/camera/stream?a=${attempt}`)}
            alt="Live ESP32-CAM view of the monitored area"
            onError={() => setFailed(true)}
          />
        )}
        {status !== "live" && (
          <div className={`camera-veil${status === "stale" ? " camera-veil--stale" : ""}`}>
            <CameraIcon width={30} height={30} />
            <span>
              {status === "unconfigured"
                ? "Camera not configured — set camera.stream_url in config.yaml"
                : status === "stale"
                  ? "Camera signal lost — showing the last frame received"
                  : "Waiting for the camera relay…"}
            </span>
          </div>
        )}

        <div className="camera-overlay camera-overlay--top">
          <span className={`camera-live camera-live--${status}`}>
            <span className="camera-live-dot" />
            {statusText}
          </span>
          {level && <LevelBadge level={level} pulse />}
        </div>

        <div className="camera-overlay camera-overlay--bottom">
          <div className="camera-meter">
            <span className="camera-meter-label">p_fire</span>
            <span className="camera-meter-track">
              <span
                className="camera-meter-fill"
                style={{ width: `${Math.round((pFire ?? 0) * 100)}%` }}
              />
            </span>
            <span className="camera-meter-value">
              {pFire != null ? <CountUp value={pFire} decimals={2} /> : "—"}
            </span>
          </div>
          <span className="camera-clock">{new Date(now).toLocaleTimeString()}</span>
          <button
            type="button"
            className="camera-btn"
            aria-label="Toggle fullscreen camera"
            onClick={() =>
              document.fullscreenElement
                ? document.exitFullscreen()
                : frameRef.current?.requestFullscreen?.()
            }
          >
            <ExpandIcon width={16} height={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
