"""Nearest-fire-station lookup via OSM Overpass — DISPLAY-ONLY (info.md 2.1).

The result is text embedded in the alert content so the DEVELOPER can call
the station themselves, immediately, without looking anything up. Nothing
in this project ever dials, forwards, or connects to the number returned
here — the only number the system ever contacts is TWILIO_TO_NUMBER, the
developer's own phone (agent/escalate.py). Any future change that would
route this module's output into a To/dial/forward field must be stopped
and flagged, not implemented (plan.md Day 8/9 revised scope).

Failure behaviour (info.md 3.2): every error path returns the same
graceful fallback dict, so the alert pipeline never crashes or stalls on
Overpass — worst case it carries "could not be determined" text. Called
exactly once per incident (graph.py's locate node) and cached in the
incident state; never re-queried within one event.
"""

import logging
import math
import time
from typing import Any

import requests

logger = logging.getLogger("firewatch.agent")

# Overpass's Apache front end 406s requests.post's default
# "User-Agent: python-requests/x.y.z" (and other generic/scripted UAs) —
# confirmed 2026-09-02 by comparing identical queries with different UAs.
# Overpass's own usage policy asks for an identifying UA; this satisfies
# that and stops the block. See logs.md Phase 8b addendum for the trace.
_USER_AGENT = ("FireWatch/1.0 (student IoT hazard-detection project; "
              "display-only fire-station lookup, no automated dispatch)")


def _fallback(why: str, fire_number: str, unified_number: str) -> dict[str, Any]:
    """Graceful fallback (info.md 3.2): Overpass failure must never block or
    delay the alert. Wording stays honest that no real station was found.

    2026-09-02: no longer repeats the 101/112 numbers itself — the caller
    (agent/graph.py's _emergency_numbers_line) now appends them as a
    standing line after this one on every message regardless of outcome,
    so restating them here would just be redundant. fire_number/
    unified_number are still accepted (config.yaml's emergency_fallback
    block, info.md 3.1) in case a future caller wants them without the
    standing line."""
    logger.warning("fire-station lookup falling back (%s)", why)
    line = "Nearest fire station could not be determined automatically."
    return {"found": False, "name": None, "phone": None,
            "distance_km": None, "line": line}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance. Good to ~0.5% — plenty for 'which is closest'."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


_RETRY_DELAY_SECONDS = 2.0  # one short retry only — bounded so it can never
                            # meaningfully delay the alert (info.md 3.2);
                            # worst case adds ~timeout+2+2s to the locate
                            # node, still well inside the 60s cancel window.


def _query_once(query: str, url: str, timeout: float) -> tuple[list[dict[str, Any]] | None, str]:
    """One Overpass POST. Returns (elements or None, description-for-log).

    Every call — success or failure — is logged with the actual HTTP
    status and a snippet of the actual response body (2026-09-02 bug
    report: prior code only logged failures, and only the exception
    string, not the real status/body, making a transient failure
    undiagnosable after the fact). This is what lets a future
    intermittent failure be read off the console/logs.md instead of
    guessed at.
    """
    try:
        resp = requests.post(url, data={"data": query}, timeout=timeout + 2,
                             headers={"User-Agent": _USER_AGENT})
    except requests.RequestException as exc:
        logger.warning("Overpass request raised %s: %s", type(exc).__name__, exc)
        return None, f"request exception: {exc}"

    if resp.status_code >= 300:
        logger.warning("Overpass HTTP %d: %s", resp.status_code, resp.text[:300])
        return None, f"HTTP {resp.status_code}: {resp.text[:200]}"

    try:
        elements = resp.json().get("elements", [])
    except ValueError as exc:
        logger.warning("Overpass HTTP %d but body did not parse as JSON: %s (%s)",
                       resp.status_code, resp.text[:300], exc)
        return None, f"HTTP {resp.status_code} with unparseable body: {exc}"

    logger.info("Overpass HTTP %d OK, %d element(s) returned", resp.status_code, len(elements))
    return elements, f"HTTP {resp.status_code} OK, {len(elements)} element(s)"


