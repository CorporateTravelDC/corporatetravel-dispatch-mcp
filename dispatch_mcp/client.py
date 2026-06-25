"""Shared HTTP client utilities for corporatetravel-dispatch-mcp.

Centralizes auth headers, User-Agent, timeout, and error formatting so tool
implementations stay focused on response parsing rather than transport concerns.
"""

from typing import Any, Optional
import httpx

from dispatch_mcp.config import (
    DISPATCH_BASE_URL,
    DISPATCH_TOKEN,
    ADSB_BASE_URL,
    ACARS_BASE_URL,
    DISPATCH_TIMEOUT,
    ADSB_TIMEOUT,
    ACARS_TIMEOUT,
)

_DISPATCH_HEADERS = {
    "User-Agent": "corporatetravel-dispatch-mcp/0.1.0",
    "Accept": "application/json",
}

_ADSB_HEADERS = {
    "User-Agent": "corporatetravel-dispatch-mcp/0.1.0",
    "Accept": "application/json",
}


def _dispatch_headers(auth: bool = False) -> dict[str, str]:
    """Return headers for dispatch platform requests, optionally with bearer token."""
    h = dict(_DISPATCH_HEADERS)
    if auth and DISPATCH_TOKEN:
        h["Authorization"] = f"Bearer {DISPATCH_TOKEN}"
    return h


async def dispatch_get(path: str, auth: bool = False, params: Optional[dict] = None) -> dict[str, Any]:
    """GET from the dispatch platform. Returns parsed JSON dict."""
    url = f"{DISPATCH_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=DISPATCH_TIMEOUT) as client:
        r = await client.get(url, headers=_dispatch_headers(auth=auth), params=params)
        r.raise_for_status()
        return r.json()


async def dispatch_post(path: str, auth: bool = False, body: Optional[dict] = None) -> dict[str, Any]:
    """POST to the dispatch platform. Returns parsed JSON dict."""
    url = f"{DISPATCH_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=DISPATCH_TIMEOUT) as client:
        r = await client.post(
            url,
            headers={**_dispatch_headers(auth=auth), "Content-Type": "application/json"},
            json=body or {},
        )
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {"status": r.status_code, "text": r.text}


async def dispatch_delete(path: str, auth: bool = False, params: Optional[dict] = None) -> dict[str, Any]:
    """DELETE on the dispatch platform. Returns parsed JSON dict."""
    url = f"{DISPATCH_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=DISPATCH_TIMEOUT) as client:
        r = await client.delete(url, headers=_dispatch_headers(auth=auth), params=params)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {"status": r.status_code, "text": r.text}


async def adsb_get(path: str) -> dict[str, Any]:
    """GET from airplanes.live ADS-B API. Returns parsed JSON dict."""
    url = f"{ADSB_BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=ADSB_TIMEOUT) as client:
        r = await client.get(url, headers=_ADSB_HEADERS)
        r.raise_for_status()
        return r.json()


_ACARS_HEADERS = {
    "User-Agent": "corporatetravel-dispatch-mcp/0.1.0",
    "Accept": "application/json",
}


async def acars_get(hex_addr: str) -> list[Any]:
    """GET ACARS messages from airframes.io for a specific ICAO hex.

    Returns a list of message objects. The endpoint may return a global feed
    if no messages exist for the hex; callers must filter client-side by
    airframe.icao.
    """
    url = ACARS_BASE_URL
    async with httpx.AsyncClient(timeout=ACARS_TIMEOUT) as client:
        r = await client.get(
            url,
            headers=_ACARS_HEADERS,
            params={"aircraft": hex_addr.lower()},
        )
        r.raise_for_status()
        data = r.json()
        # Response may be a bare list or wrapped dict
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("messages", [])
        return []


def handle_http_error(e: Exception) -> str:
    """Convert HTTP or network exceptions to actionable error strings."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 401:
            return "Error 401: Unauthorized. Set DISPATCH_TOKEN env var with a valid admin token."
        if code == 403:
            return (
                "Error 403: Forbidden. This endpoint may require Tailscale network access "
                "or a valid bearer token. Check that DISPATCH_TOKEN is set for admin routes."
            )
        if code == 404:
            return "Error 404: Resource not found. Verify the feed name or resource identifier."
        if code == 429:
            return "Error 429: Rate limited. Wait before retrying."
        return f"Error {code}: {e.response.text[:200]}"
    if isinstance(e, httpx.TimeoutException):
        return f"Error: Request timed out after {DISPATCH_TIMEOUT}s. The dispatch platform may be unreachable."
    if isinstance(e, httpx.ConnectError):
        return (
            f"Error: Cannot connect to {DISPATCH_BASE_URL}. "
            "Verify the Pi is reachable and DISPATCH_BASE_URL is correct."
        )
    return f"Error: {type(e).__name__}: {e}"
