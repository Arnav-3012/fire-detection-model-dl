"""RL-shaped alert-feedback log — DATA COLLECTION ONLY (plan.md Day 8/9 scope).

One row per resolved alert event, schema decided 2026-08-31 ahead of build:
STATE (decision context at trigger) / ACTION (threshold config in effect,
read from config.yaml at log time) / OUTCOME+REWARD / METADATA. No RL, no
automated threshold adjustment, is built or implied by this file — that
remains explicitly deferred and uncommitted (info.md 2.4, no fabrication).
The schema only keeps the door open so the data never needs re-migration.

Reward mapping — the explicit implementation-time decision plan.md said
must not be left ambiguous in shipped code (made 2026-09-02):
    CANCELLED (developer replied CANCEL)   -> reward = -1  (labelled false alarm)
    TIMEOUT   (window expired, no reply)   -> reward = +1  (implicit confirmation)
A timeout is weaker evidence than an active confirmation — the developer
may simply not have seen the phone — so the raw `outcome` column is kept
alongside `reward`: the mapping stays reversible offline (e.g. re-scoring
TIMEOUT as 0) without re-collecting a single trial.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("firewatch.agent")

FIELDNAMES = [
    # METADATA — same event_id as the incident log lines / dispatch packet
    "timestamp", "event_id",
    # STATE — decision context at the trigger moment
    "level", "p_fire", "mq2", "mq135", "gas_high", "votes",
    # ACTION — the tunable knobs a future (uncommitted) policy would adjust
    "mq2_warn", "mq2_danger", "mq135_warn", "mq135_danger",
    "fire_decision_threshold", "votes_needed",
    # OUTCOME / REWARD — per the mapping in the module docstring
    "outcome", "reward",
]


def append_feedback(state: dict[str, Any], config: dict[str, Any],
                    cancelled: bool, path: str) -> None:
    """Append one resolution record to the append-only CSV.

    Never raises: a feedback-logging failure is a lost data point, not a
    reason to disturb the alert pipeline it hangs off of (info.md 3.2).
    """
    vision = state.get("vision") or {}
    sensors = state.get("sensors") or {}
    s_cfg, v_cfg = config["sensors"], config["vision"]
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event_id": state.get("event_id"),
        "level": state.get("level"),
        "p_fire": vision.get("p_fire"),
        "mq2": sensors.get("mq2"),
        "mq135": sensors.get("mq135"),
        "gas_high": sensors.get("gas_high"),
        "votes": vision.get("votes"),
        "mq2_warn": s_cfg["mq2_warn"],
        "mq2_danger": s_cfg["mq2_danger"],
        "mq135_warn": s_cfg["mq135_warn"],
        "mq135_danger": s_cfg["mq135_danger"],
        "fire_decision_threshold": v_cfg["fire_decision_threshold"],
        "votes_needed": v_cfg["votes_needed"],
        "outcome": "CANCELLED" if cancelled else "TIMEOUT",
        "reward": -1 if cancelled else +1,
    }
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        is_new = not p.exists() or p.stat().st_size == 0
        with open(p, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if is_new:
                writer.writeheader()
            writer.writerow(row)
        logger.info("feedback logged: event %s outcome=%s reward=%+d -> %s",
                    row["event_id"], row["outcome"], row["reward"], path)
    except OSError as exc:
        logger.warning("feedback log write failed (%s) — data point lost, "
                       "alert pipeline unaffected", exc)
