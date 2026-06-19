"""Admin tools — wraps the /admin/* routes of the dispatch platform.

All admin tools require a valid DISPATCH_TOKEN bearer token.
Create one on the Pi with: csex-token create

Admin routes are only accessible from Tailscale (100.x.x.x) or via the ops hostname
with a valid token. Some deployments put Cloudflare Access on POST routes of the public dispatch hostname.
"""

import json
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from mcp.server.fastmcp import FastMCP

from dispatch_mcp.client import dispatch_get, dispatch_post, handle_http_error
from dispatch_mcp.config import DISPATCH_TOKEN


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


VALID_FEED_NAMES = {
    "metar", "nws", "tfr", "notam", "amtrak", "atcscc_opsplan", "runsheet"
}


class RefreshFeedInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    feed_name: str = Field(
        ...,
        description=(
            "Feed to force-refresh. One of: metar, nws, tfr, notam, amtrak, "
            "atcscc_opsplan, runsheet."
        ),
    )

    @field_validator("feed_name")
    @classmethod
    def validate_feed_name(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in VALID_FEED_NAMES:
            raise ValueError(
                f"Unknown feed '{v}'. Valid feeds: {', '.join(sorted(VALID_FEED_NAMES))}"
            )
        return v


class PushAlertInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    message: str = Field(
        ...,
        description="Alert message text to push via ntfy to all subscribed topics.",
        min_length=1,
        max_length=1000,
    )
    title: Optional[str] = Field(
        default=None,
        description="Optional ntfy notification title. Defaults to 'Dispatch Alert'.",
        max_length=100,
    )
    priority: Optional[int] = Field(
        default=3,
        description="ntfy priority: 1=min, 2=low, 3=default, 4=high, 5=urgent",
        ge=1,
        le=5,
    )


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP) -> None:

    def _check_token() -> Optional[str]:
        """Return error string if DISPATCH_TOKEN is not set, else None."""
        if not DISPATCH_TOKEN:
            return (
                "Error: DISPATCH_TOKEN is not set. "
                "Admin endpoints require a bearer token. "
                "Create one on the Pi with: csex-token create "
                "Then set DISPATCH_TOKEN env var before starting the MCP server."
            )
        return None

    @mcp.tool(
        name="dispatch_admin_health",
        annotations={
            "title": "Admin Health Check (Token Required)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_admin_health() -> str:
        """Get extended admin health check for the dispatch platform (requires token).

        Returns more detailed health data than the public /healthz endpoint,
        including internal queue state, container status, and error counts.
        Requires DISPATCH_TOKEN env var to be set.

        Returns:
            str: JSON admin health object, or error string if token missing/invalid.

        Examples:
            - "Show admin health status" -> call (token required)
        """
        if err := _check_token():
            return err
        try:
            data = await dispatch_get("/admin/healthz", auth=True)
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_admin_refresh_feed",
        annotations={
            "title": "Force Refresh a Dispatch Feed (Token Required)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_admin_refresh_feed(params: RefreshFeedInput) -> str:
        """Force an immediate refresh of a specific dispatch data feed.

        Bypasses the normal polling interval and triggers an immediate fetch
        for the named feed. Useful when a feed is stale or in an error state.
        Requires DISPATCH_TOKEN env var to be set.

        Args:
            params (RefreshFeedInput):
                - feed_name (str): One of: metar, nws, tfr, notam, amtrak,
                  atcscc_opsplan, runsheet

        Returns:
            str: JSON confirmation with refresh result, or error string.

        Examples:
            - "Refresh the TFR feed" -> params.feed_name='tfr'
            - "Force weather update" -> params.feed_name='metar'
        """
        if err := _check_token():
            return err
        try:
            data = await dispatch_post(f"/admin/refresh-feed/{params.feed_name}", auth=True)
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_admin_force_recompute_cps",
        annotations={
            "title": "Force CPS Recomputation (Token Required)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_admin_force_recompute_cps() -> str:
        """Force an immediate recomputation of the Critical Predictability State (CPS).

        CPS is normally recomputed after each feed update. Use this to trigger
        recomputation immediately, e.g. after a manual feed refresh.
        Requires DISPATCH_TOKEN env var to be set.

        Returns:
            str: JSON with new CPS state and score, or error string.

        Examples:
            - "Recompute CPS now" -> call with no params
        """
        if err := _check_token():
            return err
        try:
            data = await dispatch_post("/admin/force-recompute-cps", auth=True)
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_admin_force_opsplan_snapshot",
        annotations={
            "title": "Force ATCSCC Ops Plan Snapshot (Token Required)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_admin_force_opsplan_snapshot() -> str:
        """Force an immediate ATCSCC ops plan snapshot.

        Triggers a fetch and parse of the current ATCSCC National Operations Plan
        outside the normal polling schedule.
        Requires DISPATCH_TOKEN env var to be set.

        Returns:
            str: JSON confirmation or error string.

        Examples:
            - "Force opsplan refresh" -> call with no params
        """
        if err := _check_token():
            return err
        try:
            data = await dispatch_post("/admin/force-opsplan-snapshot", auth=True)
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_admin_send_push_alert",
        annotations={
            "title": "Send Push Alert via ntfy (Token Required)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def dispatch_admin_send_push_alert(params: PushAlertInput) -> str:
        """Send a push notification via ntfy through the dispatch platform.

        Fires a notification to the configured ntfy topics on the Pi.
        Use priority 5 for urgent alerts (e.g. Marine One TFR, weather emergency).
        Requires DISPATCH_TOKEN env var to be set.

        Args:
            params (PushAlertInput):
                - message (str): Alert text, max 1000 chars
                - title (str, optional): Notification title (default: 'Dispatch Alert')
                - priority (int, optional): 1-5, default 3 (4=high, 5=urgent)

        Returns:
            str: JSON confirmation or error string.

        Examples:
            - "Send test alert" -> params.message='Test alert from MCP', priority=3
            - "Send urgent Marine One alert" -> params.message='Marine One TFR active P-56', priority=5
        """
        if err := _check_token():
            return err
        try:
            body: dict = {"message": params.message, "priority": params.priority}
            if params.title:
                body["title"] = params.title
            data = await dispatch_post("/admin/push-test-alert", auth=True, body=body)
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)

    @mcp.tool(
        name="dispatch_admin_get_audit_log",
        annotations={
            "title": "Get Audit Log (Token Required)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def dispatch_admin_get_audit_log() -> str:
        """Get the dispatch platform audit log (append-only, 90-day retention).

        Returns recent audit log entries. Log is append-only and never leaves
        the Pi. Requires DISPATCH_TOKEN env var to be set.

        Returns:
            str: JSON list of audit log entries with timestamp, action, and detail.

        Examples:
            - "Show recent audit log entries" -> call (token required)
        """
        if err := _check_token():
            return err
        try:
            data = await dispatch_get("/admin/audit", auth=True)
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)
