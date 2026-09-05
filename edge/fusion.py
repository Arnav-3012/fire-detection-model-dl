"""Day 7 fusion logic: combine vision and gas signals into one hazard level.

The fusion table is the system's core safety argument (plan.md section 2):
no single sensor is trusted alone. Vision can be fooled by a TV showing
fire footage (Phase 5's documented block-bar failure — 7 alarms vs the
<=2 bar, votes_needed sweep exhausted as a lever); gas sensors can spike
on cooking fumes with no fire. Only agreement between independent
modalities earns CRITICAL. That is why rule 4 caps vision-only fire at
WARNING — it is the designed mitigation for the TV/laptop-fire limitation,
not an accident of ordering.

Detection here is fully deterministic (info.md 2.3): booleans in, a level
and a fixed reason string out. No model, no LLM, no network.
"""

from enum import IntEnum

import yaml


class Level(IntEnum):
    """Hazard levels in ascending severity.

    IntEnum (not Enum) so downstream code can compare severity directly
    (e.g. "escalate only if level >= WARNING") instead of maintaining a
    parallel ordering table that could drift from this one.
    """

    SAFE = 0
    WATCH = 1
    WARNING = 2
    CRITICAL = 3


def temp_spiking() -> bool:
    """STUB — always False. No temperature sensor exists in this build.

    DHT22 was cut in Phase 0g (cost + availability), which removed the
    only temperature signal. Rather than deleting fusion rule 2
    ("fire AND temp_spiking -> CRITICAL") or silently skipping it, the
    decision (2026-08-31 session) is to keep the rule structurally
    present in fuse() and disable it here at its input: this stub is the
    single place production code obtains temp_spiking, and it always
    returns False, so rule 2 can never fire in the field.

    This is a placeholder for future temperature hardware (DHT22 or
    similar), NOT a permanent design choice. When a sensor exists,
    replace this stub with a real rate-of-rise check against
    config.yaml's temp_rise_rate (currently itself a PLACEHOLDER) and
    rule 2 becomes live with no change to fuse() itself.
    """
    return False


def load_gas_thresholds(config_path: str = "config.yaml") -> dict[str, float]:
    """Load the calibrated MQ warn/danger thresholds from config.yaml.

    Loaded from config rather than hardcoded (info.md 3.1) because these
    are real calibrated values (2026-08-31, plan.md 5.5 procedure) that
    get re-derived whenever the sensors are recalibrated — editing them
    must mean editing one file.
    """
    with open(config_path) as f:
        sensors = yaml.safe_load(f)["sensors"]
    return {
        "mq2_warn": float(sensors["mq2_warn"]),
        "mq2_danger": float(sensors["mq2_danger"]),
        "mq135_warn": float(sensors["mq135_warn"]),
        "mq135_danger": float(sensors["mq135_danger"]),
    }


def compute_gas_high(mq2: float, mq135: float, thresholds: dict[str, float]) -> bool:
    """True when either MQ sensor is at or above its WARN threshold.

    plan.md's Day 7 spec passes gas_high into fuse() as a boolean but
    never defines its derivation; this definition — either sensor >= its
    warn threshold — is the developer's explicit instruction
    (2026-08-31 session). Warn, not danger, because gas_high's job in
    the fusion table is *corroboration*: a warn-level reading agreeing
    with a visual hazard is already independent confirmation, and waiting
    for danger-level gas would delay CRITICAL in a real fire (missing a
    real fire is the worst failure, info.md 4.1).
    """
    return mq2 >= thresholds["mq2_warn"] or mq135 >= thresholds["mq135_warn"]


def fuse(
    vision_fire: bool,
    vision_smoke: bool,
    gas_high: bool,
    temp_spiking: bool,
) -> tuple[Level, str]:
    """Map the four hazard booleans to (Level, reason) per plan.md Day 7.

    Rules are checked in strict priority order — first match wins — so
    the most severe consistent interpretation is always chosen. The
    parameter names and reason strings are plan.md's, verbatim.

    Signature note: temp_spiking arrives as a plain bool, so this table
    stays a pure function of its inputs. Production callers must obtain
    it from the temp_spiking() stub above (always False — see its
    docstring), which is what keeps rule 2 disabled in the field while
    leaving it testable and structurally intact here.
    """
    # Rule 1: two independent modalities agree — the only path to
    # CRITICAL in the current hardware build.
    if (vision_fire or vision_smoke) and gas_high:
        return Level.CRITICAL, "visual hazard confirmed by gas sensor"

    # Rule 2: DISABLED in production — temp_spiking is stubbed to False
    # (no temperature sensor; DHT22 cut in Phase 0g). Kept structurally
    # so the table matches plan.md and future hardware re-enables it by
    # replacing the stub only. Reachable in tests by forcing the
    # parameter True.
    if vision_fire and temp_spiking:
        return Level.CRITICAL, "flame detected with rapid temperature rise"

    # Rule 3: gas alone — real hazard class (leak, smouldering out of
    # frame) but unconfirmed visually, so WARNING not CRITICAL.
    if gas_high and not (vision_fire or vision_smoke):
        return Level.WARNING, "gas concentration high, no visible flame"

    # Rule 4: vision-only fire caps at WARNING. This is the deliberate
    # TV/laptop-fire mitigation (Phase 5 decision): a screen showing fire
    # produces no gas, so an unconfirmed visual flame must never reach
    # CRITICAL on its own.
    if vision_fire:
        return Level.WARNING, "visual flame, unconfirmed by sensors"

    # Rule 5: smoke is the early-warning promise — worth watching, not
    # yet worth an alarm without corroboration.
    if vision_smoke:
        return Level.WATCH, "possible smoke, monitoring"

    return Level.SAFE, "nominal"
