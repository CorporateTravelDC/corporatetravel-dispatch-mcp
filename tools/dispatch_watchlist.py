"""
dispatch_watchlist.py — MCP tools for VIP watchlist management via dispatch REST API.

The watchlist tracks flights, persons, or other subjects of interest. Active
sessions receive automatic ntfy push alerts when tracked events occur.

Auth: All endpoints require DISPATCH_TOKEN (Tier 1+).
  Authorization: Bearer {DISPATCH_TOKEN}

Covered endpoints:
  GET    /api/v1/watchlist              → list all active watchlist sessions
  POST   /api/v1/watchlist              → add a subject to the watchlist
  DELETE /api/v1/watchlist/{session_id} → remove a session from the watchlist

Standing hex-ID directive: always resolve flight#/tail# → ICAO hex before
adding a flight session. The hex field is required for session_type='flight'.
"""

from __future__ import annotations

from typing import Optional

import httpx

from config import DISPATCH_URL, DISPATCH_TOKEN

_TIMEOUT = 30  # seconds

_VALID_SESSION_TYPES = {"flight", "ground", "person"}


def _headers() -> dict[str, str]:
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    if DISPATCH_TOKEN:
        h["Authorization"] = f"Bearer {DISPATCH_TOKEN}"
    return h


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=DISPATCH_URL.rstrip("/"),
        timeout=_TIMEOUT,
        headers=_headers(),
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

def list_watchlist() -> dict:
    """
    Get all active VIP watchlist sessions from the dispatch platform.

    The watchlist tracks flights, persons, or other subjects of interest.
    Active sessions receive automatic ntfy push alerts when tracked events occur.

    Requires DISPATCH_TOKEN to be set.

    Returns:
        dict or list of watchlist session objects. Each session includes:
        session_id, session_type, subject, hex (or null), registration (or null),
        destination_icao (or null), created_at, last_updated.
    """
    with _client() as client:
        resp = client.get("/api/v1/watchlist")
        _raise_for_status(resp, "GET /api/v1/watchlist")
        return resp.json()


def add_watchlist(
    session_type: str,
    subject: str,
    hex: Optional[str] = None,
    registration: Optional[str] = None,
    destination_icao: Optional[str] = None,
) -> dict:
    """
    Add a subject to the VIP watchlist for automated dispatch monitoring.

    For flight tracking, provide the confirmed ICAO hex address. Use
    track_flight_by_callsign or track_flight_by_registration to resolve hex
    before calling this function. The dispatch poller will send ntfy push
    alerts for tracked events.

    Requires DISPATCH_TOKEN to be set.

    Args:
        session_type:     Session type — one of: 'flight', 'ground', 'person'.
        subject:          Human-readable label (e.g. 'KLM651' or 'POTUS').
        hex:              ICAO 24-bit hex address, required for session_type='flight'
                          (e.g. '484150'). Must be exactly 6 hex characters.
        registration:     Aircraft tail number (e.g. 'N12345', 'PH-BKB').
        destination_icao: Destination airport ICAO code (e.g. 'KIAD', 'KJFK').

    Returns:
        dict with new session_id on success, or raises ValueError on HTTP error.
    """
    session_type = session_type.strip().lower()
    if session_type not in _VALID_SESSION_TYPES:
        raise ValueError(
            f"Invalid session_type '{session_type}'. "
            f"Must be one of: {', '.join(sorted(_VALID_SESSION_TYPES))}."
        )

    if session_type == "flight" and not hex:
        raise ValueError(
            "hex is required for session_type='flight'. "
            "Resolve callsign or registration to ICAO hex first using "
            "track_flight_by_callsign() or track_flight_by_registration()."
        )

    if hex and len(hex.strip()) != 6:
        raise ValueError(
            f"Invalid hex '{hex}': must be exactly 6 hexadecimal characters."
        )

    payload: dict = {
        "session_type": session_type,
        "subject": subject.strip(),
    }
    if hex:
        payload["hex"] = hex.strip().lower()
    if registration:
        payload["registration"] = registration.strip().upper()
    if destination_icao:
        payload["destination_icao"] = destination_icao.strip().upper()

    with _client() as client:
        resp = client.post("/api/v1/watchlist", json=payload)
        _raise_for_status(resp, "POST /api/v1/watchlist")
        return resp.json()


def remove_watchlist(session_id: str) -> dict:
    """
    Remove a session from the VIP watchlist, stopping automated monitoring.

    Requires DISPATCH_TOKEN to be set.

    Args:
        session_id: Session ID from list_watchlist() (e.g. returned in session_id
                    field of add_watchlist() response).

    Returns:
        dict with removal confirmation, or raises ValueError on HTTP error
        (including 404 if session not found).
    """
    sid = session_id.strip()
    if not sid:
        raise ValueError("session_id must not be empty.")

    with _client() as client:
        resp = client.delete(f"/api/v1/watchlist/{sid}")
        if resp.status_code == 404:
            raise ValueError(
                f"Watchlist session '{sid}' not found (HTTP 404). "
                "Use list_watchlist() to see active sessions."
            )
        _raise_for_status(resp, f"DELETE /api/v1/watchlist/{sid}")
        return resp.json()
