const BASE = "http://127.0.0.1:8001";

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
