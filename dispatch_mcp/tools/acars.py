"""ACARS data tools — wraps airframes.io community ACARS aggregator.

airframes.io aggregates ACARS (VHF), VDL2, HFDL, and satellite ACARS from
volunteer ground stations worldwide. No auth required.

Primary use in the flight-hifi-track workflow:
  1. After ICAO hex is confirmed via ADS-B, call acars_get_by_hex to pull
     recent messages for that airframe.
  2. Extract departure/arrival airports from message text (H1 label, route strings).
  3. Extract OOOI events (OFF/OUT/ON/IN) for wheels-up confirmation.
  4. If neither ADS-B nor ACARS returns data, fall back to Claude's native
     web_search tool (not an MCP tool — handled at the skill level).

Endpoint:
  GET https://api.airframes.io/messages?aircraft=<ICAO_HEX>

  NOTE: The endpoint may return a global feed if the aircraft filter yields no
  results. All tools filter client-side by airframe.icao to isolate the target.

ACARS source type labels:
  acars       -> ACARS (VHF)
  vdl         -> VDL2
  hfdl        -> HFDL
  aero-acars  -> ACARS (Satellite)
  iridium-acars -> ACARS (Iridium)
"""

import re
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from mcp.server.fastmcp import FastMCP

from dispatch_mcp.client import acars_get, handle_http_error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ICAO_AIRPORT_RE = re.compile(r'\b([A-Z]{4})\b')
_OOOI_RE = re.compile(r'\b(OUT|OFF|ON |IN )\b')

_SOURCE_LABELS = {
    "acars":         "ACARS (VHF)",
    "vdl":           "VDL2",
    "hfdl":          "HFDL",
    "aero-acars":    "ACARS (Satellite)",
    "iridium-acars": "ACARS (Iridium)",
}


