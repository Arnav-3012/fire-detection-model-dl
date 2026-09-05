"""FastAPI front door for the response agent (plan.md Day 8).

POST /incident accepts the payload edge/main.py sends, saves the snapshot,
and runs the LangGraph app in a background task — the response returns
immediately because main.py POSTs with a 2s timeout (info.md 3.2) and the
graph legitimately takes 60s+ (the cancel window). The edge loop must
never wait on the agent.

Binds to 127.0.0.1 only (config.yaml agent.host): this is a same-machine
companion process, not an exposed service.

Run from the repo root:  uvicorn agent.server:app --port 8000
"""

import base64
import binascii
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel

from agent.graph import run_incident

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("firewatch.agent")

app = FastAPI(title="FireWatch response agent")

with open("config.yaml") as f:
    _CONFIG = yaml.safe_load(f)


class Incident(BaseModel):
    """Wire format from edge/main.py. level/reason are fuse()'s verdict —
    already decided; the agent never revisits it."""

    level: str
    reason: str
    vision: dict[str, Any]
    sensors: dict[str, Any]
    snapshot_b64: str | None = None
    timestamp: str | None = None


def _save_snapshot(snapshot_b64: str, event_stamp: str) -> str | None:
    """Decode and save the JPEG; a bad snapshot never costs the alert."""
    snapshot_dir = Path(_CONFIG["agent"]["snapshot_dir"])
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{event_stamp}.jpg"
    try:
        path.write_bytes(base64.b64decode(snapshot_b64))
        return str(path)
    except (binascii.Error, ValueError, OSError) as exc:
        logger.warning("snapshot decode/save failed (%s) — alert continues without it", exc)
        return None


def _run(payload: dict[str, Any]) -> None:
    try:
        final = run_incident(payload)
        logger.info("incident %s handled: delivered=%s cancelled=%s",
                    final.get("event_id"), final.get("delivered"), final.get("cancelled"))
    except Exception:
        # Background task: an unhandled error here would vanish silently.
        logger.exception("agent graph failed for incident")


@app.post("/incident")
def incident(inc: Incident, background: BackgroundTasks) -> dict[str, str]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload: dict[str, Any] = inc.model_dump(exclude={"snapshot_b64"})
    payload["snapshot_path"] = _save_snapshot(inc.snapshot_b64, stamp) if inc.snapshot_b64 else None
    if not payload.get("timestamp"):
        payload["timestamp"] = datetime.now().isoformat(timespec="seconds")
    background.add_task(_run, payload)
    return {"status": "accepted"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
