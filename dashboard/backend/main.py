"""Phase 11: read-only FastAPI data layer for the React dashboard.

Deliberately thin (developer instruction, 2026-09-03): every endpoint here
reads an existing file/S3 bucket/module and reshapes it to JSON. No fusion,
no decision logic, no writes — that all already lives in edge/ and agent/.
This process is a second, independent FastAPI app from agent/server.py
(which accepts incidents); it never imports or calls into that app.

Run from the repo root:  uvicorn dashboard.backend.main:app --port 8001
"""

import asyncio
import csv
import json
import logging
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from agent.locate import find_nearest_fire_station
from cloud.second_opinion import sidecar_path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("firewatch.dashboard")

# Everything this app reads is anchored to the repo root via __file__, never
# the cwd. Root cause of the 2026-09-03 "Unable to locate credentials" bug:
# this file never called load_dotenv() at all — the agent modules that
# proved AWS_* working (compose/tools/escalate) each load .env themselves at
# import, and none of them is imported here, so boto3 saw no credentials.
# The explicit path also makes the load cwd-independent (bare load_dotenv()
# searches from the cwd, which is only right when launched from the root).
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")

app = FastAPI(title="FireWatch dashboard API")

with open(_REPO_ROOT / "config.yaml") as f:
    _CONFIG = yaml.safe_load(f)

# React dev server origins (Vite default 5173, CRA default 3000) — this API
# has no auth and is read-only, so the origin list only needs to cover local
# dev, per the developer's brief.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# --- Stage 4 camera relay ---------------------------------------------
# cam_node.ino's /stream serves exactly ONE client (its own source comment
# says so), so the edge loop holding it locks the dashboard out of the
# camera entirely. The relay holds that single upstream connection and
# fans the newest frame out to every consumer.
#
# It runs HERE, in the backend, rather than in the edge loop, so Live View
# works even when edge/main.py is stopped -- a dashboard that goes blank
# whenever the detector restarts is not much of a dashboard. The edge loop
# keeps opening the stream directly today; that is unchanged by this stage
# and remains the detector's own business.
sys.path.insert(0, str(_REPO_ROOT / "edge"))
from camrelay import CameraRelay  # noqa: E402  (path must be set first)

_CAM_URL = _CONFIG.get("camera", {}).get("stream_url", "")
_relay: CameraRelay | None = None


@app.on_event("startup")
def _start_relay() -> None:
    """Start relaying if a camera URL is configured. Never fatal: a
    missing/unreachable camera degrades Live View, it must not stop the
    rest of the dashboard API from serving."""
    global _relay
    if not _CAM_URL:
        logger.info("no camera.stream_url configured — camera endpoints disabled")
        return
    _relay = CameraRelay(_CAM_URL)
    _relay.start()
    logger.info("camera relay started against %s", _CAM_URL)


@app.on_event("shutdown")
def _stop_relay() -> None:
    if _relay is not None:
        _relay.stop()


# Matches the board's own 1 Hz sample rate — pushing faster would only
# resend identical data.
WS_PUSH_INTERVAL_SECONDS = 1.0

_FEEDBACK_CSV = _REPO_ROOT / _CONFIG["agent"]["feedback_log"]
_RESULTS_CSV = _REPO_ROOT / "eval/results.csv"
_LIVE_LOG_PATH = _REPO_ROOT / _CONFIG["live_log"]["path"]
_SECOND_OPINION_PATH = sidecar_path(_LIVE_LOG_PATH)

# Cached across requests: the underlying coordinates are hardcoded
# (config.yaml location.*, plan.md section 1) and don't change between
# polls, so re-querying Overpass every tab-focus would be pure waste.
# SUCCESSFUL results only — see fire_station() for why.
_fire_station_cache: dict[str, Any] | None = None


@app.get("/api/incidents")
def incidents() -> list[dict[str, Any]]:
    """eval/alert_feedback.csv, as JSON — one row per past alert."""
    if not _FEEDBACK_CSV.exists():
        return []
    with open(_FEEDBACK_CSV, newline="") as f:
        return list(csv.DictReader(f))


