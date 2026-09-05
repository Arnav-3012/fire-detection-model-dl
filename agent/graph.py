"""LangGraph response agent (Phase 8 core + Phase 8b channels).

The graph handles RESPONSE only. Detection is deterministic and finished
before this file is ever invoked: edge/main.py's fuse() has already
produced a WARNING-or-above verdict (plan.md — the agent triggers at
WARNING/CRITICAL). Nothing here re-evaluates it; verify only bounces
anything below WARNING as a defensive guard, it never upgrades.

Nodes (plan.md Day 8, Phase 8b complete):
    verify -> locate -> compose -> notify_owner -> escalate -> wait
        -> {cancelled | simulate}, both of which append the feedback row.
Ordering is deliberate: Telegram (notify_owner) fires BEFORE Twilio
(escalate) so a Twilio failure can never block or delay the primary
must-not-fail channel. Twilio is informational only — no IVR/keypress
cancel on any channel, ever; Telegram reply is the only cancel mechanism.

Fixed edges are the point (plan.md 4.3): notify_owner can never be
skipped, and no LLM output can alter the route — compose writes text,
the edges are wired at build time.
"""

import argparse
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

import yaml
from langgraph.graph import END, StateGraph

from agent.compose import compose_alert_text, compose_sms_text
from agent.escalate import send_twilio_alerts
from agent.feedback import append_feedback
from agent.locate import find_nearest_fire_station
from agent.tools import latest_update_id, poll_for_cancel, send_telegram, simulate_dispatch
from cloud.uploader import log_incident

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("firewatch.agent")


class IncidentState(TypedDict, total=False):
    level: str                # "WARNING" | "CRITICAL" — decided upstream by fuse()
    reason: str               # fusion rule text, e.g. "visual hazard confirmed by gas sensor"
    timestamp: str
    event_id: str
    vision: dict[str, Any]    # p_fire, votes, alarm, smoke
    sensors: dict[str, Any]   # mq2, mq135, gas_high, gated
    snapshot_path: str | None
    station: dict[str, Any]   # locate's DISPLAY-ONLY result, cached once per incident
    alert_text: str
    delivered: bool
    twilio: dict[str, Any]    # escalate's {"call": False, "sms": ok} — call always False, voice call out of scope 2026-09-02
    update_offset: int        # getUpdates baseline, captured before the alert
    cancelled: bool


def _config() -> dict[str, Any]:
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def _station_line(state: IncidentState) -> str:
    # Missing station must cost a line of text, never the alert itself.
    # This default only fires if locate somehow never ran (defensive —
    # normal outcome wording comes from locate.py; the 101/112 numbers are
    # no longer part of this line — see _emergency_numbers_line below).
    default_line = "Nearest fire station could not be determined automatically."
    return (state.get("station") or {}).get("line", default_line)


def _emergency_numbers_line(state: IncidentState) -> str:
    # 2026-09-02 refinement: live testing found a real gap — Overpass CAN
    # find a real station whose OSM entry simply has no phone listed (a
    # legitimate, common OSM data gap, not a lookup bug). That case used to
    # print "no phone number is listed" with NO 101/112 fallback at all,
    # since those numbers were originally wired only into the "Overpass
    # found nothing" case. Fix: this line is now a STANDING safety
    # instruction, appended unconditionally after the station line in every
    # WARNING/CRITICAL message on both channels — independent of whether
    # Overpass succeeded, failed, or succeeded without a number.
    fb = _config()["emergency_fallback"]
    return (
        f"For any real emergency, call {fb['fire_number']} (Fire) or "
        f"{fb['unified_number']} (Unified Emergency) directly."
    )


def verify(state: IncidentState) -> IncidentState:
    """Guard, not a judge: reject sub-WARNING input, never upgrade anything."""
    if state.get("level") not in ("WARNING", "CRITICAL"):
        raise ValueError(
            f"agent invoked with level={state.get('level')!r} — the agent only "
            "runs on fuse()'s WARNING-or-above verdicts (info.md 2.3)"
        )
    state.setdefault("event_id", str(uuid.uuid4()))
    state.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
    return state


def locate(state: IncidentState) -> IncidentState:
    """Overpass fire-station lookup, once per incident (Phase 8b Part 1).

    DISPLAY-ONLY: the result is alert text so the developer can call the
    station themselves — the system never contacts that number, ever
    (info.md 2.1). find_nearest_fire_station never raises; worst case is
    a bounded overpass_timeout_seconds delay and a fallback line."""
    cfg = _config()
    loc, agent_cfg, fallback_cfg = cfg["location"], cfg["agent"], cfg["emergency_fallback"]
    state["station"] = find_nearest_fire_station(
        float(loc["latitude"]), float(loc["longitude"]),
        int(agent_cfg["overpass_radius_m"]), agent_cfg["overpass_url"],
        float(agent_cfg["overpass_timeout_seconds"]),
        str(fallback_cfg["fire_number"]), str(fallback_cfg["unified_number"]),
    )
    return state


