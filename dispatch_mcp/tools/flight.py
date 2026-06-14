"""Flight tracking tools — wraps airplanes.live ADS-B API.

airplanes.live is the primary ADS-B source for all domestic and near-shore tracking.
For overwater/oceanic flights not yet in ADS-B coverage, use FR24 (Chrome MCP) as
interim source, then switch to airplanes.live on ADS-B acquisition.

Design note: Always resolve callsign -> registration -> ICAO hex before tracking.
Hex is airframe-bound; callsign-to-hex caches in airplanes.live can carry stale
associations (yesterday's aircraft on today's flight number). Use flight_get_by_hex
for live position once hex is confirmed.
"""

import json
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from mcp.server.fastmcp import FastMCP

from dispatch_mcp.client import adsb_get, handle_http_error


# ---------------------------------------------------------------------------
# Shared response formatter
# ---------------------------------------------------------------------------


def _format_ac_entry(a: dict, identifier: str) -> str:
    """Format a single aircraft entry from airplanes.live into a compact readout."""
    parts = [
        f"hex={a.get('hex', '?')}",
        f"reg={a.get('r', '?')}",
        f"type={a.get('t', '?')}",
        f"callsign={a.get('flight', '?').strip()}",
    ]
    # Position
    lat = a.get("lat")
    lon = a.get("lon")
    if lat is not None and lon is not None:
        parts.append(f"lat={lat:.5f} lon={lon:.5f}")

    # Altitude
    alt_baro = a.get("alt_baro")
    alt_geom = a.get("alt_geom")
    if alt_baro == "ground":
        parts.append("alt=GROUND")
    elif alt_baro is not None:
        parts.append(f"alt_baro={alt_baro}ft")
        if alt_geom is not None:
            parts.append(f"alt_geom={alt_geom}ft")

    # Kinematics
    gs = a.get("gs")
    track = a.get("track")
    baro_rate = a.get("baro_rate")
    if gs is not None:
        parts.append(f"gs={gs}kts")
    if track is not None:
        parts.append(f"hdg={track}")
    if baro_rate is not None:
        parts.append(f"baro_rate={baro_rate:+}fpm")

    # Signal quality
    seen = a.get("seen")
    rssi = a.get("rssi")
    if seen is not None:
        parts.append(f"seen={seen}s_ago")
    if rssi is not None:
        parts.append(f"rssi={rssi}dBFS")

    # Squawk
    squawk = a.get("squawk")
    if squawk:
        parts.append(f"squawk={squawk}")

    # Nav accuracy
    nic = a.get("nic")
    rc = a.get("rc")
    if nic is not None:
        parts.append(f"nic={nic}")
    if rc is not None:
        parts.append(f"rc={rc}m")

    return " | ".join(parts)


def _format_ac_list(data: dict, identifier: str) -> str:
    """Format the airplanes.live response to a readable string."""
    ac_list = data.get("ac", [])
    if not ac_list:
        return (
            f"No aircraft found for '{identifier}'. "
            "Flight may be on ground, out of ADS-B coverage, or overwater. "
            "For overwater flights use FR24 via Chrome MCP as interim position source."
        )
    lines = []
    for ac in ac_list:
        lines.append(_format_ac_entry(ac, identifier))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class CallsignInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    callsign: str = Field(
        ...,
        description=(
            "ICAO callsign, e.g. 'KLM651', 'UAL925', 'AAL100'. "
            "Normalize airline codes to ICAO 3-letter: KL->KLM, UA->UAL, AA->AAL, "
            "BA->BAW, DL->DAL, AF->AFR, LH->DLH."
        ),
        min_length=3,
        max_length=8,
    )

    @field_validator("callsign")
    @classmethod
    def normalize_callsign(cls, v: str) -> str:
        return v.strip().upper()


class RegistrationInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    registration: str = Field(
        ...,
        description=(
            "Aircraft tail/registration number, e.g. 'N12345', 'PH-BKB', 'G-EUYA'. "
            "No spaces. US registrations start with N."
        ),
        min_length=2,
        max_length=12,
    )

    @field_validator("registration")
    @classmethod
    def normalize_reg(cls, v: str) -> str:
        return v.strip().upper().replace(" ", "")


class HexInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    hex: str = Field(
        ...,
        description=(
            "ICAO 24-bit hex address, exactly 6 uppercase hex characters, e.g. '484150', 'A1B2C3'. "
            "This is the most reliable identifier — airframe-bound, not reused like callsigns."
        ),
        min_length=6,
        max_length=6,
    )

    @field_validator("hex")
    @classmethod
    def normalize_hex(cls, v: str) -> str:
        v = v.strip().upper()
        if not all(c in "0123456789ABCDEF" for c in v):
            raise ValueError(f"Invalid hex '{v}': must be 6 hex characters (0-9, A-F)")
        return v


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="flight_get_by_callsign",
        annotations={
            "title": "Get Flight Position by Callsign",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def flight_get_by_callsign(params: CallsignInput) -> str:
        """Get current ADS-B position for a flight by ICAO callsign via airplanes.live.

        WARNING: Callsign-to-hex mapping can be stale (yesterday's aircraft on
        today's flight number). After getting the hex from this call, verify it with
        flight_get_by_registration to confirm the physical airframe. Use the confirmed
        hex for all subsequent queries and watchlist entries.

        Args:
            params (CallsignInput):
                - callsign (str): ICAO 3-letter callsign, e.g. 'KLM651', 'UAL925'
                  (normalize: KL->KLM, UA->UAL, AA->AAL, BA->BAW, DL->DAL)

        Returns:
            str: Pipe-delimited aircraft state line:
                hex | reg | type | callsign | lat lon | alt_baro | gs | hdg | baro_rate
                | seen_ago | rssi | squawk | nic | rc
                Or: "No aircraft found" message with guidance for overwater flights.

        Examples:
            - "Where is KLM651 right now?" -> params.callsign='KLM651'
            - "Track UAL925" -> params.callsign='UAL925', then verify hex via registration
        """
        try:
            data = await adsb_get(f"/callsign/{params.callsign}")
            return _format_ac_list(data, params.callsign)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="flight_get_by_registration",
        annotations={
            "title": "Get Flight Position by Registration / Tail Number",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def flight_get_by_registration(params: RegistrationInput) -> str:
        """Get ADS-B position and ICAO hex for an aircraft by tail/registration number.

        Registration is airframe-bound, making this the preferred way to confirm
        ICAO hex before adding to watchlist. airplanes.live returns the aircraft's
        database entry including hex even when the aircraft is not currently transmitting.

        Args:
            params (RegistrationInput):
                - registration (str): Tail number, e.g. 'N12345', 'PH-BKB', 'G-EUYA'

        Returns:
            str: Pipe-delimited aircraft state line including confirmed hex.
                Or: "No aircraft found" message (aircraft may be on ground or not in DB).

        Examples:
            - "What's the hex for N12345?" -> params.registration='N12345', extract hex from result
            - "Confirm the aircraft on KLM651 is PH-BKB" -> call with PH-BKB, verify hex matches callsign result
        """
        try:
            data = await adsb_get(f"/reg/{params.registration}")
            return _format_ac_list(data, params.registration)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="flight_get_by_hex",
        annotations={
            "title": "Get Flight Position by ICAO Hex Address",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def flight_get_by_hex(params: HexInput) -> str:
        """Get current ADS-B position for an aircraft by confirmed ICAO 24-bit hex address.

        Hex queries are the most reliable — they bypass callsign privacy filters and
        avoid stale callsign-to-hex associations. Use this for all position polls once
        hex has been confirmed via flight_get_by_registration.

        Args:
            params (HexInput):
                - hex (str): 6-character uppercase hex, e.g. '484150', 'A1B2C3'

        Returns:
            str: Pipe-delimited aircraft state line with full telemetry, or
                "No aircraft found" (overwater, ground, or hex not in ADS-B coverage).

        Examples:
            - "Poll position for hex 484150" -> params.hex='484150'
            - "Is hex A1B2C3 still airborne?" -> call, check alt field
        """
        try:
            data = await adsb_get(f"/hex/{params.hex}")
            return _format_ac_list(data, params.hex)
        except Exception as e:
            return handle_http_error(e)
