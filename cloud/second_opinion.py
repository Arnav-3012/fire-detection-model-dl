"""Stage 6c: ask the Lambda for a second opinion when the board goes GAS_HIGH.

ADVISORY ONLY -- the contract cloud/lambda_infer/handler.py states, and the
reason this module has no return value the edge loop could use. Nothing
here reaches edge/fusion.py's fuse(): the result is written to a sidecar
file that only the dashboard reads. Set aws.second_opinion.enabled false
(the default) and edge/main.py's detection is byte-for-byte unchanged.

WHEN IT FIRES. On the RISING EDGE of the board's GAS_HIGH, not per frame
and not per GAS_HIGH frame -- one gas event, one call. That is what keeps
this inside the AWS free tier (tools/transport_plan.md Stage 6). A rising
edge that lands inside the cooldown, over the session budget, or while a
call is still in flight is SKIPPED, not queued: a deferred call would
score a frame from after the moment that mattered.

THREE COST GUARDS, all client-side because the account's concurrency
quota (10) left no room to reserve concurrency on the function itself:
  1. rising-edge trigger (above)
  2. cooldown_seconds between calls
  3. max_calls_per_session, a process-lifetime breaker -- same idea as
     cloud/uploader.py's max_uploads_per_session
No retries anywhere, for the reason uploader.py gives: a retry loop is
exactly how a cost bug compounds. botocore is used ONLY to sign; the
request itself is one plain requests.post().

NEVER BLOCKS THE LOOP. The encode, sign and POST all run on a daemon
thread. The edge loop's cost on a trigger is one frame.copy(); on every
other frame, one boolean compare. A cold start (~1-3s) or a dead WAN
therefore costs the detector nothing -- unlike notify_agent(), which is
synchronous and accepted there only because it is rate-limited to once
a minute.

JPEG QUALITY 95, MEASURED (2026-09-24). The cloud scores a re-encoded
copy of the frame local saw, so the encode is itself a source of
disagreement. Over 300 val frames (100/class), re-encode vs original
through the same model:

    q80  mean |dp_fire| 0.0079  max 0.242  verdict flips 3/300 (1.0%)
    q90  mean           0.0049  max 0.139  verdict flips 3/300 (1.0%)
    q95  mean           0.0027  max 0.068  verdict flips 1/300 (0.3%)

q80 is what notify_agent() uses; here it would manufacture a 1%
disagreement rate on its own, which is the signal this feature exists to
show. ~100-150KB per frame at 640x480, far under the 6MB URL payload cap.
"""

import base64
import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import cv2
import numpy as np
import requests
from dotenv import load_dotenv

JPEG_QUALITY = 95
# How many opinions the sidecar keeps. The dashboard shows the newest;
# the rest is a short on-screen history for a demo, not a record.
HISTORY_SIZE = 10

_REPO_ROOT = Path(__file__).resolve().parents[1]


def sidecar_path(live_log_path: str | Path) -> Path:
    """Where opinions are published: beside the live log. One definition,
    used by both the writer here and dashboard/backend/main.py's reader."""
    p = Path(live_log_path)
    return p.with_name(p.stem + "_second_opinion.json")


def _region_from_url(url: str) -> str:
    """<id>.lambda-url.<region>.on.aws -> <region>. SigV4 signs for a
    region, and deriving it from the endpoint means the two cannot drift."""
    host = urlparse(url).hostname or ""
    parts = host.split(".")
    if len(parts) < 4 or parts[1] != "lambda-url":
        raise ValueError(f"not a Lambda Function URL: {url!r}")
    return parts[2]


def _local_visual(vision: dict[str, Any]) -> bool:
    """What LOCAL vision says, as fuse() consumed it: the temporally
    smoothed fire alarm or sustained smoke -- not the per-frame flags."""
    return bool(vision["alarm"]) or bool(vision["smoke_sustained"])


