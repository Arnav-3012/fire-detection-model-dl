"""Alert text composition — the ONE place the LLM is allowed (info.md 2.3).

The LLM turns an already-decided fusion verdict into readable text. It is
never asked whether there is a fire, never shown a path to influence the
escalation level or the cancel logic — its output is used only as message
body text and is never parsed for decisions. Groq failure falls back to
the deterministic templates below (info.md 3.2): the alert always goes out.

Tone (design decision, 2026-09-02, argued in logs.md Phase 8): WARNING is
the identical state for a real early-stage fire and a TV-fire false
trigger (Phase 5's documented limitation) and the system cannot yet tell
them apart — so WARNING text states that uncertainty honestly in both
directions, calm but not dismissive. CRITICAL means two independent
signals agree: genuinely urgent, direct call to action.
"""

import logging
import os
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from groq import Groq

load_dotenv()
logger = logging.getLogger("firewatch.agent")

SYSTEM_PROMPT = """You write short alert messages for FireWatch, a home fire-detection \
system. You are given a verdict already made by deterministic sensors — you never judge \
whether there is a fire, never second-guess the verdict, and never add advice about \
thresholds or sensors. Write 2-3 sentences, plain text, no markdown or emoji.

The reader is a real person, possibly stressed — never a developer reading logs. Never \
include raw sensor readings, probabilities, variable names, or anything that looks like \
a debug line. You are given an exact time phrase (such as "at 9:29 PM"). The message \
MUST contain that phrase verbatim, exactly as given — never a raw ISO timestamp, never \
a vague reference like "just now" in its place.

If the tier is WARNING (vision-only, NOT confirmed by gas sensors): state honestly that \
a visual flame signal was detected and is not yet confirmed by gas sensors. Do NOT guess \
or imply whether it is more likely a real fire or a false trigger (such as a screen \
showing fire or a bright light) — the system genuinely cannot tell at this stage, and \
the wording must not lean either way. Say monitoring continues and an immediate alert \
will follow if gas sensors confirm. Tone: calm and informative — a heads-up, not an \
emergency alarm.

If the tier is CRITICAL (vision AND gas sensors both confirm): two independent signals \
agree — this is a confirmed hazard requiring immediate attention. Tone: urgent, direct, \
with a clear call to action: respond within the 60-second window or the simulated \
dispatch proceeds."""

# Deterministic fallbacks — same wording rules as the prompt above. These
# are the messages of record if Groq is down; they must stand on their own.
# {time} takes natural_time_phrase()'s output ("at 9:29 PM" style), which
# arrives with its preposition included.
TEMPLATES = {
    "WARNING": (
        "FireWatch WARNING: Visual flame signal detected {time}, not yet "
        "confirmed by gas sensors. This could be an early-stage fire or a false "
        "trigger — the system cannot tell at this stage. Monitoring continues; "
        "you will be alerted immediately if gas sensors confirm."
    ),
    "CRITICAL": (
        "FireWatch CRITICAL: Confirmed fire hazard detected {time} — visual "
        "flame AND gas sensor readings independently agree. Check the area "
        "immediately. Respond within 60 seconds or the simulated dispatch "
        "will proceed."
    ),
}


# SMS-specific short templates (2026-09-02 bug fix — Twilio error 30044
# "Trial Message Length Exceeded"). Trial accounts cap SMS to a small
# number of 160-char GSM-7 segments; the old body (composed text + station
# line + 101/112 line + reasoning, 460-600+ chars / 4 segments) exceeded
# it. Confirmed via Twilio console: one earlier 3-segment message
# delivered, a 4-segment one failed 30044 — so the real ceiling sits
# somewhere between 3 and 4 segments. SMS_CHAR_BUDGET is deliberately far
# below that observed edge for margin, not tuned to sit just under it.
# Telegram is UNAFFECTED and keeps the full-detail message unchanged —
# this budget applies to SMS only.
SMS_CHAR_BUDGET = 300

# {time} is natural_time_phrase()'s output ("at 9:29 PM"), {numbers} is
# graph.py's emergency-numbers line collapsed to SMS length.
SMS_TEMPLATES = {
    "WARNING": "FireWatch WARNING: possible fire {time}, unconfirmed. {numbers}",
    "CRITICAL": "FireWatch CRITICAL: fire confirmed by vision+gas {time}. {numbers}",
}