def compose(state: IncidentState) -> IncidentState:
    agent_cfg = _config()["agent"]
    state["alert_text"] = compose_alert_text(
        dict(state), agent_cfg["groq_model"], float(agent_cfg["groq_timeout_seconds"])
    )
    return state


def notify_owner(state: IncidentState) -> IncidentState:
    """Send the alert to Telegram; baseline the cancel offset first.

    The message body is human sentences ONLY (2026-09-02 addendum): the
    composed text (which carries the level and a natural-language time)
    plus the deterministic cancel instruction. The raw technical context
    stays out of the message — it goes to the console log below and into
    the dispatch packet, never to the stressed person's phone.
    """
    vision = state.get("vision") or {}
    sensors = state.get("sensors") or {}
    logger.info(
        "incident %s %s (%s): p_fire=%s votes=%s mq2=%s mq135=%s gas_high=%s",
        state.get("event_id"), state["level"], state["reason"],
        vision.get("p_fire"), vision.get("votes"),
        sensors.get("mq2"), sensors.get("mq135"), sensors.get("gas_high"),
    )
    base = float(_config()["fusion"]["cancel_window_seconds"])
    message = (
        f"{state['alert_text']}\n\n"
        f"{_station_line(state)}\n\n"
        f"{_emergency_numbers_line(state)}\n\n"
        f"Reply CANCEL within {base:.0f} seconds to stop escalation."
    )
    print(f"--- Telegram message ---\n{message}\n------------------------")
    state["update_offset"] = latest_update_id()
    state["delivered"] = send_telegram(message, state.get("snapshot_path"))
    return state


def escalate(state: IncidentState) -> IncidentState:
    """Twilio SMS to the developer's OWN number (Phase 8b Part 2).

    Informational one-way only — Telegram (already sent, one node back)
    stays the only cancel mechanism. send_twilio_alerts never raises.

    **2026-09-02 SMS-length fix (Twilio error 30044 "Trial Message Length
    Exceeded"):** trial accounts cap SMS to a few 160-char segments; the
    body used to reuse Telegram's full alert_text + station_line +
    emergency_numbers_line, which ran 4 segments and was rejected —
    confirmed via Twilio console. The SMS now gets its OWN short body from
    compose_sms_text (under compose.SMS_CHAR_BUDGET chars), separate from
    Telegram's unchanged full-detail message. Station name/number is
    included only if it still fits after the level/fact and numbers lines
    — otherwise it's dropped from SMS specifically (logged tradeoff) and
    the reader relies on Telegram for that detail.

    **2026-09-02 (same day, later): SMS cancel line removed.** SMS has no
    listening/webhook mechanism behind it — Telegram alone can receive and
    act on a CANCEL reply (agent/tools.py poll_for_cancel). A real
    SMS-based cancel would need a Twilio webhook server + ngrok tunnel
    (~1-2 hours, a new failure surface); assessed and explicitly rejected
    given the project's remaining timeline. compose_sms_text no longer
    emits any "reply CANCEL" wording — SMS is purely informational (alert
    content + station info + 101/112 numbers), so it can never imply an
    interactive response works when it doesn't.

    **Voice call OUT OF SCOPE (2026-09-02):** Twilio trial accounts gate
    every call behind an interactive "press any key" prompt before any
    custom content plays, defeating an informational alert call — not
    worth a paid-account upgrade for a prototype. SMS is unaffected and
    stays in scope. See agent/escalate.py and logs.md Phase 8b addendum
    "Twilio voice call dropped from scope"."""
    agent_cfg = _config()["agent"]
    sms_text = compose_sms_text(
        dict(state), _emergency_numbers_line(state), _station_line(state),
        llm_text=state.get("alert_text"),
    )
    if len(sms_text) > 300:  # sanity guard, mirrors compose.SMS_CHAR_BUDGET
        logger.warning("SMS body unexpectedly long (%d chars) — sending anyway", len(sms_text))
    logger.info("SMS body (%d chars): %s", len(sms_text), sms_text)
    state["twilio"] = send_twilio_alerts(sms_text, float(agent_cfg["twilio_timeout_seconds"]))
    return state


def wait(state: IncidentState) -> IncidentState:
    """Reply-based cancel window (plan.md Day 9's mechanism).

    Flat `cancel_window_seconds` base. **2026-09-02: the prior call-
    duration extension was reverted** — with the voice call out of scope
    (agent/escalate.py), there is no call to time against, so the window
    is always exactly the base again."""
    cfg = _config()
    window = float(cfg["fusion"]["cancel_window_seconds"])
    print(f"--- cancel window open: reply CANCEL on Telegram within {window:.0f}s ---")
    state["cancelled"] = poll_for_cancel(
        window, float(cfg["agent"]["telegram_poll_seconds"]), state.get("update_offset", 0)
    )
    return state


