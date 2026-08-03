"""Second-brain tools -- manual vault capture and (future) recall/search actions.

Each action lives in its own module here (remember.py today; recall.py,
search.py, etc. as they're added) and exposes register(mcp). This __init__
aggregates them, mirroring the top-level dispatch_mcp/tools/__init__.py
pattern one level down -- the same structure gig_mobility uses in
agentic-management-tooling-mcp for its own namespace of related tools.
"""
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from dispatch_mcp.tools.second_brain import remember

    remember.register(mcp)
