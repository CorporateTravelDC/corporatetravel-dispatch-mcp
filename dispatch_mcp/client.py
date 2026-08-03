"""Shared HTTP client utilities for corporatetravel-dispatch-mcp.

Centralizes auth headers, User-Agent, timeout, and error formatting so tool
implementations stay focused on response parsing rather than transport concerns.
"""

from typing import Any, Optional
import httpx

from dispatch_mcp.config import (
    DISPATCH_BASE_URL,
    DISPATCH_FALLBACK_URL,
    DISPATCH_TOKEN,
    ADSB_BASE_URL,
    ACARS_BASE_URL,
    DISPATCH_TIMEOUT,
    ADSB_TIMEOUT,
    ACARS_TIMEOUT,
)

# Exceptions that mean "couldn't even reach the server" -- worth failing over.
# Deliberately excludes httpx.HTTPStatusError: a 401/403/404/429/5xx means the
# server DID answer, so retrying the same request against a different base URL
# wouldn't fix an auth/routing/rate-limit problem and could mask a real one.
_TRANSPORT_FAILURES = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException)


async def _request_with_failover(method: str, path: str, **kwargs) -> "httpx.Response":
    """Try DISPATCH_BASE_URL (Tailscale by default); on transport-level failure
    only, retry once against DISPATCH_FALLBACK_URL (Cloudflare tunnel)."""
    async with httpx.AsyncClient(timeout=DISPATCH_TIMEOUT) as client:
        try:
            r = await client.request(method, f"{DISPATCH_BASE_URL}{path}", **kwargs)
            return r
        except _TRANSPORT_FAILURES:
            if not DISPATCH_FALLBACK_URL or DISPATCH_FALLBACK_URL == DISPATCH_BASE_URL:
                raise
            return await client.request(method, f"{DISPATCH_FALLBACK_URL}{path}", **kwargs)

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
    """GET from the dispatch platform (Tailscale primary, Cloudflare failback). Returns parsed JSON dict."""
    r = await _request_with_failover("GET", path, headers=_dispatch_headers(auth=auth), params=params)
    r.raise_for_status()
    return r.json()


async def dispatch_post(path: str, auth: bool = False, body: Optional[dict] = None) -> dict[str, Any]:
    """POST to the dispatch platform (Tailscale primary, Cloudflare failback).

    Note: the Cloudflare tunnel has Access gating on POST routes -- a failback
    attempt here may still 401/403 rather than succeed. That's expected and
    still preferable to never trying a second path at all.
    """
    r = await _request_with_failover(
        "POST", path,
        headers={**_dispatch_headers(auth=auth), "Content-Type": "application/json"},
        json=body or {},
    )
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"status": r.status_code, "text": r.text}


async def dispatch_delete(path: str, auth: bool = False, params: Optional[dict] = None) -> dict[str, Any]:
    """DELETE on the dispatch platform (Tailscale primary, Cloudflare failback). Returns parsed JSON dict."""
    r = await _request_with_failover("DELETE", path, headers=_dispatch_headers(auth=auth), params=params)
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
            f"Error: Cannot connect to {DISPATCH_BASE_URL} or its failback "
            f"{DISPATCH_FALLBACK_URL}. Verify the Pi is reachable on Tailscale "
            "and the Cloudflare tunnel is up."
        )
    return f"Error: {type(e).__name__}: {e}"
