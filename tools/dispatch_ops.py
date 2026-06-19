"""
dispatch_ops.py — MCP tools wrapping Tier 0 (no-auth) read-only dispatch REST endpoints.

All endpoints are available without authentication and proxy data collected by
the dispatch platform's poller and ingest services.

Base URL comes from config.DISPATCH_BASE_URL (default: https://your-dispatch.your-domain).

Covered endpoints:
  GET /healthz                         → platform health check
  GET /api/v1/cps                      → Critical Predictability State (HEMS go/no-go)
  GET /api/v1/tfr                      → raw FAA TFR list
  GET /api/v1/tfr-enriched             → TFRs with AI threat interpretation
  GET /api/v1/weather                  → METAR snapshot for DC-area airports
  GET /api/v1/alerts                   → NWS alerts for DC metro
  GET /api/v1/notams                   → active FAA NOTAMs
  GET /api/v1/amtrak                   → Amtrak status at Washington Union Station
  GET /api/v1/route                    → ground route impact assessment
  GET /api/v1/opsplan                  → ATCSCC National Operations Plan snapshot
  GET /api/v1/brief                    → current AI-generated daily operational brief
  GET /api/v1/brief/history            → brief history list
  GET /api/v1/brief/weekly             → current weekly brief
  GET /api/v1/feeds                    → feed freshness / error state for all data feeds
  GET /api/v1/aircraft/{identifier}    → FAA registry lookup by N-number or ICAO hex
"""

from __future__ import annotations

import httpx

from config import DISPATCH_URL

_TIMEOUT = 30  # seconds


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=DISPATCH_URL.rstrip("/"),
        timeout=_TIMEOUT,
        headers={"Accept": "application/json"},
    )


def _raise_for_status(resp: httpx.Response, context: str) -> None:
    """Raise ValueError with status code and body on HTTP error."""
    if resp.is_error:
        try:
            body = resp.text[:500]
        except Exception:
            body = "<unreadable>"
        raise ValueError(
            f"{context} failed with HTTP {resp.status_code}: {body}"
        )


# ── MCP tool functions ───────────────────────────────────────────────────────

def get_health_check() -> dict:
    """
    Check the health of the CS Executive Services dispatch platform.

    Returns service health summary including API status and snapshot age for
    each data feed. Use this first to verify the platform is reachable before
    querying individual feeds.

    Returns:
        dict with 'status' field and per-feed freshness, or raises ValueError
        on HTTP error.
    """
    with _client() as client:
        resp = client.get("/healthz")
        _raise_for_status(resp, "GET /healthz")
        return resp.json()


def get_cps() -> dict:
    """
    Get the current Critical Predictability State (CPS) — the HEMS go/no-go score.

    CPS is computed from six factors: ceiling, visibility, wind, precipitation,
    airspace restriction, and GDP (Ground Delay Program). Final state is one of:
    GO, CAUTION, or NO-GO per Part 135.609 thresholds.

    Returns:
        dict with keys: state (GO/CAUTION/NO-GO), score (0.0-1.0),
        factors (ceiling/visibility/wind/precip/airspace/gdp each with value,
        score, label), computed_at (ISO timestamp).
    """
    with _client() as client:
        resp = client.get("/api/v1/cps")
        _raise_for_status(resp, "GET /api/v1/cps")
        return resp.json()


def get_tfr() -> dict:
    """
    Get all active Temporary Flight Restrictions (TFRs) from the dispatch platform.

    Returns raw TFR list parsed from FAA tfr.faa.gov XML feed. Each TFR includes
    location, altitude floor/ceiling, effective time window, and type code.
    For AI-enriched TFRs with threat interpretation, use get_tfr_enriched().

    Returns:
        dict or list of active TFR objects. Each TFR includes: notam_id, type,
        location, floor_ft, ceiling_ft, effective_start, effective_end, description.
    """
    with _client() as client:
        resp = client.get("/api/v1/tfr")
        _raise_for_status(resp, "GET /api/v1/tfr")
        return resp.json()


