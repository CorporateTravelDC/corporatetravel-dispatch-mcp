"""Configuration for corporatetravel-dispatch-mcp.

All values are environment-variable overridable so the same server binary works
against local Tailscale, ops.csexecutiveservices.com, or a dev instance.
"""

import os

# Dispatch platform base URL.
# Default: ops.csexecutiveservices.com (no Cloudflare Access gate).
# Override: DISPATCH_BASE_URL env var.
# Notes:
#   - dispatch.csexecutiveservices.com has Cloudflare Access on POST routes; prefer ops for programmatic use.
#   - Tailscale (http://100.94.80.100:8000) works on-net and bypasses CF entirely.
DISPATCH_BASE_URL: str = os.environ.get(
    "DISPATCH_BASE_URL", "https://ops.csexecutiveservices.com"
).rstrip("/")

# Admin bearer token for /admin/* routes. Created via `csex-token create`.
# Tier 0 (/api/v1/*) endpoints work without this.
DISPATCH_TOKEN: str = os.environ.get("DISPATCH_TOKEN", "")

# airplanes.live ADS-B API base (unauthenticated).
ADSB_BASE_URL: str = "https://api.airplanes.live/v2"

# HTTP client timeouts (seconds).
DISPATCH_TIMEOUT: float = float(os.environ.get("DISPATCH_TIMEOUT", "30"))
ADSB_TIMEOUT: float = float(os.environ.get("ADSB_TIMEOUT", "15"))
