"""Phase 11: read-only FastAPI data layer for the React dashboard.

Deliberately thin (developer instruction, 2026-09-03): every endpoint here
reads an existing file/S3 bucket/module and reshapes it to JSON. No fusion,
no decision logic, no writes — that all already lives in edge/ and agent/.
This process is a second, independent FastAPI app from agent/server.py
(which accepts incidents); it never imports or calls into that app.

Run from the repo root:  uvicorn dashboard.backend.main:app --port 8001
"""

import csv
import json
import logging
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.locate import find_nearest_fire_station

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

_FEEDBACK_CSV = _REPO_ROOT / _CONFIG["agent"]["feedback_log"]
_RESULTS_CSV = _REPO_ROOT / "eval/results.csv"
_LIVE_LOG_PATH = _REPO_ROOT / _CONFIG["live_log"]["path"]

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


@app.get("/api/live-sensors")
def live_sensors() -> dict[str, Any]:
    """The 1 Hz rolling live-readings buffer edge/main.py maintains
    (edge/livelog.py), plus the calibrated gas thresholds — bundled here so
    the frontend can draw threshold lines without a second config endpoint.

    The file is replaced atomically by the writer, so a read here never sees
    a partial JSON document. Missing file = edge loop not running (or not
    yet sampling): an expected state, not an error.
    """
    sensors_cfg = _CONFIG["sensors"]
    thresholds = {
        k: sensors_cfg[k]
        for k in (
            "mq2_baseline", "mq2_warn", "mq2_danger",
            "mq135_baseline", "mq135_warn", "mq135_danger",
        )
    }
    if not _LIVE_LOG_PATH.exists():
        return {"ok": False, "reason": "no live data yet — is edge/main.py running?",
                "readings": [], "thresholds": thresholds}
    try:
        readings = json.loads(_LIVE_LOG_PATH.read_text())
    except (OSError, ValueError) as exc:
        logger.warning("live-sensors read failed: %s", exc)
        return {"ok": False, "reason": str(exc), "readings": [], "thresholds": thresholds}
    return {"ok": True, "reason": None, "readings": readings, "thresholds": thresholds}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
