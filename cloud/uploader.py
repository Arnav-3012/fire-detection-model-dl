"""S3 upload of CRITICAL incident packets — cloud logging only, never dispatch.

info.md 2.1/3.2 boundaries restated here: this module contacts only the S3
bucket named in config.yaml's aws.s3_bucket, and a failure here must never
block or delay the local dispatch log, Telegram, or Twilio (all of which
have already run by the time graph.py's simulate node calls this).

Cost-safety design (developer requirement, zero tolerance for a cost bug):

1. Single fire point — log_incident() is called from exactly one place,
   agent/graph.py's simulate() node, itself reached at most once per
   incident (graph.py's conditional edge routes wait -> simulate XOR
   cancelled, never both, never in a loop). No retry loop inside this
   module compounds that call into more than one HTTP request pair.
2. Session upload counter (session_max_uploads) — a process-lifetime
   circuit breaker, checked before every upload attempt. Not expected to
   ever trip in normal use; exists purely to bound worst-case cost if some
   future bug ever caused repeated triggering.
3. No retry-with-backoff. One attempt, log a warning on failure, return.
   A retry loop is exactly the failure mode this phase is designed to
   prevent.
4. Bounded payload size — the JSON packet is the same few-hundred-byte
   dispatch packet already written to dispatch_log.jsonl (no unbounded
   fields), and the JPEG snapshot is a single webcam frame already saved
   to disk by agent/server.py (typically tens to a couple hundred KB).
   Nothing here accumulates or streams an unbounded file.
"""

import json
import logging
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("firewatch.cloud")

_upload_count = 0


def log_incident(payload: dict[str, Any], jpeg_bytes: bytes | None, aws_cfg: dict[str, Any]) -> str | None:
    """Upload one incident's JSON (+ optional JPEG) to S3. Returns the JSON key, or None.

    Called at most once per CRITICAL incident, from agent/graph.py's
    simulate() node — the same single point simulate_dispatch() already
    fires from. Never called from a loop, never called per-frame.

    On ANY failure (missing credentials, network error, bucket error): log
    a warning, fall back to a local file under data/incidents/, and
    return None. The caller's local dispatch_log.jsonl write is unaffected
    either way — it happens in simulate_dispatch(), not here.
    """
    global _upload_count

    limit = int(aws_cfg.get("max_uploads_per_session", 50))
    if _upload_count >= limit:
        logger.warning(
            "S3 upload SKIPPED — session_max_uploads circuit breaker hit "
            "(%d/%d uploads this session). This should never happen in "
            "normal use; if it does, something upstream is re-triggering "
            "incidents far more than expected. No further S3 uploads will "
            "be attempted this session.", _upload_count, limit,
        )
        return None

    event_id = payload.get("event_id", "unknown")
    stamp = payload.get("timestamp", "")
    try:
        date_part, time_part = stamp.split("T")
        y, m, d = date_part.split("-")
        hhmmss = time_part.replace(":", "")[:6]
    except (ValueError, AttributeError):
        y, m, d, hhmmss = "0000", "00", "00", "000000"

    prefix = f"device_01/{y}/{m}/{d}/{hhmmss}_{event_id}"
    json_key = f"{prefix}.json"
    jpg_key = f"{prefix}.jpg"

    try:
        s3 = boto3.client("s3", region_name=aws_cfg.get("region"))
        s3.put_object(
            Bucket=aws_cfg["s3_bucket"], Key=json_key,
            Body=json.dumps(payload).encode("utf-8"), ContentType="application/json",
        )
        if jpeg_bytes:
            s3.put_object(
                Bucket=aws_cfg["s3_bucket"], Key=jpg_key,
                Body=jpeg_bytes, ContentType="image/jpeg",
            )
        _upload_count += 1
        logger.info("S3 upload OK (%d/%d this session): s3://%s/%s",
                     _upload_count, limit, aws_cfg["s3_bucket"], json_key)
        return json_key
    except (BotoCoreError, ClientError, KeyError) as exc:
        logger.warning("S3 upload failed (%s) — falling back to local file, "
                       "no retry attempted", exc)
        _local_fallback(payload, jpeg_bytes, json_key)
        return None


def _local_fallback(payload: dict[str, Any], jpeg_bytes: bytes | None, json_key: str) -> None:
    """Write the same packet locally when S3 is unreachable (plan.md Day 10)."""
    fallback_dir = Path("data/incidents")
    fallback_dir.mkdir(parents=True, exist_ok=True)
    local_json = fallback_dir / Path(json_key).name
    local_json.write_text(json.dumps(payload))
    if jpeg_bytes:
        (fallback_dir / Path(json_key).with_suffix(".jpg").name).write_bytes(jpeg_bytes)
    logger.info("Local fallback written: %s", local_json)