def get_tfr_enriched() -> dict:
    """
    Get active TFRs with AI-generated threat interpretation and enrichment.

    Same TFR data as get_tfr() but with additional fields: threat_level,
    movement_type (e.g. POTUS, VVIP), pattern match flags for Marine One and
    Air Force One indicators, and plain-language summary of each TFR.

    Returns:
        dict or list of enriched TFR objects with additional fields beyond raw TFR:
        threat_level, movement_type, is_marine_one, is_af1, summary.
    """
    with _client() as client:
        resp = client.get("/api/v1/tfr-enriched")
        _raise_for_status(resp, "GET /api/v1/tfr-enriched")
        return resp.json()


def get_weather() -> dict:
    """
    Get current METAR weather snapshot for DC-area airports.

    Returns parsed METARs from AviationWeather.gov ADDS for stations in and
    around the DC area (KIAD, KDCA, KBWI, KJYO, KHEF, KCGS, etc.).

    Returns:
        dict with 'stations' list. Each station entry: icao, obs_time,
        wind_dir, wind_speed_kt, wind_gust_kt, visibility_sm, ceiling_ft,
        temp_c, dewpoint_c, altimeter_inhg, flight_category, raw_metar.
    """
    with _client() as client:
        resp = client.get("/api/v1/weather")
        _raise_for_status(resp, "GET /api/v1/weather")
        return resp.json()


def get_alerts() -> dict:
    """
    Get active National Weather Service alerts for the DC metro region.

    Pulls from api.weather.gov for the DC area. Returns warnings, watches,
    advisories, and statements currently in effect.

    Returns:
        dict or list of alert objects. Each alert includes: id, event,
        headline, description, severity, certainty, urgency, effective,
        expires, areas.
    """
    with _client() as client:
        resp = client.get("/api/v1/alerts")
        _raise_for_status(resp, "GET /api/v1/alerts")
        return resp.json()


def get_notams() -> dict:
    """
    Get active NOTAMs (Notices to Air Missions) from the dispatch platform.

    Returns NOTAMs from the FAA NOTAM API covering DC-area airports and airspace.
    Requires FAA_NOTAM_API_KEY to be configured on the dispatch platform.

    Returns:
        dict or list of NOTAM objects. Each NOTAM includes: id, type, location,
        effective_start, effective_end, text (raw NOTAM text).
    """
    with _client() as client:
        resp = client.get("/api/v1/notams")
        _raise_for_status(resp, "GET /api/v1/notams")
        return resp.json()


def get_amtrak() -> dict:
    """
    Get current Amtrak train status at Washington Union Station (WAS/WASH).

    Returns arrival and departure status for trains at WAS. Covers Acela and
    NE Regional services on the NEC corridor.

    Returns:
        dict with 'trains' list. Each train: train_number, route_name,
        direction (NORTH/SOUTH), scheduled_time, estimated_time, status,
        delay_minutes, platform, last_updated.
    """
    with _client() as client:
        resp = client.get("/api/v1/amtrak")
        _raise_for_status(resp, "GET /api/v1/amtrak")
        return resp.json()


def get_route_impact() -> dict:
    """
    Get current ground route impact assessment for DC-area chauffeur operations.

    Evaluates active TFRs, weather alerts, and airspace restrictions against
    common executive transportation corridors. Returns impact level and
    recommended route adjustments.

    Returns:
        dict with keys: impact_level (NONE/LOW/MODERATE/HIGH/SEVERE),
        factors (list of active impact sources), recommendations (list of
        suggested route adjustments), computed_at (ISO timestamp).
    """
    with _client() as client:
        resp = client.get("/api/v1/route")
        _raise_for_status(resp, "GET /api/v1/route")
        return resp.json()


