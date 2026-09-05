"""Agent tools: Telegram delivery, cancel polling, simulated dispatch.

Telegram is the ONLY cancel/confirm mechanism — reply-based per plan.md
Day 9 ("a message containing CANCEL"), no inline buttons, no webhook
server, no IVR/keypress path on any channel, ever. Phase 8b added the
other channels in their own modules: agent/locate.py (Overpass, display-
only), agent/escalate.py (Twilio, informational one-way, developer's own
number only), agent/feedback.py (RL-shaped outcome log, data only).

info.md 2.1 is absolute here: simulate_dispatch() writes a local JSON line
and prints a banner. It contacts nothing. If a future change would let any
code in this file reach a real emergency service, stop and flag it instead.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("firewatch.agent")

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _telegram_call(method: str, timeout: float = 10.0, **params: Any) -> dict | None:
    """One Telegram Bot API call. Returns the result dict, or None on failure.

    Failures return None instead of raising because per info.md 3.2 the
    alert path degrades and continues — it never crashes on the network.
    """
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    try:
        resp = requests.post(
            TELEGRAM_API.format(token=token, method=method), data=params, timeout=timeout
        )
        body = resp.json()
        if body.get("ok"):
            return body["result"]
        logger.warning("Telegram %s refused: %s", method, body.get("description"))
    except requests.RequestException as exc:
        logger.warning("Telegram %s failed: %s", method, exc)
    return None


def send_telegram(text: str, photo_path: str | None = None) -> bool:
    """Send the alert to the configured chat; retry once (info.md 3.2).

    Sends the snapshot as a photo with the alert as caption when available
    (Telegram caps captions at 1024 chars — compose keeps text short), and
    falls back to text-only if the photo send fails or there is no snapshot:
    a missing image must never cost the alert itself.
    """
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    for attempt in (1, 2):
        if photo_path and Path(photo_path).is_file():
            try:
                with open(photo_path, "rb") as f:
                    token = os.environ["TELEGRAM_BOT_TOKEN"]
                    resp = requests.post(
                        TELEGRAM_API.format(token=token, method="sendPhoto"),
                        data={"chat_id": chat_id, "caption": text[:1024]},
                        files={"photo": f},
                        timeout=15,
                    )
                if resp.json().get("ok"):
                    return True
                logger.warning("sendPhoto attempt %d refused: %s", attempt, resp.text[:200])
            except (requests.RequestException, ValueError) as exc:
                logger.warning("sendPhoto attempt %d failed: %s", attempt, exc)
        if _telegram_call("sendMessage", chat_id=chat_id, text=text) is not None:
            return True
    logger.warning("Telegram delivery failed after retry — alert NOT delivered")
    return False


def latest_update_id() -> int:
    """Baseline getUpdates offset, captured BEFORE the alert is sent.

    This makes the cancel window immune to stale chat history: only
    messages arriving after this point can cancel.
    """
    result = _telegram_call("getUpdates", offset=-1, timeout=5)
    if result:
        return result[-1]["update_id"] + 1
    return 0


def poll_for_cancel(window_seconds: float, poll_interval: float, offset: int) -> bool:
    """Poll getUpdates for a message containing CANCEL from the configured chat.

    Exactly plan.md Day 9's mechanism: reply-based, 60s, early return on
    match. Any Telegram failure mid-window counts as no-cancel — the safe
    default is to proceed to (simulated) dispatch, never to silently drop
    a confirmed hazard because the network flaked.
    """
    chat_id = str(os.environ["TELEGRAM_CHAT_ID"])
    deadline = time.monotonic() + window_seconds
    while time.monotonic() < deadline:
        updates = _telegram_call("getUpdates", offset=offset, timeout=5) or []
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message") or {}
            if str(msg.get("chat", {}).get("id")) != chat_id:
                continue
            if "CANCEL" in (msg.get("text") or "").upper():
                return True
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
    return False


def simulate_dispatch(state: dict[str, Any], log_path: str) -> dict[str, Any]:
    """Append the SIMULATED dispatch packet to a local JSONL file. Nothing else.

    info.md 2.1, absolute rule: no call, SMS, or API request to any real
    emergency service, ever. The packet exists so the report can show what
    WOULD be sent; the banner exists so no demo viewer can mistake it for
    a real dispatch.
    """
    packet = {
        "SIMULATED": True,
        "note": "SIMULATION ONLY — no real emergency service was contacted, "
        "no call or message was placed. Packet written to a local file only.",
        "event_id": state.get("event_id", str(uuid.uuid4())),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "level": state.get("level"),
        "reason": state.get("reason"),
        "vision": state.get("vision"),
        "sensors": state.get("sensors"),
        "alert_text": state.get("alert_text"),
        "owner_response": "cancel window expired or hazard confirmed — not cancelled",
        "snapshot_path": state.get("snapshot_path"),
    }
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(packet) + "\n")
    banner = "*" * 66
    print(f"\n{banner}\n***  SIMULATED DISPATCH — THIS IS NOT A REAL EMERGENCY CALL  ***")
    print("***  No emergency service was contacted. Packet appended to   ***")
    print(f"***  {str(path):<56}  ***\n{banner}\n")
    return packet
