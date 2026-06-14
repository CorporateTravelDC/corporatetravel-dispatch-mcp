# corporatetravel-dispatch-mcp

MCP server exposing the CS Executive Services dispatch platform and airplanes.live flight
tracking as portable, agent-agnostic tools. Works with any MCP-compatible agent: Claude Code,
Cline, Cursor, Zed, Windsurf, and others via [mcpo](./docs/mcpo-openwebui.md) → Open WebUI.

## Tools (21 total)

### Dispatch Platform — Tier 0 (no auth required)

| Tool | Endpoint | Description |
|---|---|---|
| `dispatch_health_check` | `/healthz` | Service health + snapshot ages |
| `dispatch_get_feeds` | `/api/v1/feeds` | Feed freshness and error state |
| `dispatch_get_tfr` | `/api/v1/tfr` | Active TFRs from FAA |
| `dispatch_get_tfr_enriched` | `/api/v1/tfr-enriched` | TFRs with AI threat interpretation |
| `dispatch_get_weather` | `/api/v1/weather` | DC-area METAR snapshot |
| `dispatch_get_alerts` | `/api/v1/alerts` | Active NWS weather alerts |
| `dispatch_get_notams` | `/api/v1/notams` | Active NOTAMs (requires FAA key on Pi) |
| `dispatch_get_cps` | `/api/v1/cps` | Critical Predictability State (HEMS go/no-go) |
| `dispatch_get_route` | `/api/v1/route` | Ground route impact assessment |
| `dispatch_get_amtrak` | `/api/v1/amtrak` | Amtrak status at WAS |
| `dispatch_get_brief` | `/api/v1/brief` | AI-generated daily operational brief |
| `dispatch_get_opsplan` | `/api/v1/opsplan` | ATCSCC National Operations Plan |
| `dispatch_get_runsheet` | `/api/v1/runsheet` | Active trip runsheet (**Tailscale-only**) |

### Dispatch Platform — Watchlist

| Tool | Method | Description |
|---|---|---|
| `dispatch_watchlist_get` | GET | List active VIP watchlist sessions |
| `dispatch_watchlist_add` | POST | Add flight/person to watchlist |
| `dispatch_watchlist_remove` | DELETE | Remove watchlist session |

### Admin (requires `DISPATCH_TOKEN`)

| Tool | Description |
|---|---|
| `dispatch_admin_health` | Extended health check |
| `dispatch_admin_refresh_feed` | Force-refresh a named feed |
| `dispatch_admin_force_recompute_cps` | Force CPS recomputation |
| `dispatch_admin_force_opsplan_snapshot` | Force opsplan fetch |
| `dispatch_admin_send_push_alert` | Send ntfy push notification |
| `dispatch_admin_get_audit_log` | View audit log |

### Flight Tracking — airplanes.live (no auth)

| Tool | Description |
|---|---|
| `flight_get_by_callsign` | ADS-B position lookup by ICAO callsign |
| `flight_get_by_registration` | ADS-B position + hex by tail number |
| `flight_get_by_hex` | ADS-B position by confirmed ICAO hex |

**Hex resolution order:** `callsign → registration → hex`. Always confirm hex via
`flight_get_by_registration` before adding to watchlist — hex is airframe-bound;
callsign-to-hex mappings can be stale day-over-day.

## Install

```bash
pip install -e .
```

Requires Python 3.11+.

## Configure

| Env var | Default | Notes |
|---|---|---|
| `DISPATCH_BASE_URL` | `https://ops.csexecutiveservices.com` | Use Tailscale IP for runsheet |
| `DISPATCH_TOKEN` | _(empty)_ | Required for admin tools (`csex-token create`) |
| `DISPATCH_TIMEOUT` | `30` | HTTP timeout (seconds) |
| `ADSB_TIMEOUT` | `15` | airplanes.live timeout (seconds) |
| `DISPATCH_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `DISPATCH_MCP_PORT` | `8080` | Port when transport=http |

## Use with Claude Code

Add to `~/.claude/settings.json` (or project `.claude/settings.json`):

```json
{
  "mcpServers": {
    "dispatch": {
      "command": "dispatch-mcp",
      "env": {
        "DISPATCH_BASE_URL": "https://ops.csexecutiveservices.com",
        "DISPATCH_TOKEN": "your-token-here"
      }
    }
  }
}
```

## Use with Cline / Cursor / Zed / Windsurf

Same MCP JSON config block — each supports `mcpServers` in their settings file.
Path the `command` to the installed `dispatch-mcp` binary or `python -m dispatch_mcp.server`.

## Use with Open WebUI / Conduit

See [docs/mcpo-openwebui.md](./docs/mcpo-openwebui.md) for the mcpo bridge setup.

## Verify syntax

```bash
python -m py_compile dispatch_mcp/server.py \
  dispatch_mcp/config.py \
  dispatch_mcp/client.py \
  dispatch_mcp/tools/dispatch.py \
  dispatch_mcp/tools/flight.py \
  dispatch_mcp/tools/admin.py
echo "All clean"
```

## Notes

- Tier 0 endpoints (`/api/v1/*`) require no authentication.
- `dispatch_get_runsheet` is Tier 1 (Tailscale-gated): set `DISPATCH_BASE_URL=http://100.94.80.100:8000`.
- Admin endpoints require `DISPATCH_TOKEN`. Create tokens on the Pi: `csex-token create`.
- `dispatch.csexecutiveservices.com` has Cloudflare Access on POST routes; use `ops.csexecutiveservices.com` for programmatic access.
- CUI rules: this server never generates or exposes SHARES/HEARS/HEART frequencies. The platform ships with empty placeholder credential files.

## License

MIT