def cloud_visual(p_fire: float, p_smoke: float, fire_thr: float, smoke_thr: float) -> tuple[bool, bool]:
    """The same per-frame decision rules local uses (config.yaml vision.*):
    fire if P(fire) >= fire_decision_threshold; smoke if smoke is the
    argmax AND P(smoke) >= smoke_decision_threshold. No temporal voting --
    the cloud sees one frame, and that asymmetry is documented in
    handler.py as part of why a disagreement is informative."""
    p_neutral = 1.0 - p_fire - p_smoke
    fire = p_fire >= fire_thr
    smoke = p_smoke >= smoke_thr and p_smoke > p_fire and p_smoke > p_neutral
    return fire, smoke


class SecondOpinion:
    """Rising-edge-triggered, budgeted, non-blocking Lambda caller.

    Construct once; call on_frame() every loop iteration AFTER set_alarm().
    Never raises into the caller.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        cfg = config.get("aws", {}).get("second_opinion", {}) or {}
        self.enabled = bool(cfg.get("enabled", False))
        self._endpoint = str(cfg.get("endpoint", ""))
        self._max_calls = int(cfg.get("max_calls_per_session", 20))
        self._cooldown = float(cfg.get("cooldown_seconds", 60))
        self._timeout = float(cfg.get("timeout_seconds", 4.0))
        self._fire_thr = float(config["vision"]["fire_decision_threshold"])
        self._smoke_thr = float(config["vision"]["smoke_decision_threshold"])
        self._path = sidecar_path(config["live_log"]["path"])

        self._prev_gas_high = False
        self._calls = 0
        self._last_call = float("-inf")
        self._in_flight = threading.Event()
        self._history: deque[dict[str, Any]] = deque(maxlen=HISTORY_SIZE)
        self._budget_announced = False
        self._region = ""
        self._credentials = None

        if self.enabled:
            try:
                self._region = _region_from_url(self._endpoint)
                # Explicit path: edge/main.py never loads .env itself, and a
                # bare load_dotenv() would search from the cwd (the bug
                # dashboard/backend/main.py documents from 2026-09-03).
                load_dotenv(_REPO_ROOT / ".env")
                import boto3  # deferred: nothing AWS loads when disabled
                creds = boto3.Session().get_credentials()
                if creds is None:
                    raise RuntimeError("no AWS credentials found (.env / ~/.aws)")
                self._credentials = creds
            except (ValueError, RuntimeError, ImportError) as exc:
                print(f"WARNING: cloud second opinion DISABLED ({exc}) — local detection unaffected")
                self.enabled = False
        # A stale sidecar from a previous run would show an old opinion as if
        # it belonged to this session. Clear it either way.
        self._publish()

    def describe(self) -> str:
        if not self.enabled:
            return "Cloud second opinion: OFF (aws.second_opinion.enabled)"
        return (f"Cloud second opinion: ON — {self._region}, rising edge of GAS_HIGH, "
                f"cooldown {self._cooldown:.0f}s, max {self._max_calls} calls/session. "
                f"ADVISORY ONLY, never feeds fuse().")

    def on_frame(self, gas_high: bool, frame: np.ndarray, level_name: str,
                 vision: dict[str, Any]) -> None:
        """Per-frame hook. Cheap unless this frame is a GAS_HIGH rising edge."""
        rising = gas_high and not self._prev_gas_high
        self._prev_gas_high = gas_high
        if not (rising and self.enabled):
            return

        now = time.monotonic()
        skip = None
        if self._calls >= self._max_calls:
            skip = f"session budget spent ({self._calls}/{self._max_calls})"
        elif now - self._last_call < self._cooldown:
            skip = f"cooldown ({now - self._last_call:.0f}s < {self._cooldown:.0f}s)"
        elif self._in_flight.is_set():
            skip = "previous call still in flight"
        if skip:
            if not (skip.startswith("session budget") and self._budget_announced):
                print(f"cloud second opinion SKIPPED — {skip}")
            self._budget_announced |= skip.startswith("session budget")
            return

        self._calls += 1
        self._last_call = now
        self._in_flight.set()
        local = {
            "level": level_name,
            "p_fire": round(float(vision["p_fire"]), 4),
            "p_smoke": round(float(vision["p_smoke"]), 4),
            "fire": bool(vision["alarm"]),
            "smoke": bool(vision["smoke_sustained"]),
            "visual": _local_visual(vision),
        }
        # Copy on THIS thread: the camera may reuse the buffer next read.
        threading.Thread(target=self._call, args=(frame.copy(), local, self._calls),
                         name="second-opinion", daemon=True).start()
        print(f"*** cloud second opinion requested ({self._calls}/{self._max_calls}) ***")

    # --- worker thread ------------------------------------------------
    def _call(self, frame: np.ndarray, local: dict[str, Any], n: int) -> None:
        entry: dict[str, Any] = {"timestamp": time.time(), "call": n, "local": local}
        started = time.perf_counter()
        try:
            ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not ok:
                raise ValueError("frame could not be JPEG-encoded")
            body = json.dumps({"jpeg_b64": base64.b64encode(jpeg.tobytes()).decode()})
            resp = requests.post(self._endpoint, data=body, headers=self._sign(body),
                                 timeout=self._timeout)
            data = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {}
            if resp.status_code != 200 or not data.get("ok"):
                raise RuntimeError(f"HTTP {resp.status_code}: {data.get('error') or resp.text[:200]}")
            entry.update(self._judge(local, data))
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            # No opinion is a normal outcome (WAN down, cold-start timeout,
            # expired key). Shown on the dashboard as exactly that.
            entry.update(ok=False, error=f"{exc.__class__.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 -- a daemon thread must not die silently
            entry.update(ok=False, error=f"unexpected {exc.__class__.__name__}: {exc}")
        finally:
            entry["round_trip_ms"] = round((time.perf_counter() - started) * 1000, 1)
            self._history.append(entry)
            self._publish()
            self._in_flight.clear()
        if entry["ok"]:
            state = "agrees" if entry["agree"] else "DISAGREES"
            print(f"*** cloud second opinion: {state} — cloud p_fire={entry['cloud']['p_fire']:.2f} "
                  f"vs local {local['level']} ({entry['round_trip_ms']:.0f}ms) ***")
        else:
            print(f"WARNING: cloud second opinion failed ({entry['error']}) — local alarm unaffected")

    def _sign(self, body: str) -> dict[str, str]:
        """SigV4 headers for the AWS_IAM Function URL. Signing only -- the
        request itself goes out via requests, so botocore's retry logic
        never gets a chance to turn one event into several invocations."""
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest

        req = AWSRequest(method="POST", url=self._endpoint, data=body,
                         headers={"Content-Type": "application/json"})
        SigV4Auth(self._credentials.get_frozen_credentials(), "lambda", self._region).add_auth(req)
        return dict(req.headers.items())

    def _judge(self, local: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        p_fire, p_smoke = float(data["p_fire"]), float(data["p_smoke"])
        fire, smoke = cloud_visual(p_fire, p_smoke, self._fire_thr, self._smoke_thr)
        return {
            "ok": True,
            "cloud": {"p_fire": p_fire, "p_smoke": p_smoke, "fire": fire, "smoke": smoke,
                      "visual": fire or smoke, "crops": data.get("crops"),
                      "inference_ms": data.get("inference_ms")},
            # Agreement is on the VISUAL question only -- "is there a
            # visible hazard in frame?" -- because that is the only thing
            # both sides can answer. Gas is local's alone.
            "agree": (fire or smoke) == local["visual"],
        }

    def _publish(self) -> None:
        """Atomic replace, same pattern and failure contract as livelog.py."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "enabled": self.enabled,
                "calls": self._calls,
                "max_calls": self._max_calls,
                "history": list(self._history),
            }))
            os.replace(tmp, self._path)
        except OSError as exc:
            print(f"WARNING: could not publish second opinion ({exc}); detection unaffected")