# 2026-09-02 fix: SMS carries NO cancel/reply instruction of any kind.
# Considered and rejected this session: a real SMS-based cancel (Twilio
# webhook receiving the reply) would need a webhook server + ngrok tunnel
# (~1-2 hours) and a new failure surface, not worth it for the remaining
# timeline — so SMS was never going to have working reply-to-cancel.
# Leaving in a line that says "reply CANCEL" (even one pointing at
# Telegram) reads as an interactive prompt on a channel where replying
# does nothing; removed entirely. SMS is now purely informational — alert
# content + station info + 101/112 numbers, no call to action. Telegram
# is unaffected and remains the sole cancel/confirm mechanism (its own
# "Reply CANCEL within Ns..." line, built in agent/graph.py's
# notify_owner, is untouched).


def compose_sms_text(state: dict[str, Any], numbers_line: str, station_line: str,
                     llm_text: str | None = None) -> str:
    """Short SMS body, under SMS_CHAR_BUDGET chars (info.md 2.4 — never a
    malformed/truncated mid-sentence message, even in a short context).

    Purely informational (2026-09-02): no cancel/reply instruction of any
    kind — SMS has no listening mechanism behind it (see module-level note
    above), so a "reply CANCEL" line would mislead the reader into
    thinking a reply does something. Deterministic by default; if llm_text
    is given and already fits the budget alongside the numbers line, it is
    used instead of the template so SMS still reflects the composed
    wording when there's room. The station line (priority 3) is appended
    ONLY if it still fits — otherwise it's dropped from SMS specifically
    and the reader relies on Telegram's fuller message for that detail
    (explicit, logged tradeoff, not a silent drop).
    """
    level = state["level"]
    time_phrase = natural_time_phrase(state["timestamp"])
    short_numbers = numbers_line.replace("For any real emergency, call ", "Emergencies: ") \
                                 .replace(" directly.", ".")

    base = SMS_TEMPLATES.get(level, SMS_TEMPLATES["CRITICAL"]).format(
        time=time_phrase, numbers=short_numbers
    )

    def _fits(body: str) -> bool:
        return len(body) <= SMS_CHAR_BUDGET

    candidate = None
    if llm_text and time_phrase in llm_text:
        llm_body = f"{llm_text} {short_numbers}"
        if _fits(llm_body):
            candidate = llm_body

    if candidate is None:
        candidate = base

    with_station = f"{candidate} {station_line}"
    if _fits(with_station):
        return with_station
    return candidate


def natural_time_phrase(iso_timestamp: str) -> str:
    """ISO event time -> a concrete clock-time phrase, e.g. "at 9:29 PM".

    Always a real clock time, never "just now" (2026-09-02 bug fix): a vague
    phrase gives the developer no way to confirm from message history when
    an alert actually fired. Date added only when it genuinely differs from
    today. Returned WITH its preposition so templates and the LLM never
    have to conjugate around it. Unparseable input falls back to the
    current time — the message must still carry a concrete time.
    """
    try:
        event = datetime.fromisoformat(iso_timestamp)
    except (ValueError, TypeError):
        event = datetime.now()
    clock = event.strftime("%-I:%M %p")
    if event.date() == datetime.now().date():
        return f"at {clock}"
    return f"at {clock} on {event.strftime('%b %-d')}"


def compose_alert_text(state: dict[str, Any], model: str, timeout: float) -> str:
    """Return alert body text: Groq if it answers, template if not.

    The LLM is deliberately NOT shown the raw sensor values: it has no
    business evaluating them (info.md 2.3), and the message must contain
    none of them — withholding them enforces both at once. The structured
    data still reaches the console/dispatch log via notify_owner/simulate.
    """
    level = state["level"]
    time_phrase = natural_time_phrase(state["timestamp"])
    template = TEMPLATES.get(level, TEMPLATES["CRITICAL"]).format(time=time_phrase)
    user_msg = (
        f"Tier: {level}\nHazard: {state.get('reason')}\n"
        f"Time phrase to use: {time_phrase}\n"
        f"Write the alert message."
    )
    try:
        client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=timeout)
        reply = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            # gpt-oss is a reasoning model on Groq: max_tokens caps hidden
            # reasoning PLUS visible output, so a tight cap truncates the
            # visible message mid-sentence (2026-09-02 bug). 1024 leaves
            # ample room for both; the alert itself is 2-3 sentences.
            max_tokens=1024,
            temperature=0.3,
        )
        choice = reply.choices[0]
        text = (choice.message.content or "").strip()
        if choice.finish_reason == "length":
            # A cut-off alert must never reach a phone — template instead.
            logger.warning("Groq output hit the token cap (truncated) — using template")
        elif text and time_phrase in text:
            return text
        elif text:
            logger.warning("Groq output missing the time phrase %r — using template",
                           time_phrase)
        else:
            logger.warning("Groq returned empty text — using deterministic template")
    except Exception as exc:  # any Groq/network failure: template, never crash
        logger.warning("Groq compose failed (%s) — using deterministic template", exc)
    return template
