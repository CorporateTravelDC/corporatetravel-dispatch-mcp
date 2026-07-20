"""Airport FIDS tools — wraps the dispatch platform's MWAA gate/baggage endpoint
and (2026-07-20) the layered SWIM/website/AeroAPI arrivals resolver.

The dispatch platform polls flyreagan.com (DCA) and flydulles.com (IAD) every 60s
and exposes the data via /api/v1/fids/{airport} and /api/v1/fids/{airport}/{flight}.
A separate /api/v1/fids/{airport}/arrivals route (dispatch_get_fids_arrivals below)
covers DCA/IAD/BWI via a three-tier resolver: FAA SWIM primary, MWAA website
fallback (DCA/IAD only), FlightAware AeroAPI fallback (all three hubs).

Discovery (2026-06-24):
  - No headless browser required -- Cookie: flight-info=1 is sufficient
  - DCA: https://www.flyreagan.com/arrivals-and-departures/json
  - IAD: https://www.flydulles.com/arrivals-and-departures/json
  - Both airports supported; BWI is not MWAA -- see dispatch_get_fids_arrivals
    for how BWI is covered instead (AeroAPI, and SWIM once flight_events is
    reliably populated).

Key fields returned: gate, terminal, baggage carousel, status, estimated arrival,
remaining flight time, tail number, dep_airport, dep_gate.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from mcp.server.fastmcp import FastMCP

from dispatch_mcp.client import dispatch_get, handle_http_error


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class FidsAirportInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    airport: str = Field(
        ...,
        description="Airport code: 'DCA' (Reagan National) or 'IAD' (Dulles).",
    )

    @field_validator("airport")
    @classmethod
    def normalize_airport(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("DCA", "IAD"):
            raise ValueError(f"airport must be 'DCA' or 'IAD', got '{v}'")
        return v


class FidsFlightInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    airport: str = Field(
        ...,
        description="Airport code: 'DCA' or 'IAD'.",
    )
    flight: str = Field(
        ...,
        description=(
            "IATA carrier code + flight number, e.g. 'AA1557', 'UA928', 'DL404'. "
            "No spaces. Case-insensitive."
        ),
        min_length=3,
        max_length=10,
    )
    date: Optional[str] = Field(
        default=None,
        description="Date filter YYYY-MM-DD. Defaults to today if omitted.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )

    @field_validator("airport")
    @classmethod
    def normalize_airport(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("DCA", "IAD"):
            raise ValueError(f"airport must be 'DCA' or 'IAD', got '{v}'")
        return v

    @field_validator("flight")
    @classmethod
    def normalize_flight(cls, v: str) -> str:
        return v.strip().upper().replace(" ", "")


class FidsArrivalsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    airport: str = Field(
        ...,
        description="Airport code: 'DCA' (Reagan National), 'IAD' (Dulles), or 'BWI' (Baltimore/Washington).",
    )
    carriers: Optional[str] = Field(
        default=None,
        description=(
            "Comma-separated IATA carrier codes to filter by, e.g. 'AA,UA'. "
            "Omit for all carriers."
        ),
    )
    within_minutes: int = Field(
        default=90,
        ge=1,
        le=720,
        description="Forward-looking window in minutes (default 90).",
    )

    @field_validator("airport")
    @classmethod
    def normalize_airport(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("DCA", "IAD", "BWI"):
            raise ValueError(f"airport must be 'DCA', 'IAD', or 'BWI', got '{v}'")
        return v


# ---------------------------------------------------------------------------
# Response formatters
# ---------------------------------------------------------------------------


def _format_fids_flight(data: dict) -> str:
    """Format a single FIDS flight record into a readable string."""
    lines = [
        f"FIDS: {data.get('iata','?')}{data.get('flight_number','?')} -- {data.get('airport','?')}",
        f"  Status:      {data.get('status', '?')}",
        f"  Gate:        {data.get('gate') or 'TBD'}",
        f"  Terminal:    {data.get('terminal') or '?'}",
        f"  Baggage:     Carousel {data.get('baggage') or 'TBD'}",
        f"  Scheduled:   {data.get('scheduled') or '?'}",
        f"  Estimated:   {data.get('estimated') or '?'}",
        f"  Remaining:   {data.get('remaining') or 'n/a'}",
        f"  Tail:        {data.get('tail') or '?'}",
        f"  Dep airport: {data.get('dep_airport') or '?'}",
        f"  Dep gate:    {data.get('dep_gate') or '?'}",
        f"  Dep term:    {data.get('dep_terminal') or '?'}",
    ]
    return "\n".join(lines)


def _format_fids_snapshot(data: dict) -> str:
    return (
        f"FIDS snapshot -- {data.get('airport','?')}\n"
        f"  Arrivals:    {data.get('arrivals_count', 0)}\n"
        f"  Departures:  {data.get('departures_count', 0)}\n"
        f"  As of:       {data.get('ts','?')}"
    )


def _format_fids_arrivals(data: dict) -> str:
    airport = data.get("airport", "?")
    source_used = data.get("source_used", "?")
    results = data.get("results") or []
    note = data.get("note")

    lines = [f"Arrivals -- {airport} (source: {source_used}, {len(results)} matching)"]
    for r in results:
        carrier = r.get("carrier") or r.get("airline") or "?"
        flight_num = r.get("flight_num") or "?"
        origin = r.get("origin") or "?"
        status = r.get("status") or "?"
        sched = r.get("scheduled") or "?"
        extra = ""
        if r.get("gate"):
            extra += f" gate {r['gate']}"
        if r.get("terminal"):
            extra += f" T{r['terminal']}"
        if r.get("baggage_claim"):
            extra += f" claim {r['baggage_claim']}"
        lines.append(f"  {carrier} {flight_num}  from {origin}  {sched}  {status}{extra}")
    if not results:
        lines.append("  (no matching flights in this window)")
    if note:
        lines.append(f"Note: {note}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="dispatch_get_fids_flight",
        annotations={
            "title": "Get Gate and Baggage Carousel for an Arrival",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def dispatch_get_fids_flight(params: FidsFlightInput) -> str:
        """Get confirmed gate, baggage carousel, and arrival status for a specific flight
        at DCA (Reagan National) or IAD (Dulles) from the MWAA FIDS.

        Data is sourced from flyreagan.com (DCA) and flydulles.com (IAD), updated
        every 60 seconds by the dispatch platform poller. Confirmed carousel numbers
        are marked [FIDS] in baggage push notifications.

        Args:
            params (FidsFlightInput):
                - airport (str): 'DCA' or 'IAD'
                - flight (str): IATA carrier + number e.g. 'AA1557', 'UA928'
                - date (str, optional): 'YYYY-MM-DD' -- defaults to today

        Returns:
            str: Formatted arrival details:
                status, gate, terminal, baggage carousel, scheduled/estimated times,
                remaining flight time, tail number, departure info.
                Returns 404 message if flight not found in FIDS.
                Returns 503 if dispatch platform is unreachable.

        Examples:
            - "What carousel is AA1557 at DCA?" -> airport='DCA', flight='AA1557'
            - "What gate for UA928 at IAD?" -> airport='IAD', flight='UA928'
            - "Is DL404 at DCA running on time?" -> airport='DCA', flight='DL404', check status
        """
        path = f"/api/v1/fids/{params.airport}/{params.flight}"
        req_params = {}
        if params.date:
            req_params["date"] = params.date
        try:
            data = await dispatch_get(path, params=req_params if req_params else None)
            return _format_fids_flight(data)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_fids_snapshot",
        annotations={
            "title": "Get FIDS Feed Snapshot for an Airport",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def dispatch_get_fids_snapshot(params: FidsAirportInput) -> str:
        """Get a health/freshness snapshot of the FIDS feed for DCA or IAD.

        Returns arrival/departure counts and cache timestamp. Use this to verify
        the FIDS feed is current before relying on gate/baggage data.

        Args:
            params (FidsAirportInput):
                - airport (str): 'DCA' or 'IAD'

        Returns:
            str: Arrivals count, departures count, and cache timestamp.

        Examples:
            - "Is the DCA FIDS feed current?" -> airport='DCA'
        """
        try:
            data = await dispatch_get(f"/api/v1/fids/{params.airport}")
            return _format_fids_snapshot(data)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_get_fids_arrivals",
        annotations={
            "title": "Get Layered Arrivals Lookup (SWIM + Website + AeroAPI)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def dispatch_get_fids_arrivals(params: FidsArrivalsInput) -> str:
        """Get forward-looking arrivals for DCA, IAD, or BWI, optionally filtered
        by carrier, within a time window.

        Uses a three-tier layered resolver on the dispatch platform:
          1. FAA SWIM (flight_events table) -- primary, all three hubs
          2. MWAA airport-website FIDS scrape -- fallback, DCA/IAD only
             (BWI is not MWAA-operated and has no equivalent free feed)
          3. FlightAware AeroAPI -- fallback, all three hubs (funded 2026-07-20)
        Each tier is only queried if the previous one returned nothing, so a
        healthy SWIM feed means AeroAPI (paid/metered) is rarely if ever called.
        The response tells you which tier actually served the data.

        Args:
            params (FidsArrivalsInput):
                - airport (str): 'DCA', 'IAD', or 'BWI'
                - carriers (str, optional): comma-separated IATA codes, e.g. 'AA,UA'
                - within_minutes (int, optional): forward-looking window, default 90

        Returns:
            str: List of matching arrivals (carrier, flight number, origin,
                status, scheduled time, gate/terminal/baggage where available),
                which source tier served the data, and a note explaining why
                (e.g. "SWIM empty, served from website fallback").

        Examples:
            - "What American and United flights are landing at Reagan in the
              next 90 minutes?" -> airport='DCA', carriers='AA,UA'
            - "Anything coming into BWI in the next hour?" -> airport='BWI',
              within_minutes=60
            - "Show me all Dulles arrivals right now" -> airport='IAD'
        """
        req_params = {"within_minutes": params.within_minutes}
        if params.carriers:
            req_params["carriers"] = params.carriers
        try:
            data = await dispatch_get(
                f"/api/v1/fids/{params.airport}/arrivals", params=req_params
            )
            return _format_fids_arrivals(data)
        except Exception as e:
            return handle_http_error(e)
