"""Configuration for corporatetravel-dispatch-mcp.

All values are environment-variable overridable so the same server binary works
against a local Tailscale address, a public ops hostname, or a dev instance.
"""

import os

# Dispatch platform base URL.
# Default: generic placeholder — set DISPATCH_BASE_URL to your actual instance.
# Override: DISPATCH_BASE_URL env var.
# Notes:
#   - Some deployments put Cloudflare Access on POST routes; use the ops hostname for programmatic use.
#   - Tailscale addresses work on-net and bypass CF entirely.
DISPATCH_BASE_URL: str = os.environ.get(
    "DISPATCH_BASE_URL", "https://your-dispatch.your-domain"
).rstrip("/")

# Admin bearer token for /admin/* routes. Created via `csex-token create`.
# Tier 0 (/api/v1/*) endpoints work without this.
DISPATCH_TOKEN: str = os.environ.get("DISPATCH_TOKEN", "")

# airplanes.live ADS-B API base (unauthenticated).
ADSB_BASE_URL: str = "https://api.airplanes.live/v2"

# HTTP client timeouts (seconds).
DISPATCH_TIMEOUT: float = float(os.environ.get("DISPATCH_TIMEOUT", "30"))
ADSB_TIMEOUT: float = float(os.environ.get("ADSB_TIMEOUT", "15"))
