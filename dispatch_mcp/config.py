"""Configuration for corporatetravel-dispatch-mcp.

All values are environment-variable overridable so the same server binary works
against local Tailscale, ops.csexecutiveservices.com, or a dev instance.
"""

import os

# Dispatch platform base URL.
# Default: Tailscale (http://192.0.2.10:8000) -- on-net, bypasses CF entirely,
# and matches the default every other platform component (dispatch-runner,
# acars_watcher, ais_watcher) already uses.
# Override: DISPATCH_BASE_URL env var.
# Notes:
#   - ops.csexecutiveservices.com was the prior default (chosen to avoid the
#     Cloudflare Access gate dispatch.csexecutiveservices.com has on POST
#     routes) but is misrouted to the corporatetraveldc-runner (frontend SPA)
#     container, not the FastAPI web API: /healthz there returns a bogus
#     {"service": "dispatch-runner"} payload, and every /api/v1/* route just
#     serves index.html (SPA fallback), which fails JSON parsing with
#     "Expecting value: line 1 column 1 (char 0)". Fixed 2026-07-17 -- do not
#     revert to ops.csexecutiveservices.com until that DNS/tunnel routing is
#     actually corrected upstream.
#   - dispatch.csexecutiveservices.com has Cloudflare Access on POST routes;
#     fine for GET-only Tier 0 tools, avoid for admin/mutation tools.
DISPATCH_BASE_URL: str = os.environ.get(
    "DISPATCH_BASE_URL", "http://192.0.2.10:8000"
).rstrip("/")

# Fallback base URL, tried only when DISPATCH_BASE_URL fails at the transport
# level (connection refused/timeout -- Tailscale unreachable, laptop off-net,
# DERP hiccup). Never used to retry an HTTP-level error (401/403/404/429/5xx)
# from a server that DID answer -- that's not a "primary is down" signal.
# Added 2026-07-26 per operator: Tailscale stays primary/default; Cloudflare
# becomes an explicit, code-level failback instead of the two being separate
# uncoordinated defaults across different tools.
# Note: dispatch.csexecutiveservices.com has Cloudflare Access on POST routes
# -- GET/Tier-0 fallback calls should succeed, POST/admin fallback calls may
# still 401/403 there. That's a clean, informative failure, which is still
# strictly better than no fallback attempt at all.
DISPATCH_FALLBACK_URL: str = os.environ.get(
    "DISPATCH_FALLBACK_URL", "https://dispatch.csexecutiveservices.com"
).rstrip("/")

# Admin bearer token for /admin/* routes. Created via `csex-token create`.
# Tier 0 (/api/v1/*) endpoints work without this.
DISPATCH_TOKEN: str = os.environ.get("DISPATCH_TOKEN", "")

# airplanes.live ADS-B API base (unauthenticated).
ADSB_BASE_URL: str = "https://api.airplanes.live/v2"

# airframes.io ACARS aggregator (unauthenticated).
# Returns recent ACARS/VDL2/HFDL messages; filter client-side by airframe.icao.
ACARS_BASE_URL: str = os.environ.get(
    "ACARS_BASE_URL", "https://api.airframes.io/messages"
)

# HTTP client timeouts (seconds).
DISPATCH_TIMEOUT: float = float(os.environ.get("DISPATCH_TIMEOUT", "30"))
ADSB_TIMEOUT: float = float(os.environ.get("ADSB_TIMEOUT", "15"))
ACARS_TIMEOUT: float = float(os.environ.get("ACARS_TIMEOUT", "15"))