def _incident_packet(state: IncidentState, owner_response: str) -> dict[str, Any]:
    """Same field shape as tools.simulate_dispatch's packet, for S3-only use
    on the cancelled path (which never touches dispatch_log.jsonl — that
    file's purpose is what WOULD have been dispatched, not every incident).
    Not SIMULATED-dispatch-framed: a cancelled event was never a dispatch."""
    return {
        "event_id": state.get("event_id"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "level": state.get("level"),
        "reason": state.get("reason"),
        "vision": state.get("vision"),
        "sensors": state.get("sensors"),
        "alert_text": state.get("alert_text"),
        "owner_response": owner_response,
        "snapshot_path": state.get("snapshot_path"),
    }


def _upload_critical(state: IncidentState, cfg: dict[str, Any], packet: dict[str, Any]) -> None:
    """Phase 10 (+ CRITICAL/cancelled extension): CRITICAL only, at most
    once per call site. Called from both terminal nodes so the CRITICAL
    corpus in S3 covers true dispatches AND cancelled false alarms — both
    are needed for log review / model performance, not just non-cancelled
    ones. Each call site still fires at most once per incident (verify's
    fixed-edge graph reaches exactly one terminal node per run)."""
    if state.get("level") != "CRITICAL":
        return
    jpeg_bytes = None
    snapshot_path = state.get("snapshot_path")
    if snapshot_path and Path(snapshot_path).is_file():
        jpeg_bytes = Path(snapshot_path).read_bytes()
    log_incident(packet, jpeg_bytes, cfg["aws"])


def cancelled(state: IncidentState) -> IncidentState:
    """Owner cancelled: record as a false alarm (reward -1) and stop."""
    logger.info("event %s CANCELLED by owner — logged as false alarm, no dispatch",
                state.get("event_id"))
    print("--- owner replied CANCEL: false alarm, escalation stopped ---")
    cfg = _config()
    packet = _incident_packet(state, owner_response="cancelled by owner within window")
    _upload_critical(state, cfg, packet)
    append_feedback(dict(state), cfg, cancelled=True, path=cfg["agent"]["feedback_log"])
    return state


def simulate(state: IncidentState) -> IncidentState:
    cfg = _config()
    packet = simulate_dispatch(dict(state), cfg["agent"]["dispatch_log"])
    # S3 upload fires here, CRITICAL only, at most once — the same single
    # point simulate_dispatch() already fires from. A WARNING timeout
    # still writes the local dispatch log above but never uploads.
    _upload_critical(state, cfg, packet)
    append_feedback(dict(state), cfg, cancelled=False, path=cfg["agent"]["feedback_log"])
    return state


def build_graph() -> Any:
    """Wire the fixed-edge state machine. Routes are code, never LLM output."""
    g = StateGraph(IncidentState)
    for name, fn in [("verify", verify), ("locate", locate), ("compose", compose),
                     ("notify_owner", notify_owner), ("escalate", escalate),
                     ("wait", wait), ("cancelled", cancelled), ("simulate", simulate)]:
        g.add_node(name, fn)
    g.set_entry_point("verify")
    g.add_edge("verify", "locate")
    g.add_edge("locate", "compose")
    g.add_edge("compose", "notify_owner")
    # Telegram before Twilio: the primary channel is never behind Twilio.
    g.add_edge("notify_owner", "escalate")
    g.add_edge("escalate", "wait")
    g.add_conditional_edges(
        "wait",
        lambda s: "cancelled" if s.get("cancelled") else "simulate",
        {"cancelled": "cancelled", "simulate": "simulate"},
    )
    g.add_edge("cancelled", END)
    g.add_edge("simulate", END)
    return g.compile()


def run_incident(payload: dict[str, Any]) -> dict[str, Any]:
    """Entry point used by agent/server.py per incident."""
    return dict(build_graph().invoke(payload))


if __name__ == "__main__":
    # Fire drill: exercise the full graph with a synthetic verdict, no edge
    # loop needed. The verdict is still handed in ready-made — even the
    # drill never asks the agent to decide anything.
    parser = argparse.ArgumentParser(description="FireWatch agent fire drill")
    parser.add_argument("level", choices=["warning", "critical"])
    args = parser.parse_args()
    drill = {
        "level": args.level.upper(),
        "reason": "visual hazard confirmed by gas sensor" if args.level == "critical"
        else "visual flame, unconfirmed by sensors",
        "vision": {"p_fire": 0.91, "votes": 6, "alarm": True, "smoke": False},
        "sensors": {"mq2": 181 if args.level == "critical" else 58,
                    "mq135": 152 if args.level == "critical" else 52,
                    "gas_high": args.level == "critical", "gated": False},
        "snapshot_path": None,
    }
    final = run_incident(drill)
    print(f"drill finished: delivered={final.get('delivered')} "
          f"twilio={final.get('twilio')} cancelled={final.get('cancelled')} "
          f"station_found={(final.get('station') or {}).get('found')}")
