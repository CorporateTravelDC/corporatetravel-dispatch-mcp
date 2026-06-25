"""Airport FIDS tools — wraps the dispatch platform's MWAA gate/baggage endpoint.

The dispatch platform polls flyreagan.com (DCA) and flydulles.com (IAD) every 60s
and exposes the data via /api/v1/fids/{airport} and /api/v1/fids/{airport}/{flight}.

Discovery (2026-06-24):
  - No headless browser required -- Cookie: flight-info=1 is sufficient
  - DCA: https://www.flyreagan.com/arrivals-and-departures/json
  - IAD: https://www.flydulles.com/arrivals-and-departures/json
  - Both airports supported; BWI is not MWAA and is not wired

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
