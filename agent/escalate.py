"""Twilio SMS to the developer's OWN phone — INFORMATIONAL ONLY.

The boundary, restated where the code lives (info.md 2.1, plan.md Day 8/9
revised scope): the ONLY number this module ever contacts is
TWILIO_TO_NUMBER — the developer's own phone. The fire-station number is
written CONTENT inside the message, never a destination; nothing here may
ever dial, forward, or connect to it, or to any emergency service, under
any framing.

**2026-09-02 scope change: the voice call is OUT of scope, SMS stays.**
Live testing showed Twilio trial accounts play an interactive "press any
key to accept the call" gate before any custom TwiML content is spoken —
this defeats the purpose of a one-way informational alert call, and
removing it requires a paid account upgrade not worth it for a prototype.
The call-placing code is kept below, commented out rather than deleted,
in case a paid account revisits this later — but it must not fire on any
WARNING/CRITICAL event. SMS is unaffected by the trial-tier call gate and
is fully working, so it remains in scope. See logs.md Phase 8b addendum
"Twilio voice call dropped from scope" for the full argument.

There is deliberately no IVR, no <Gather>, no webhook server, no keypress
cancel (decided against 2026-09-02: ngrok/webhook infrastructure for no
marginal value — and now moot for the call specifically, since the call
itself is out of scope). Telegram remains the ONLY cancel/confirm
mechanism — the SMS is one-way information.

Failure behaviour (info.md 3.2): any Twilio failure logs a warning and
returns — it can never block Telegram, which has already been sent by the
time this module runs (graph.py orders notify_owner before escalate).
Twilio SMS is the project's one real-cost service (plan.md cost note).
"""

import logging
import os
from xml.sax.saxutils import escape

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("firewatch.agent")

TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/{resource}.json"

# Full-length informational-only disclosure. 2026-09-02 SMS-length fix:
# this no longer fits the SMS character budget alongside the level/fact,
# numbers, and cancel lines (info.md 2.1's no-auto-dispatch boundary is
# still stated on Telegram's full message, which is unaffected) — kept
# here for reference/possible reuse, not appended to the short SMS body.
INFO_ONLY_LINE = (
    "This alert is informational only. FireWatch will not contact the fire "
    "station or any emergency service itself. Call them directly if this is "
    "a real emergency."
)

# Unused now that the call is out of scope (see module docstring) — kept
# for the commented-out call code below, in case it's revisited later.
# Closing line of the TTS script: names the exact action and channel the
# cancel flow expects — tools.poll_for_cancel matches any Telegram reply
# containing CANCEL, so this wording is literally actionable as spoken.
CANCEL_LINE = "If this is a false alarm, reply CANCEL on Telegram right now."


def _twilio_post(resource: str, timeout: float, **params: str) -> bool:
    """One Twilio REST request. Returns success; never raises (info.md 3.2).

    Every attempt is logged — including the request's To/From (never the
    auth token or SID) and the outcome — so a missing/failed SMS is
    diagnosable from console output/logs.md rather than guessed at
    (2026-09-02 bug report: SMS did not arrive on a live test run)."""
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    to, frm = params.get("To"), params.get("From")
    logger.info("Twilio %s request: To=%s From=%s", resource, to, frm)
    try:
        resp = requests.post(
            TWILIO_API.format(sid=sid, resource=resource), data=params,
            auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]), timeout=timeout,
        )
        if resp.status_code < 300:
            try:
                twilio_sid = resp.json().get("sid", "?")
            except ValueError:
                twilio_sid = "?"
            logger.info("Twilio %s accepted (HTTP %d), sid=%s",
                       resource, resp.status_code, twilio_sid)
            return True
        logger.warning("Twilio %s refused (HTTP %d): %s",
                       resource, resp.status_code, resp.text[:300])
    except requests.RequestException as exc:
        logger.warning("Twilio %s request raised %s: %s", resource, type(exc).__name__, exc)
    return False


def send_twilio_alerts(sms_text: str, timeout: float) -> dict[str, bool]:
    """Send the informational SMS; report what succeeded.

    **2026-09-02 SMS-length fix:** sms_text is a SEPARATE, SHORTER body
    built by agent.compose.compose_sms_text — distinct from Telegram's
    full-detail message (notify_owner). Trial Twilio accounts cap SMS to a
    few 160-char segments (error 30044 "Trial Message Length Exceeded",
    confirmed via Twilio console); reusing Telegram's full composed text +
    station line + numbers line + reasoning ran 4 segments and was
    rejected. graph.py's escalate node now builds this short body once and
    passes it straight through — this module no longer assembles the SMS
    body itself.

    **Voice call disabled 2026-09-02 (scope change, see module docstring):**
    Twilio trial accounts gate every call behind an interactive "press any
    key" prompt before any TwiML content plays, which defeats the point of
    a one-way informational call — not worth a paid-account upgrade for a
    prototype. The call code is left in place, commented out, below.
    Returns only {"call": False, "sms": ...} — call is always False now,
    so agent/graph.py's old call-duration cancel-window extension never
    triggers (window reverts to the flat base, per that same change).
    """
    try:
        to = os.environ["TWILIO_TO_NUMBER"]        # the developer's own phone —
        sender = os.environ["TWILIO_FROM_NUMBER"]  # the ONLY destination, ever
    except KeyError as exc:
        logger.warning("Twilio env var missing (%s) — SMS was NEVER attempted "
                       "(no HTTP request made), not a Twilio-side failure. "
                       "Check .env has all four TWILIO_* vars set.", exc)
        return {"call": False, "sms": False}

    body = sms_text

    # --- Voice call: OUT OF SCOPE 2026-09-02, do not re-enable without
    # --- revisiting the Twilio trial-tier "press any key" gate first.
    # script = escape(
    #     f"Fire Watch alert. {alert_text} {station_line} {INFO_ONLY_LINE} {CANCEL_LINE}")
    # twiml = (f"<Response><Say>{script}</Say><Pause length='1'/>"
    #          f"<Say>Repeating. {script}</Say></Response>")
    # call_ok = _twilio_post("Calls", timeout, To=to, From=sender, Twiml=twiml)
    call_ok = False

    result: dict[str, bool] = {
        "call": call_ok,
        "sms": _twilio_post("Messages", timeout, To=to, From=sender, Body=body),
    }
    logger.info("Twilio informational alerts: call=%(call)s sms=%(sms)s", result)
    return result