@app.get("/api/s3-archive")
def s3_archive() -> dict[str, Any]:
    """CRITICAL incident JSON objects from S3, across every device_XX/ prefix.

    Not hardcoded to device_01/ (developer instruction) so the same endpoint
    keeps working if a second device prefix is ever added (context.md's
    Phase 11 fleet-monitoring note). Graceful error response, not a 500, if
    S3 is unreachable or misconfigured (info.md 3.2) — the dashboard must
    show a clear "could not load" state rather than break.
    """
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    aws_cfg = _CONFIG["aws"]
    try:
        s3 = boto3.client("s3", region_name=aws_cfg.get("region"))
        paginator = s3.get_paginator("list_objects_v2")
        incidents_by_device: dict[str, list[dict[str, Any]]] = {}
        for page in paginator.paginate(Bucket=aws_cfg["s3_bucket"]):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".json"):
                    continue
                device = key.split("/", 1)[0]
                body = s3.get_object(Bucket=aws_cfg["s3_bucket"], Key=key)["Body"].read()
                incident = json.loads(body)
                incident["_s3_key"] = key
                incidents_by_device.setdefault(device, []).append(incident)
        return {"ok": True, "devices": incidents_by_device}
    except (BotoCoreError, ClientError, KeyError) as exc:
        logger.warning("S3 archive read failed: %s", exc)
        return {"ok": False, "error": str(exc), "devices": {}}


@app.get("/api/trials")
def trials() -> dict[str, Any]:
    """eval/results.csv (Day 11 evaluation trials), or an explicit not-found
    response — trials not having started yet is expected, not an error."""
    if not _RESULTS_CSV.exists():
        return {"ok": False, "reason": "no trial data yet", "rows": []}
    with open(_RESULTS_CSV, newline="") as f:
        return {"ok": True, "reason": None, "rows": list(csv.DictReader(f))}


@app.get("/api/fire-station")
def fire_station() -> dict[str, Any]:
    """Cached nearest-fire-station lookup, reusing agent/locate.py's existing
    Overpass + 101/112 fallback logic verbatim (no reimplementation)."""
    global _fire_station_cache
    if _fire_station_cache is not None:
        return _fire_station_cache

    loc = _CONFIG["location"]
    agent_cfg = _CONFIG["agent"]
    fallback = _CONFIG["emergency_fallback"]
    result = find_nearest_fire_station(
        lat=loc["latitude"],
        lon=loc["longitude"],
        radius_m=agent_cfg["overpass_radius_m"],
        url=agent_cfg["overpass_url"],
        timeout=agent_cfg["overpass_timeout_seconds"],
        fallback_fire_number=fallback["fire_number"],
        fallback_unified_number=fallback["unified_number"],
    )
    result["fire_number"] = fallback["fire_number"]
    result["unified_number"] = fallback["unified_number"]
    # Root cause of the 2026-09-03 "could not be determined" bug: this cache
    # used to store the FIRST result unconditionally, so one transient
    # Overpass failure (the exact intermittent class agent/locate.py's
    # 2026-09-02 retry fix documents) stuck as "could not be determined" for
    # the life of the process. Cache only genuine finds; a fallback result
    # is returned but NOT cached, so the next poll retries.
    if result.get("found"):
        _fire_station_cache = result
    return result


def _live_sensors_payload() -> dict[str, Any]:
    """The live-sensors payload, shared by the REST endpoint and the
    WebSocket below.

    One builder, deliberately: Stage 5's whole premise is that the WS
    payload is IDENTICAL to /api/live-sensors, so LiveSensorChart.jsx
    drops in unchanged and falling back to polling is a one-line change.
    Two separate builders would drift the first time either changed.

    Thresholds prefer the FIRMWARE-published values the board now sends
    (Stage 3) over config.yaml's, which are stale August 10-bit
    Arduino-era numbers — see config.yaml's sensors block. Falls back to
    config when the board has not published any yet (still warming up,
    or legacy firmware).
    """
    sensors_cfg = _CONFIG["sensors"]
    thresholds = {
        k: sensors_cfg[k]
        for k in (
            "mq2_baseline", "mq2_warn", "mq2_danger",
            "mq135_baseline", "mq135_warn", "mq135_danger",
        )
    }
    # The firmware names its fields warn_mq2 / baseline_mq135 / ...,
    # while the dashboard's contract (and config.yaml) uses mq2_warn /
    # mq135_baseline / ... . Mapping is REQUIRED, not cosmetic: merging
    # the raw firmware dict would ADD six new keys while leaving the six
    # stale config keys in place, and the chart — which reads the config
    # names — would keep drawing the stale lines while looking updated.
    live = _read_firmware_thresholds()
    for sensor in ("mq2", "mq135"):
        for field in ("baseline", "warn", "danger"):
            firmware_key = f"{field}_{sensor}"
            config_key = f"{sensor}_{field}"
            if firmware_key in live:
                thresholds[config_key] = live[firmware_key]

    second_opinion = _read_second_opinion()
    if not _LIVE_LOG_PATH.exists():
        return {"ok": False, "reason": "no live data yet — is edge/main.py running?",
                "readings": [], "thresholds": thresholds, "second_opinion": second_opinion}
    try:
        readings = json.loads(_LIVE_LOG_PATH.read_text())
    except (OSError, ValueError) as exc:
        logger.warning("live-sensors read failed: %s", exc)
        return {"ok": False, "reason": str(exc), "readings": [], "thresholds": thresholds,
                "second_opinion": second_opinion}
    return {"ok": True, "reason": None, "readings": readings, "thresholds": thresholds,
            "second_opinion": second_opinion}


