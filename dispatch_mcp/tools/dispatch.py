"""Dispatch platform tools — wraps the corporatetraveldc REST API.

All Tier 0 (/api/v1/*) endpoints require no authentication.
Runsheet (/api/v1/runsheet) requires Tailscale network access (returns 403 from public internet).
Watchlist endpoints manage VIP session state.
"""

import json
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

from dispatch_mcp.client import dispatch_get, dispatch_post, dispatch_delete, handle_http_error


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class WatchlistAddInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    session_type: str = Field(
        ...,
        description="Session type, e.g. 'flight', 'ground', 'person'",
        min_length=1,
        max_length=32,
    )
    subject: str = Field(
        ...,
        description="Human-readable label, e.g. callsign 'KLM651' or name 'POTUS'",
        min_length=1,
        max_length=128,
    )
    hex: Optional[str] = Field(
        default=None,
        description="ICAO 24-bit hex address of aircraft, e.g. '484150'. Required for flight tracking.",
        min_length=6,
        max_length=6,
    )
    registration: Optional[str] = Field(
        default=None,
        description="Aircraft tail/registration number, e.g. 'N12345' or 'PH-BKB'",
        max_length=16,
    )
    destination_icao: Optional[str] = Field(
        default=None,
        description="Destination airport ICAO code, e.g. 'KIAD', 'KJFK'",
        max_length=4,
    )


class WatchlistRemoveInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    session_id: Optional[str] = Field(
        default=None, description="Watchlist session ID to remove"
    )
    hex: Optional[str] = Field(
        default=None, description="ICAO hex of aircraft whose session to remove"
    )


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:  # noqa: C901

    @mcp.tool(
        name="dispatch_health_check",
        annotations={
            "title": "Dispatch Platform Health Check",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_health_check() -> str:
        """Check the health of the CS Executive Services dispatch platform.

        Returns service health summary including API status and snapshot age for
        each data feed. Use this first to verify the platform is reachable before
        querying individual feeds.

        Returns:
            str: JSON with 'status' field and per-feed freshness, or error string.

        Examples:
            - "Is the dispatch platform up?" -> call with no params
            - "How old is the TFR data?" -> call, check 'tfr.age_seconds' in response
        """
        try:
            data = await dispatch_get("/healthz")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_feeds",
        annotations={
            "title": "Get Feed Freshness and Error State",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_feeds() -> str:
        """Get freshness and error state for all dispatch data feeds.

        Returns per-feed metadata: last_updated timestamp, age_seconds, whether
        the feed is in an error state, and the last error message if any.

        Returns:
            str: JSON dict keyed by feed name (tfr, metar, nws, notam, amtrak,
                 atcscc_opsplan, runsheet). Each entry includes last_updated,
                 age_seconds, error (bool), error_msg (str|null).

        Examples:
            - "Which feeds are stale or erroring?" -> call and filter error==true
            - "When was weather last updated?" -> call, check metar.last_updated
        """
        try:
            data = await dispatch_get("/api/v1/feeds")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_tfr",
        annotations={
            "title": "Get Active TFRs",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_tfr() -> str:
        """Get all active Temporary Flight Restrictions (TFRs) from the dispatch platform.

        Returns raw TFR list parsed from FAA tfr.faa.gov XML feed. Each TFR includes
        location, altitude floor/ceiling, effective time window, and type code.
        For AI-enriched TFRs with threat interpretation, use dispatch_get_tfr_enriched.

        Returns:
            str: JSON list of active TFR objects, or error string.
                Each TFR includes: notam_id, type, location, floor_ft, ceiling_ft,
                effective_start, effective_end, description.

        Examples:
            - "Are there any active TFRs?" -> call, check array length
            - "Are there VIP or POTUS TFRs active?" -> call, filter by type or description
        """
        try:
            data = await dispatch_get("/api/v1/tfr")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_tfr_enriched",
        annotations={
            "title": "Get AI-Enriched TFRs",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_tfr_enriched() -> str:
        """Get active TFRs with AI-generated threat interpretation and enrichment.

        Same TFR data as dispatch_get_tfr but with additional fields: threat_level,
        movement_type (e.g. POTUS, VVIP), pattern match flags for Marine One and
        Air Force One indicators, and plain-language summary of each TFR.

        Returns:
            str: JSON list of enriched TFR objects. Additional fields beyond raw TFR:
                threat_level (str), movement_type (str|null), is_marine_one (bool),
                is_af1 (bool), summary (str).

        Examples:
            - "Any Marine One TFRs right now?" -> call, filter is_marine_one==true
            - "What's the threat level of active TFRs?" -> call, check threat_level fields
        """
        try:
            data = await dispatch_get("/api/v1/tfr-enriched")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_weather",
        annotations={
            "title": "Get DC-Area METAR Weather Snapshot",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_weather() -> str:
        """Get the current METAR weather snapshot for DC-area airports.

        Returns parsed METARs from AviationWeather.gov ADDS for stations in and
        around the DC area (KIAD, KDCA, KBWI, KJYO, KHEF, KCGS, etc.).
        Data includes ceiling, visibility, wind, temperature, altimeter.

        Returns:
            str: JSON dict with 'stations' list. Each station entry:
                icao (str), obs_time (str), wind_dir (int|null), wind_speed_kt (int),
                wind_gust_kt (int|null), visibility_sm (float), ceiling_ft (int|null),
                temp_c (float), dewpoint_c (float), altimeter_inhg (float),
                flight_category (str: VFR/MVFR/IFR/LIFR), raw_metar (str).

        Examples:
            - "What's the ceiling at Dulles?" -> call, find KIAD entry, check ceiling_ft
            - "Is it VFR at DC area airports?" -> call, check flight_category per station
        """
        try:
            data = await dispatch_get("/api/v1/weather")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_alerts",
        annotations={
            "title": "Get Active NWS Weather Alerts",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_alerts() -> str:
        """Get active National Weather Service alerts for the DC metro region.

        Pulls from api.weather.gov for the DC area. Returns warnings, watches,
        advisories, and statements currently in effect.

        Returns:
            str: JSON list of alert objects. Each alert includes:
                id (str), event (str, e.g. 'Winter Storm Warning'),
                headline (str), description (str), severity (str),
                certainty (str), urgency (str), effective (str), expires (str),
                areas (list[str]).

        Examples:
            - "Are there any weather alerts for DC?" -> call, check array length
            - "Any tornado warnings active?" -> call, filter by event containing 'Tornado'
        """
        try:
            data = await dispatch_get("/api/v1/alerts")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_notams",
        annotations={
            "title": "Get Active NOTAMs",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_notams() -> str:
        """Get active NOTAMs (Notices to Air Missions) from the dispatch platform.

        Requires FAA_NOTAM_API_KEY to be configured on the Pi. Returns NOTAMs
        from the FAA NOTAM API covering DC-area airports and airspace.

        Returns:
            str: JSON list of NOTAM objects, or feed-error string if key not configured.
                Each NOTAM includes: id, type, location, effective_start, effective_end,
                text (raw NOTAM text).

        Examples:
            - "Any NOTAMs for KIAD?" -> call, filter by location=='KIAD'
            - "Are there any runway closures at DCA?" -> call, filter by location and text
        """
        try:
            data = await dispatch_get("/api/v1/notams")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_cps",
        annotations={
            "title": "Get Critical Predictability State (HEMS Go/No-Go)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_cps() -> str:
        """Get the current Critical Predictability State (CPS) — the HEMS go/no-go score.

        CPS is computed from six factors: ceiling, visibility, wind, precipitation,
        airspace restriction, and GDP (Ground Delay Program). Final state is one of:
        GO, CAUTION, or NO-GO per Part 135.609 thresholds.

        Returns:
            str: JSON object with:
                state (str: GO/CAUTION/NO-GO),
                score (float: 0.0-1.0),
                factors: {
                    ceiling: {value, score, label},
                    visibility: {value, score, label},
                    wind: {value, score, label},
                    precip: {value, score, label},
                    airspace: {value, score, label},
                    gdp: {value, score, label}
                },
                computed_at (str: ISO timestamp).

        Examples:
            - "Is it a go for HEMS operations?" -> call, check state field
            - "What's limiting the CPS score?" -> call, find lowest factor scores
        """
        try:
            data = await dispatch_get("/api/v1/cps")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_route",
        annotations={
            "title": "Get Ground Route Impact Assessment",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_route() -> str:
        """Get current ground route impact assessment for DC-area chauffeur operations.

        Evaluates active TFRs, weather alerts, and airspace restrictions against
        common executive transportation corridors. Returns impact level and
        recommended route adjustments.

        Returns:
            str: JSON object with:
                impact_level (str: NONE/LOW/MODERATE/HIGH/SEVERE),
                factors (list[str]: active impact sources),
                recommendations (list[str]: suggested route adjustments),
                computed_at (str: ISO timestamp).

        Examples:
            - "Will TFRs affect our route today?" -> call, check impact_level
            - "Any route adjustments needed?" -> call, check recommendations list
        """
        try:
            data = await dispatch_get("/api/v1/route")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_amtrak",
        annotations={
            "title": "Get Amtrak Status at Washington Union Station",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_amtrak() -> str:
        """Get current Amtrak train status at Washington Union Station (WAS/WASH).

        Returns arrival and departure status for trains at WAS. Covers Acela and
        NE Regional services on the NEC corridor. Requires AMTRAK_FEED_URL to be
        configured on the Pi (push-primary ingest or poller fallback).

        Returns:
            str: JSON object with 'trains' list. Each train:
                train_number (str), route_name (str), direction (str: NORTH/SOUTH),
                scheduled_time (str), estimated_time (str|null), status (str),
                delay_minutes (int), platform (str|null), last_updated (str).

        Examples:
            - "Is the Acela arriving on time?" -> call, filter route_name by 'Acela'
            - "How delayed is train 95?" -> call, find by train_number, check delay_minutes
        """
        try:
            data = await dispatch_get("/api/v1/amtrak")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_brief",
        annotations={
            "title": "Get Daily Operational Brief",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_brief() -> str:
        """Get the AI-generated daily operational brief for CS Executive Services.

        Synthesizes TFR status, weather, CPS score, NWS alerts, and ATCSCC ops plan
        into a concise executive brief suitable for morning standup or client briefing.
        Brief is cached and regenerated periodically by the poller.

        Returns:
            str: JSON object with:
                brief_text (str: full plain-language brief),
                generated_at (str: ISO timestamp),
                cps_state (str: GO/CAUTION/NO-GO at brief generation time),
                tfr_count (int),
                alert_count (int).

        Examples:
            - "What's the daily brief?" -> call, return brief_text to user
            - "Summarize today's operational picture" -> call, synthesize brief_text
        """
        try:
            data = await dispatch_get("/api/v1/brief")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_opsplan",
        annotations={
            "title": "Get ATCSCC National Ops Plan",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_opsplan() -> str:
        """Get the current FAA ATCSCC National Operations Plan snapshot.

        Returns the current day's ATCSCC ops plan from aviationweather.gov/node/1,
        which includes ground delay programs, ground stops, miles-in-trail
        restrictions, and other national ATCSCC advisories.

        Returns:
            str: JSON object with:
                snapshot_time (str: ISO timestamp),
                programs (list[dict]): each entry has type, facility, reason,
                    avg_delay_minutes, scope, start_time, end_time.
                raw_text (str: full ops plan text).

        Examples:
            - "Are there any ground delays at IAD?" -> call, filter programs by facility
            - "What's the ATCSCC situation today?" -> call, return programs list
        """
        try:
            data = await dispatch_get("/api/v1/opsplan")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_runsheet",
        annotations={
            "title": "Get Active Trip Runsheet",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_get_runsheet() -> str:
        """Get the active trip runsheet for today's chauffeur operations.

        NOTE: This endpoint is Tier 1 — it requires Tailscale network access
        (100.x.x.x range) or will return 403. Set DISPATCH_BASE_URL to the
        Tailscale address (http://100.94.80.100:8000) to access this endpoint.

        Returns:
            str: JSON object with 'trips' list. Each trip includes:
                trip_id (str), client_name (str), pickup_time (str),
                pickup_location (str), destination (str), notes (str),
                status (str: PENDING/ACTIVE/COMPLETE).
                Returns 403 error if not on Tailscale.

        Examples:
            - "What trips do we have today?" -> call (requires Tailscale)
            - "What time is the first pickup?" -> call, find earliest pickup_time
        """
        try:
            data = await dispatch_get("/api/v1/runsheet", auth=True)
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    # ---------------------------------------------------------------------------
    # Watchlist
    # ---------------------------------------------------------------------------

    @mcp.tool(
        name="dispatch_watchlist_get",
        annotations={
            "title": "Get VIP Watchlist Sessions",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_watchlist_get() -> str:
        """Get all active VIP watchlist sessions from the dispatch platform.

        The watchlist tracks flights, persons, or other subjects of interest.
        Active sessions receive automatic ntfy push alerts when tracked events occur.

        Returns:
            str: JSON list of watchlist session objects. Each session:
                session_id (str), session_type (str), subject (str),
                hex (str|null), registration (str|null),
                destination_icao (str|null), created_at (str), last_updated (str).

        Examples:
            - "What's on the watchlist?" -> call, return sessions
            - "Is KLM651 being tracked?" -> call, filter by subject=='KLM651'
        """
        try:
            data = await dispatch_get("/api/v1/watchlist")
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_watchlist_add",
        annotations={
            "title": "Add Session to VIP Watchlist",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def dispatch_watchlist_add(params: WatchlistAddInput) -> str:
        """Add a subject to the VIP watchlist for automated dispatch monitoring.

        Creates a new watchlist session. For flight tracking, provide the confirmed
        ICAO hex address (use flight_get_by_callsign or flight_get_by_registration
        to resolve hex before adding). The dispatch poller will send ntfy push
        alerts for tracked events.

        Args:
            params (WatchlistAddInput):
                - session_type (str): 'flight', 'ground', or 'person'
                - subject (str): Human label, e.g. 'KLM651' or 'POTUS'
                - hex (str, optional): ICAO 24-bit hex, required for flight sessions
                - registration (str, optional): Aircraft tail number
                - destination_icao (str, optional): 4-letter ICAO airport code

        Returns:
            str: JSON with new session_id on success, or error string.

        Examples:
            - "Start tracking KLM651" -> first resolve hex via flight_get_by_callsign,
              then call with session_type='flight', subject='KLM651', hex=<resolved>
        """
        try:
            body = params.model_dump(exclude_none=True)
            data = await dispatch_post("/api/v1/watchlist", body=body)
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_watchlist_remove",
        annotations={
            "title": "Remove Session from VIP Watchlist",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def dispatch_watchlist_remove(params: WatchlistRemoveInput) -> str:
        """Remove a session from the VIP watchlist, stopping automated monitoring.

        Provide either session_id (precise) or hex (removes all sessions for that aircraft).
        At least one of session_id or hex must be provided.

        Args:
            params (WatchlistRemoveInput):
                - session_id (str, optional): Session ID from dispatch_watchlist_get
                - hex (str, optional): ICAO hex to remove all sessions for that aircraft

        Returns:
            str: JSON confirmation or error string.

        Examples:
            - "Stop tracking KLM651" -> get hex via flight_get_by_callsign, then call with hex=<hex>
            - "Remove watchlist session abc123" -> call with session_id='abc123'
        """
        try:
            query: dict = {}
            if params.session_id:
                query["session_id"] = params.session_id
            if params.hex:
                query["hex"] = params.hex
            if not query:
                return "Error: Provide at least one of session_id or hex."
            data = await dispatch_delete("/api/v1/watchlist", params=query)
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)