def find_nearest_fire_station(lat: float, lon: float, radius_m: int,
                              url: str, timeout: float,
                              fallback_fire_number: str,
                              fallback_unified_number: str) -> dict[str, Any]:
    """Closest amenity=fire_station to (lat, lon), or the fallback dict.

    Returns {found, name, phone, distance_km, line} where "line" is a
    ready-to-embed human sentence — callers use it verbatim so Telegram
    and the Twilio SMS say exactly the same thing (the Twilio voice call
    is out of scope as of 2026-09-02, see agent/escalate.py).

    fallback_fire_number/fallback_unified_number are used in "line" only
    on genuine lookup failure (info.md 3.2) — never when a real station is
    found, even if that station has no phone number on record. As of the
    2026-09-02 refinement, callers (agent/graph.py) ALSO append these same
    101/112 numbers as a standing line on every message regardless of this
    function's outcome — live testing found that a found-station-but-no-
    phone-number result (a common, legitimate OSM data gap) previously left
    the reader with no fallback number at all.

    2026-09-02 bug fix: live testing found the SAME coordinates return a
    real station on one run and "could not be determined" on another run
    minutes later — traced to Overpass's public instance occasionally
    returning a transient error (rate limit / temporary unavailability) on
    a single request, which the code then took as final. One short retry
    (after _RETRY_DELAY_SECONDS) is now attempted before falling back, since
    a transient failure is exactly the case info.md 3.2's graceful-fallback
    pattern exists for — but a genuine two-strikes failure still falls back
    immediately, never blocking the alert.
    """
    # (0.0, 0.0) is config.yaml's documented placeholder, not a location —
    # querying Null Island would "succeed" with garbage, so fall back loudly.
    if abs(lat) < 1e-9 and abs(lon) < 1e-9:
        return _fallback("location.latitude/longitude still 0.0 placeholders — "
                         "set real coordinates in config.yaml",
                         fallback_fire_number, fallback_unified_number)
    # nwr = nodes+ways+relations: stations are mapped as any of the three.
    # "out center" gives ways/relations a single representative coordinate.
    query = (f"[out:json][timeout:{int(timeout)}];"
             f'nwr["amenity"="fire_station"](around:{int(radius_m)},{lat},{lon});'
             f"out center tags;")

    elements, detail = _query_once(query, url, timeout)
    if elements is None:
        logger.warning("Overpass first attempt failed (%s) — retrying once after %.0fs",
                       detail, _RETRY_DELAY_SECONDS)
        time.sleep(_RETRY_DELAY_SECONDS)
        elements, detail = _query_once(query, url, timeout)
        if elements is None:
            return _fallback(f"Overpass failed twice — first: (see prior log line), "
                             f"retry: {detail}",
                             fallback_fire_number, fallback_unified_number)

    best: dict[str, Any] | None = None
    best_km = math.inf
    for el in elements:
        pos = el if "lat" in el else el.get("center", {})
        if "lat" not in pos or "lon" not in pos:
            continue
        km = _haversine_km(lat, lon, pos["lat"], pos["lon"])
        if km < best_km:
            best, best_km = el, km
    if best is None:
        return _fallback(f"no amenity=fire_station within {radius_m} m",
                         fallback_fire_number, fallback_unified_number)

    tags = best.get("tags", {})
    name = tags.get("name") or "Unnamed fire station"
    phone = tags.get("phone") or tags.get("contact:phone")
    line = f"Nearest fire station: {name}, about {best_km:.1f} km away"
    line += f", phone {phone}." if phone else ". No phone number is listed on OpenStreetMap."
    return {"found": True, "name": name, "phone": phone,
            "distance_km": round(best_km, 2), "line": line}
