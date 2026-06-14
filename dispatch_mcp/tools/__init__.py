"""Tool registration for corporatetravel-dispatch-mcp.

Call register(mcp) to attach all tools to a FastMCP instance.
"""

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register all tool modules against the given FastMCP instance."""
    from dispatch_mcp.tools import dispatch, flight, admin

    dispatch.register(mcp)
    flight.register(mcp)
    admin.register(mcp)