def _read_second_opinion() -> dict[str, Any] | None:
    """Stage 6d: the cloud second-opinion sidecar cloud/second_opinion.py
    writes, verbatim. None when the edge loop has never written one.

    Rides on the live payload rather than its own endpoint so Live View
    gets it over the socket it already holds -- and so REST and WS stay
    byte-identical, which is Stage 5's contract. An additive key: the
    chart ignores it.
    """
    if not _SECOND_OPINION_PATH.exists():
        return None
    try:
        return json.loads(_SECOND_OPINION_PATH.read_text())
    except (OSError, ValueError):
        return None


def _read_firmware_thresholds() -> dict[str, float]:
    """The six live thresholds the board publishes, if the edge loop has
    written them. Empty when unavailable — callers fall back to config.

    Read from the live-log sidecar rather than reaching into the edge
    loop: this backend is a separate process and must stay decoupled
    from it (it may not even be running).
    """
    path = _LIVE_LOG_PATH.with_name(_LIVE_LOG_PATH.stem + "_thresholds.json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}


@app.get("/api/live-sensors")
def live_sensors() -> dict[str, Any]:
    """The 1 Hz rolling live-readings buffer edge/main.py maintains
    (edge/livelog.py), plus the calibrated gas thresholds — bundled here so
    the frontend can draw threshold lines without a second config endpoint.

    The file is replaced atomically by the writer, so a read here never sees
    a partial JSON document. Missing file = edge loop not running (or not
    yet sampling): an expected state, not an error.
    """
    return _live_sensors_payload()


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    """Push the live-sensors payload at 1 Hz.

    Payload is byte-identical to GET /api/live-sensors (both call
    _live_sensors_payload), so the frontend chart component is unchanged
    and falling back to polling is a one-line swap.

    1 Hz because that is the rate the data actually changes — the board
    samples once per second (sensor_esp32_node.ino SAMPLE_INTERVAL_MS),
    so pushing faster would send duplicate frames.

    Sends immediately on connect rather than waiting a full second: a
    freshly-opened tab should draw at once, not sit blank.

    CORS note: the WebSocket handshake bypasses CORSMiddleware entirely,
    so no CORS changes are needed for this endpoint.
    """
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(_live_sensors_payload())
            await asyncio.sleep(WS_PUSH_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        pass
    except (OSError, RuntimeError) as exc:
        # A client vanishing mid-send surfaces as a transport error, not
        # always WebSocketDisconnect. Log once and let the task end —
        # this must never take the app down.
        logger.info("live websocket closed: %s", exc)


@app.get("/api/camera/snapshot")
def camera_snapshot() -> Response:
    """The newest JPEG, verbatim — no decode, no re-encode.

    Returns 503 rather than a stale image when the camera is not live:
    a snapshot silently showing a minutes-old frame is worse than an
    honest error, because the caller cannot tell the difference.
    """
    if _relay is None:
        return Response(status_code=503, content=b"camera not configured")
    jpeg, age = _relay.latest_jpeg()
    if jpeg is None:
        return Response(status_code=503, content=b"no frame received yet")
    if not _relay.is_live():
        return Response(status_code=503,
                        content=f"stale frame ({age:.1f}s old)".encode())
    return Response(content=jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.get("/api/camera/stream")
def camera_stream() -> StreamingResponse:
    """MJPEG fan-out: the same multipart format cam_node.ino serves, so
    a plain <img src> works exactly as it does against the board.

    Every client that hits this endpoint is served from the relay's slot,
    so any number of viewers cost the board exactly one connection.
    """

    def generate():
        # wait_for_frame() blocks until the NEXT frame, so this emits at
        # the upstream rate without polling (CPU) or repeating frames.
        while True:
            jpeg = _relay.wait_for_frame(timeout=5.0) if _relay else None
            if jpeg is None:
                # Upstream is down. End the response rather than hanging:
                # the browser's <img> will retry, and a stalled forever
                # connection would leak a thread per viewer.
                return
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n"
                   b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                   + jpeg + b"\r\n")

    if _relay is None:
        return Response(status_code=503, content=b"camera not configured")
    return StreamingResponse(
        generate(), media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"})


@app.get("/api/camera/status")
def camera_status() -> dict[str, Any]:
    """Relay diagnostics — whether frames are arriving, and how old."""
    if _relay is None:
        return {"configured": False, "live": False,
                "reason": "camera.stream_url not set in config.yaml"}
    return {"configured": True, **_relay.stats()}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