def _extract_route(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse origin and destination from an ACARS message text.

    Handles patterns like:
      - "KSFO,KDFW,2325"       -> KSFO, KDFW
      - "KBOS,KDCA"            -> KBOS, KDCA
      - "KMCODCA197"  (8-char) -> KMCO, KDCA (less reliable, not used)
      - "KOAKKMDW197"          -> KOAK, KMDW

    Returns (origin, destination) or (None, None) if not parseable.
    """
    if not text:
        return None, None

    # Comma-delimited pair: KXXX,KYYY  (ICAO airports, K-prefix or international)
    # Captures the first two 4-letter codes separated by a comma
    comma_match = re.search(
        r'\b([A-Z]{4}),([A-Z]{4})\b',
        text
    )
    if comma_match:
        return comma_match.group(1), comma_match.group(2)

    # 8-char concatenated pair common in ABS messages: e.g. KOAKKMDW
    concat_match = re.search(r'\b([A-Z]{4})([A-Z]{4})\d', text)
    if concat_match:
        return concat_match.group(1), concat_match.group(2)

    return None, None


def _extract_oooi(text: str) -> list[str]:
    """Find OOOI keywords in message text."""
    if not text:
        return []
    found = []
    for kw in ("OUT", "OFF", "ON", " IN "):
        if kw.strip() in text:
            found.append(kw.strip())
    return found


def _parse_messages(messages: list[dict], target_hex: str) -> dict:
    """
    Filter messages to target hex and extract structured ACARS data.

    Returns:
        {
            "message_count": int,
            "departure":     str | None,
            "destination":   str | None,
            "oooi_events":   list[str],
            "source_types":  list[str],
            "recent_texts":  list[str],   # up to 3 non-empty message texts
            "flight":        str | None,  # callsign seen in messages
        }
    """
    target = target_hex.upper()
    matched = [
        m for m in messages
        if (m.get("airframe") or {}).get("icao", "").upper() == target
    ]

    departure = None
    destination = None
    oooi_events: list[str] = []
    source_types: set[str] = set()
    recent_texts: list[str] = []
    flight = None

    for msg in matched[:30]:  # scan newest 30 matched messages
        src = msg.get("sourceType") or msg.get("source", "")
        if src:
            source_types.add(_SOURCE_LABELS.get(src, src))

        # Flight callsign
        f = (msg.get("flight") or {}).get("flight")
        if f and not flight:
            flight = f.strip()

        # Route from departingAirport / destinationAirport fields
        dep_field = msg.get("departingAirport")
        dst_field = msg.get("destinationAirport")
        if dep_field and not departure:
            departure = dep_field
        if dst_field and not destination:
            destination = dst_field

        # Route from message text
        text = (msg.get("text") or "").strip()
        if text:
            if len(recent_texts) < 3:
                recent_texts.append(text[:200])
            if not (departure and destination):
                orig, dest = _extract_route(text)
                if orig and not departure:
                    departure = orig
                if dest and not destination:
                    destination = dest

        # OOOI events
        for ev in _extract_oooi(text):
            if ev not in oooi_events:
                oooi_events.append(ev)

    return {
        "message_count": len(matched),
        "departure":     departure,
        "destination":   destination,
        "oooi_events":   oooi_events,
        "source_types":  sorted(source_types),
        "recent_texts":  recent_texts,
        "flight":        flight,
    }


def _format_acars_result(result: dict, hex_addr: str) -> str:
    count = result["message_count"]
    if count == 0:
        return (
            f"ACARS: No messages found for hex {hex_addr}. "
            "Aircraft may not be actively transmitting, or no ground station "
            "is within reception range. "
            "If ADS-B is also unavailable, use web_search fallback."
        )

    lines = [f"ACARS ({count} messages for {hex_addr})"]

    if result["flight"]:
        lines.append(f"  Callsign:    {result['flight']}")
    if result["departure"]:
        lines.append(f"  Departure:   {result['departure']}")
    if result["destination"]:
        lines.append(f"  Destination: {result['destination']}")
    else:
        lines.append("  Destination: not found in messages")
    if result["oooi_events"]:
        lines.append(f"  OOOI events: {', '.join(result['oooi_events'])}")
    if result["source_types"]:
        lines.append(f"  Sources:     {', '.join(result['source_types'])}")
    if result["recent_texts"]:
        lines.append("  Recent message text (up to 3):")
        for i, t in enumerate(result["recent_texts"], 1):
            lines.append(f"    [{i}] {t}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class AcarsHexInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    hex: str = Field(
        ...,
        description=(
            "ICAO 24-bit hex address, exactly 6 hex characters (case-insensitive). "
            "e.g. 'aa1be0', 'A1B2C3'. Obtain this from flight_get_by_registration "
            "before calling this tool."
        ),
        min_length=6,
        max_length=6,
    )

    @field_validator("hex")
    @classmethod
    def normalize_hex(cls, v: str) -> str:
        v = v.strip().upper()
        if not all(c in "0123456789ABCDEF" for c in v):
            raise ValueError(f"Invalid hex '{v}': must be 6 hex characters")
        return v


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="acars_get_by_hex",
        annotations={
            "title": "Get ACARS Messages by ICAO Hex",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": False,  # live feed; results change each call
            "openWorldHint": True,
        },
    )
    async def acars_get_by_hex(params: AcarsHexInput) -> str:
        """Query airframes.io for recent ACARS messages for a specific airframe hex.

        Use this after confirming the ICAO hex via ADS-B to:
          - Confirm destination airport (often embedded in H1-label message text)
          - Detect OOOI events (OUT/OFF/ON/IN) for wheels-up confirmation
          - Identify source type (VHF ACARS, VDL2, HFDL, satellite)

        The airframes.io endpoint may return a global feed if no messages exist
        for the requested hex. This tool always filters client-side.

        Args:
            params (AcarsHexInput):
                - hex (str): 6-character ICAO hex, e.g. 'aa1be0'

        Returns:
            str: Structured summary of matched ACARS messages:
                - Message count for this hex
                - Departure / destination airports (if found in text)
                - OOOI events detected (OUT/OFF/ON/IN)
                - Source type(s) (VHF, VDL2, HFDL, Satellite)
                - Up to 3 raw message text excerpts
                Or: guidance to use web_search fallback if no messages found.

        Workflow position:
            1. flight_get_by_callsign  -> get hex + registration
            2. flight_get_by_registration -> confirm hex
            3. acars_get_by_hex        -> destination + OOOI (this tool)
            4. flight_get_by_hex       -> live ADS-B position
            5. dispatch_watchlist_add  -> start OOOI monitoring

        Examples:
            - "Confirm destination for N750UW (aa1be0)" -> params.hex='aa1be0'
            - "Has AAL1557 taken off yet?" -> call with confirmed hex, check OOOI events for OFF
            - "Where is KLM651 going?" -> call with confirmed hex, read destination field
        """
        try:
            data = await acars_get(params.hex.lower())
            if not isinstance(data, list):
                # Some responses may be wrapped
                data = data.get("messages", []) if isinstance(data, dict) else []
            result = _parse_messages(data, params.hex)
            return _format_acars_result(result, params.hex)
        except Exception as e:
            return handle_http_error(e)
