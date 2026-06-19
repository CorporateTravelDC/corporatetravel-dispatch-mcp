"""
dispatch_admin.py — MCP tools wrapping dispatch admin REST endpoints.

All admin endpoints require DISPATCH_TOKEN (bearer token). These tools expose
platform management operations: health diagnostics, feed refresh, CPS recompute,
ops plan snapshot, and push alert delivery.

Covered endpoints:
  GET  /admin/healthz                      → extended admin health check
  GET  /admin/feeds                        → per-feed freshness with error details
  GET  /admin/audit                        → audit log (append-only, 90-day retention)
  POST /admin/refresh-feed/{feed_name}     → force immediate feed refresh
  POST /admin/force-recompute-cps          → force CPS recomputation
  POST /admin/force-opsplan-snapshot       → force ATCSCC ops plan snapshot
  POST /admin/push-alert                   → send ntfy push notification

Valid feed names for refresh_feed():
  metar | nws | tfr | notam | amtrak | atcscc_opsplan | runsheet
"""

from __future__ import annotations

import httpx

from config import DISPATCH_URL, DISPATCH_TOKEN

_TIMEOUT = 60  # seconds — admin ops (refresh, recompute) may take longer

_VALID_FEEDS = {
    "metar",
    "nws",
    "tfr",
    "notam",
    "amtrak",
    "atcscc_opsplan",
    "runsheet",
}


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

def get_admin_health() -> dict:
    """
    Get extended admin health check for the dispatch platform.

    Returns more detailed health data than the public /healthz endpoint,
    including internal queue state, container status, and error counts.

    Requires DISPATCH_TOKEN to be set.

    Returns:
        dict with detailed admin health object including queue state,
        container status, and per-feed error counts.
    """
    with _client() as client:
        resp = client.get("/admin/healthz")
        _raise_for_status(resp, "GET /admin/healthz")
        return resp.json()


def get_admin_feeds() -> dict:
    """
    Get per-feed freshness and error details from the dispatch admin interface.

    Returns more detailed feed metadata than the public /api/v1/feeds endpoint,
    including internal error traces and poller cycle information.

    Requires DISPATCH_TOKEN to be set.

    Returns:
        dict keyed by feed name with last_updated, age_seconds, error state,
        error message, and poller metadata.
    """
    with _client() as client:
        resp = client.get("/admin/feeds")
        _raise_for_status(resp, "GET /admin/feeds")
        return resp.json()


def get_audit_log() -> dict:
    """
    Get the dispatch platform audit log (append-only, 90-day retention).

    Returns recent audit log entries. The log is append-only and never leaves
    the Pi. Entries record admin actions, feed refreshes, push alerts sent,
    CPS recomputations, and other platform events.

    Requires DISPATCH_TOKEN to be set.

    Returns:
        dict or list of audit log entries with timestamp, action, and detail.
    """
    with _client() as client:
        resp = client.get("/admin/audit")
        _raise_for_status(resp, "GET /admin/audit")
        return resp.json()


def refresh_feed(feed_name: str) -> dict:
    """
    Force an immediate refresh of a specific dispatch data feed.

    Bypasses the normal polling interval and triggers an immediate fetch
    for the named feed. Useful when a feed is stale or in an error state.

    Requires DISPATCH_TOKEN to be set.

    Args:
        feed_name: One of: metar, nws, tfr, notam, amtrak, atcscc_opsplan, runsheet.

    Returns:
        dict with refresh confirmation and result details.

    Raises:
        ValueError: If feed_name is not in the known list, or on HTTP error.
    """
    feed = feed_name.strip().lower()
    if feed not in _VALID_FEEDS:
        raise ValueError(
            f"Unknown feed '{feed}'. "
            f"Valid feed names: {', '.join(sorted(_VALID_FEEDS))}."
        )

    with _client() as client:
        resp = client.post(f"/admin/refresh-feed/{feed}")
        _raise_for_status(resp, f"POST /admin/refresh-feed/{feed}")
        return resp.json()


def force_recompute_cps() -> dict:
    """
    Force an immediate recomputation of the Critical Predictability State (CPS).

    CPS is normally recomputed after each feed update. Use this to trigger
    recomputation immediately, e.g. after a manual feed refresh.

    Requires DISPATCH_TOKEN to be set.

    Returns:
        dict with new CPS state and score after recomputation.
    """
    with _client() as client:
        resp = client.post("/admin/force-recompute-cps")
        _raise_for_status(resp, "POST /admin/force-recompute-cps")
        return resp.json()


def force_opsplan_snapshot() -> dict:
    """
    Force an immediate ATCSCC ops plan snapshot.

    Triggers a fetch and parse of the current ATCSCC National Operations Plan
    outside the normal polling schedule.

    Requires DISPATCH_TOKEN to be set.

    Returns:
        dict with confirmation of the new snapshot and its timestamp.
    """
    with _client() as client:
        resp = client.post("/admin/force-opsplan-snapshot")
        _raise_for_status(resp, "POST /admin/force-opsplan-snapshot")
        return resp.json()


def send_push_alert(
    message: str,
    title: str = "Dispatch Alert",
    priority: int = 3,
) -> dict:
    """
    Send a push notification via ntfy through the dispatch platform.

    Fires a notification to the configured ntfy topics on the Pi.
    Use priority 5 for urgent alerts (e.g. Marine One TFR, weather emergency).

    Requires DISPATCH_TOKEN to be set.

    Args:
        message:  Alert text (max ~1000 chars).
        title:    Notification title (default: 'Dispatch Alert').
        priority: ntfy priority 1-5 (1=min, 2=low, 3=default, 4=high, 5=urgent).
                  Default: 3.

    Returns:
        dict with confirmation of the push delivery.

    Raises:
        ValueError: If priority is out of range [1, 5], or on HTTP error.
    """
    if not message or not message.strip():
        raise ValueError("message must not be empty.")

    if not (1 <= priority <= 5):
        raise ValueError(
            f"priority must be between 1 and 5 (got {priority}). "
            "1=min, 2=low, 3=default, 4=high, 5=urgent."
        )

    payload = {
        "message": message.strip(),
        "title": title.strip() if title else "Dispatch Alert",
        "priority": priority,
    }

    with _client() as client:
        resp = client.post("/admin/push-alert", json=payload)
        _raise_for_status(resp, "POST /admin/push-alert")
        return resp.json()
