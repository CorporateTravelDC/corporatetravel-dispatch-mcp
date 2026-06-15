"""FAA aircraft registry tools — wraps /api/v1/aircraft/* dispatch endpoints.

The dispatch platform caches the full FAA Releasable Aircraft Database weekly.
These tools allow offline N-number → hex resolution and LADD status checks
without hitting airplanes.live for every lookup.

LADD flag means the owner has opted into the FAA's Limited Aircraft Data
Dissemination program — their position data will NOT appear in public ADS-B
feeds (airplanes.live, FR24, etc.), which explains "No aircraft found" returns
for N-numbers that do exist in the registry.
"""

import json
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from mcp.server.fastmcp import FastMCP

from dispatch_mcp.client import dispatch_get, handle_http_error


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class AircraftLookupInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    identifier: str = Field(
        ...,
        description=(
            "N-number (e.g. 'N12345', '12345') or ICAO 24-bit hex address "
            "(e.g. 'a1b2c3'). Leading 'N' on N-numbers is optional."
        ),
        min_length=4,
        max_length=10,
    )

    @field_validator("identifier")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip().upper()


# ---------------------------------------------------------------------------
# Response formatter
# ---------------------------------------------------------------------------

_TYPE_AIRCRAFT_LABELS = {
    "1": "Glider",
    "2": "Balloon",
    "3": "Blimp/Dirigible",
    "4": "Fixed Wing Single Engine",
    "5": "Fixed Wing Multi Engine",
    "6": "Rotorcraft",
    "7": "Weight-Shift-Control",
    "8": "Powered Parachute",
    "9": "Gyroplane",
    "H": "Hybrid Lift",
    "O": "Other",
}

_TYPE_ENGINE_LABELS = {
    "0": "None",
    "1": "Reciprocating",
    "2": "Turbo-prop",
    "3": "Turbo-shaft",
    "4": "Turbo-jet",
    "5": "Turbo-fan",
    "6": "Ramjet",
    "7": "2-Cycle",
    "8": "4-Cycle",
    "9": "Unknown",
    "10": "Electric",
    "11": "Rotary",
}

_STATUS_LABELS = {
    "V": "Valid",
    "D": "Deregistered",
    "N": "Not Manufactured",
    "X": "Expired",
    "S": "Switched",
}


def _format_aircraft_record(data: dict) -> str:
    """Format an FAA registry record into a compact, readable string."""
    n     = data.get("n_number") or "?"
    hex_  = data.get("mode_s_hex") or "unknown"
    name  = data.get("registrant_name") or "?"
    city  = data.get("city") or ""
    state = data.get("state") or ""
    location = f"{city}, {state}".strip(", ") if (city or state) else "?"
    year  = data.get("year_mfr") or "?"
    mfr   = data.get("mfr_mdl_code") or "?"
    serial = data.get("serial_number") or "?"
    status_code = data.get("status_code") or "?"
    status = _STATUS_LABELS.get(status_code, status_code)
    ta_code = data.get("type_aircraft") or "?"
    ta = _TYPE_AIRCRAFT_LABELS.get(ta_code, ta_code)
    te_code = data.get("type_engine") or "?"
    te = _TYPE_ENGINE_LABELS.get(te_code, te_code)
    exp = data.get("expiration_date") or "?"
    ladd = data.get("ladd", False)

    lines = [
        f"N-Number:      N{n}",
        f"ICAO hex:      {hex_}",
        f"Registrant:    {name}",
        f"Location:      {location}",
        f"Year Mfr:      {year}",
        f"Model code:    {mfr}",
        f"Serial:        {serial}",
        f"Aircraft type: {ta} ({ta_code})",
        f"Engine type:   {te} ({te_code})",
        f"Status:        {status} ({status_code})",
        f"Expires:       {exp}",
        f"LADD / Privacy:{' YES — position data suppressed in public ADS-B feeds' if ladd else ' No'}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="dispatch_lookup_aircraft",
        annotations={
            "title": "Look Up Aircraft in FAA Registry Cache",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def dispatch_lookup_aircraft(params: AircraftLookupInput) -> str:
        """Look up an aircraft by N-number or ICAO hex from the dispatch platform's
        local FAA registry cache (updated weekly from the FAA releasable database).

        Use this tool to:
        - Resolve an N-number to its ICAO hex address without hitting airplanes.live
        - Check if an aircraft is on the FAA LADD privacy list (explains ADS-B silence)
        - Confirm registrant, location, aircraft type, and registration status

        Args:
            params (AircraftLookupInput):
                - identifier (str): N-number ('N12345' or '12345') or ICAO hex ('a1b2c3')

        Returns:
            str: Formatted registration record including N-number, ICAO hex, registrant,
                 location, aircraft/engine type, registration status, expiry, and LADD flag.
                 Returns 503 if registry has not been imported yet (first import Monday 02:00 ET).
                 Returns 404 if identifier not found.

        Examples:
            - "What's the hex for N757AF?" -> params.identifier='N757AF'
            - "Who owns a1b2c3?" -> params.identifier='a1b2c3'
            - "Is N12345 on the LADD list?" -> params.identifier='N12345', check ladd field
        """
        try:
            data = await dispatch_get(f"/api/v1/aircraft/{params.identifier}")
            return _format_aircraft_record(data)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_faa_registry_status",
        annotations={
            "title": "FAA Registry Import Status",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def dispatch_faa_registry_status() -> str:
        """Return the status of the local FAA aircraft registry cache.

        Shows how many records are loaded, how many valid registrations,
        how many LADD privacy entries, and when the last weekly import ran.

        Returns:
            str: Registry stats — total records, valid count, LADD count, last import time.

        Examples:
            - "Is the FAA registry loaded?" -> call, check total field
            - "When was the FAA database last updated?" -> call, check last_updated
        """
        try:
            data = await dispatch_get("/api/v1/aircraft-registry/status")
            total = data.get("total", 0)
            valid = data.get("valid", 0)
            ladd  = data.get("ladd", 0)
            last  = data.get("last_updated") or "Never — first import runs Monday 02:00 ET"
            return (
                f"FAA Registry Cache\n"
                f"  Total records:   {total:,}\n"
                f"  Valid (status V):{valid:,}\n"
                f"  LADD entries:    {ladd:,}\n"
                f"  Last import:     {last}"
            )
        except Exception as e:
            return handle_http_error(e)
