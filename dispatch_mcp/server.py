#!/usr/bin/env python3
"""
corporatetravel-dispatch-mcp

MCP server exposing the CS Executive Services dispatch platform and airplanes.live
flight tracking as portable, agent-agnostic tools.

Runs via stdio (default) for Claude Code, Cline, Cursor, Zed, Windsurf, and any
MCP-compatible agent. Can also run as a streamable HTTP server for mcpo → Open WebUI
integration.

Usage:
    # stdio (for Claude Code and local agents):
    dispatch-mcp

    # HTTP (for mcpo / Open WebUI):
    DISPATCH_MCP_TRANSPORT=http DISPATCH_MCP_PORT=8080 dispatch-mcp

Environment variables:
    DISPATCH_BASE_URL   Dispatch platform base URL (default: https://ops.csexecutiveservices.com)
    DISPATCH_TOKEN      Admin bearer token for /admin/* routes (create with csex-token create)
    DISPATCH_TIMEOUT    HTTP timeout in seconds for dispatch calls (default: 30)
    ADSB_TIMEOUT        HTTP timeout in seconds for airplanes.live calls (default: 15)
    DISPATCH_MCP_TRANSPORT  'stdio' or 'http' (default: stdio)
    DISPATCH_MCP_PORT       Port for HTTP transport (default: 8080)

Tool inventory (26 tools):
    Dispatch platform — Tier 0 (no auth):
        dispatch_health_check          /healthz
        dispatch_get_feeds             /api/v1/feeds
        dispatch_get_tfr               /api/v1/tfr
        dispatch_get_tfr_enriched      /api/v1/tfr-enriched
        dispatch_get_weather           /api/v1/weather
        dispatch_get_alerts            /api/v1/alerts
        dispatch_get_notams            /api/v1/notams
        dispatch_get_cps               /api/v1/cps
        dispatch_get_route             /api/v1/route
        dispatch_get_amtrak            /api/v1/amtrak
        dispatch_get_brief             /api/v1/brief
        dispatch_get_opsplan           /api/v1/opsplan
        dispatch_get_runsheet          /api/v1/runsheet  (Tailscale-only)

    Dispatch platform — Watchlist:
        dispatch_watchlist_get         /api/v1/watchlist  GET
        dispatch_watchlist_add         /api/v1/watchlist  POST
        dispatch_watchlist_remove      /api/v1/watchlist  DELETE

    FAA Aircraft Registry (local cache, updated weekly):
        dispatch_lookup_aircraft       /api/v1/aircraft/{identifier}
        dispatch_faa_registry_status   /api/v1/aircraft-registry/status

    Admin (DISPATCH_TOKEN required):
        dispatch_admin_health          /admin/healthz
        dispatch_admin_refresh_feed    /admin/refresh-feed/{name}
        dispatch_admin_force_recompute_cps
        dispatch_admin_force_opsplan_snapshot
        dispatch_admin_send_push_alert /admin/push-test-alert
        dispatch_admin_get_audit_log   /admin/audit

    Flight tracking — airplanes.live (no auth):
        flight_get_by_callsign         /v2/callsign/{callsign}
        flight_get_by_registration     /v2/reg/{registration}
        flight_get_by_hex              /v2/hex/{hex}
"""

import os
from mcp.server.fastmcp import FastMCP
from dispatch_mcp import tools

# ---------------------------------------------------------------------------
# Server instantiation
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "dispatch_mcp",
    instructions=(
        "You are connected to the CS Executive Services dispatch platform. "
        "Use dispatch_health_check first to verify connectivity. "
        "For flight tracking, always resolve callsign -> registration -> hex before "
        "adding to watchlist (hex is airframe-bound; callsigns can be stale). "
        "Admin tools require DISPATCH_TOKEN to be set. "
        "dispatch_get_runsheet requires Tailscale network access."
    ),
)

# Register all tools
tools.register(mcp)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    transport = os.environ.get("DISPATCH_MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        port = int(os.environ.get("DISPATCH_MCP_PORT", "8080"))
        mcp.run(transport="streamable-http", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
