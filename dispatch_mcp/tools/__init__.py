"""Tool registration for corporatetravel-dispatch-mcp.

Call register(mcp) to attach all tools to a FastMCP instance.
"""

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, public_safe: bool = False) -> None:
    """Register tool modules against the given FastMCP instance.

    2026-08-06: public_safe (default False, preserves prior all-tools
    behavior for the existing private instance) excludes admin and
    second_brain -- neither has any per-caller authorization of its own
    (admin._check_token() only verifies this PROCESS has a token
    configured, not that the caller presented one; every outbound call to
    the dispatch API uses one fixed baked-in DISPATCH_ADMIN_TOKEN
    regardless of caller) and second_brain.remember is write-capable into
    the vault. Both are safe on a loopback-only/tailnet-only instance
    where reachability itself is the access control; neither is safe on
    an instance with a public hostname in front of it. See
    docs/COMPLIANCE_SECURITY.md for the equivalent reasoning already
    applied to the dispatch web API's own public/tailnet split.
    """
    from dispatch_mcp.tools import dispatch, flight, admin, aircraft, acars, fids, second_brain

    dispatch.register(mcp)
    flight.register(mcp)
    aircraft.register(mcp)
    acars.register(mcp)
    fids.register(mcp)
    if not public_safe:
        admin.register(mcp)
        second_brain.register(mcp)