def get_opsplan() -> dict:
    """
    Get the current FAA ATCSCC National Operations Plan snapshot.

    Returns the current day's ATCSCC ops plan from aviationweather.gov/node/1,
    which includes ground delay programs, ground stops, miles-in-trail
    restrictions, and other national ATCSCC advisories.

    Returns:
        dict with keys: snapshot_time (ISO timestamp), programs (list — each
        entry has type, facility, reason, avg_delay_minutes, scope, start_time,
        end_time), raw_text (full ops plan text).
    """
    with _client() as client:
        resp = client.get("/api/v1/opsplan")
        _raise_for_status(resp, "GET /api/v1/opsplan")
        return resp.json()


def get_brief() -> dict:
    """
    Get the AI-generated daily operational brief for CS Executive Services.

    Synthesizes TFR status, weather, CPS score, NWS alerts, and ATCSCC ops plan
    into a concise executive brief suitable for morning standup or client briefing.
    Brief is cached and regenerated periodically by the poller.

    Returns:
        dict with keys: brief_text (full plain-language brief), generated_at
        (ISO timestamp), cps_state (GO/CAUTION/NO-GO at brief generation time),
        tfr_count (int), alert_count (int).
    """
    with _client() as client:
        resp = client.get("/api/v1/brief")
        _raise_for_status(resp, "GET /api/v1/brief")
        return resp.json()


def get_brief_history() -> dict:
    """
    Get the brief history list from the dispatch platform.

    Returns a list of previously generated daily briefs with metadata.

    Returns:
        dict or list of brief history entries with generated_at timestamps
        and summary metadata.
    """
    with _client() as client:
        resp = client.get("/api/v1/brief/history")
        _raise_for_status(resp, "GET /api/v1/brief/history")
        return resp.json()


def get_weekly_brief() -> dict:
    """
    Get the current weekly operational brief from the dispatch platform.

    Returns a consolidated weekly summary synthesizing the week's TFR activity,
    weather patterns, operational incidents, and fleet performance.

    Returns:
        dict with weekly brief text, generation timestamp, and summary metrics.
    """
    with _client() as client:
        resp = client.get("/api/v1/brief/weekly")
        _raise_for_status(resp, "GET /api/v1/brief/weekly")
        return resp.json()


def get_feeds() -> dict:
    """
    Get freshness and error state for all dispatch data feeds.

    Returns per-feed metadata: last_updated timestamp, age_seconds, whether
    the feed is in an error state, and the last error message if any.

    Returns:
        dict keyed by feed name (tfr, metar, nws, notam, amtrak,
        atcscc_opsplan, runsheet). Each entry includes last_updated,
        age_seconds, error (bool), error_msg (str or null).
    """
    with _client() as client:
        resp = client.get("/api/v1/feeds")
        _raise_for_status(resp, "GET /api/v1/feeds")
        return resp.json()


def get_aircraft(identifier: str) -> dict:
    """
    Look up an aircraft by N-number or ICAO hex from the dispatch platform's
    local FAA registry cache (updated weekly from the FAA releasable database).

    Use this to resolve an N-number to its ICAO hex address, check if an aircraft
    is on the FAA LADD privacy list, or confirm registrant and registration status.

    Args:
        identifier: N-number ('N12345' or '12345') or ICAO hex ('a1b2c3').

    Returns:
        dict with registration record: N-number, ICAO hex, registrant, location,
        aircraft/engine type, registration status, expiry, and LADD flag.
        Returns error dict if identifier not found (HTTP 404).
    """
    ident = identifier.strip()
    with _client() as client:
        resp = client.get(f"/api/v1/aircraft/{ident}")
        if resp.status_code == 404:
            return {
                "error": f"Aircraft '{ident}' not found in FAA registry",
                "identifier": ident,
                "guidance": (
                    "Registry may not yet be imported (first import Monday 02:00 ET), "
                    "or identifier is invalid."
                ),
            }
        _raise_for_status(resp, f"GET /api/v1/aircraft/{ident}")
        return resp.json()
