export const BASE = "http://127.0.0.1:8001";

// WebSocket origin derived from BASE, so the backend address stays defined
// in exactly one place (Stage 5). http -> ws, https -> wss.
export const WS_BASE = BASE.replace(/^http/, "ws");

// Absolute URL for a backend resource referenced by the browser directly
// (e.g. an <img src>), which cannot use the fetch helper below.
export const backendUrl = (path) => `${BASE}${path}`;

async function getJson(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

export const fetchIncidents = () => getJson("/api/incidents");
export const fetchS3Archive = () => getJson("/api/s3-archive");
export const fetchTrials = () => getJson("/api/trials");
export const fetchFireStation = () => getJson("/api/fire-station");
export const fetchLiveSensors = () => getJson("/api/live-sensors");
