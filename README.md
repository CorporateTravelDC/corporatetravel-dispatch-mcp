# corporatetravel-dispatch-mcp

_Last verified against code: 2026-08-11_

> **Right repo?** You want **`corporatetravel-dispatch-mcp`** (this one) for the MCP server.
> The dispatch platform source lives at [`corporatetraveldc-dispatch`](https://github.com/CorporateTravelDC/corporatetraveldc-dispatch).
> The public mirror is at [`ctdi-dispatch`](https://github.com/CorporateTravelDC/ctdi-dispatch).

MCP server exposing the CS Executive Services dispatch platform (Raspberry Pi 5 based),
airplanes.live flight tracking, and airframes.io ACARS as portable, agent-agnostic tools.
Works with any MCP-compatible agent: Claude Code, Cline, Cursor, Zed, Windsurf, and — via
two [mcpo](./docs/mcpo-openwebui.md) HTTP bridges — Open WebUI locally and remote
integrations (e.g. a Claude.ai custom connector) publicly.

> ALL Public Commits are GPG signed using Key: ABD3976FCC006E0F3FE559177286B3118BA4EFB2. Pubkey is included in this repo as `ABD3976FCC006E0F3FE559177286B3118BA4EFB2.gpg`.

## Tools (34 total; 26 in public-safe mode)

Tool registration lives in `dispatch_mcp/tools/__init__.py`:
`register(mcp, public_safe: bool)`. With `DISPATCH_MCP_PUBLIC_SAFE=1` the
`admin` module (7 tools) and `second_brain` package (1 tool) are **never
loaded** — not merely gated — leaving the 26-tool public-safe subset. Counts
verified 2026-08-11 with `grep -rc "@mcp.tool" dispatch_mcp/tools/` and against
both running mcpo instances' `/openapi.json` (34 paths private, 26 public).

### Dispatch platform — Tier 0 (no auth required) — `tools/dispatch.py`

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
| `dispatch_get_opsplan` | `/api/v1/opsplan` | FAA ATCSCC National Operations Plan |
| `dispatch_get_runsheet` | `/api/v1/runsheet` | Active trip runsheet (**Tailscale-only**, sends bearer token) |
| `dispatch_get_data_usage` | `/api/v1/data-usage?days={n}` | Pi network data usage (vnstat daily log) |

### Dispatch platform — Watchlist — `tools/dispatch.py` (bearer token sent)

| Tool | Method + route | Description |
|---|---|---|
| `dispatch_watchlist_get` | `GET /api/v1/watchlist` | List active VIP watchlist sessions |
| `dispatch_watchlist_add` | `POST /api/v1/watchlist/{flights\|trains\|vessels}` | Add subject to watchlist (typed routes; generic/ground/person not yet supported) |
| `dispatch_watchlist_remove` | `DELETE /api/v1/watchlist/{session_id}` | Remove watchlist session |

### Dispatch platform — FIDS — `tools/fids.py`

| Tool | Endpoint | Description |
|---|---|---|
| `dispatch_get_fids_flight` | `/api/v1/fids/{airport}/{flight}` | Confirmed gate, baggage carousel, arrival status (DCA/IAD, MWAA) |
| `dispatch_get_fids_snapshot` | `/api/v1/fids/{airport}` | FIDS feed health/freshness snapshot (DCA/IAD) |
| `dispatch_get_fids_arrivals` | `/api/v1/fids/{airport}/arrivals` | Forward-looking arrivals, DCA/IAD/BWI (SWIM + website + AeroAPI) |

### FAA Aircraft Registry — `tools/aircraft.py` (local cache on the Pi, updated weekly)

| Tool | Endpoint | Description |
|---|---|---|
| `dispatch_lookup_aircraft` | `/api/v1/aircraft/{identifier}` | Look up aircraft by N-number or ICAO hex |
| `dispatch_faa_registry_status` | `/api/v1/aircraft-registry/status` | Local registry cache status |

### Admin — `tools/admin.py` (requires `DISPATCH_TOKEN`; **excluded in public-safe mode**)

| Tool | Route | Description |
|---|---|---|
| `dispatch_admin_health` | `GET /admin/healthz` | Extended health check |
| `dispatch_admin_refresh_feed` | `POST /admin/refresh-feed/{name}` | Force-refresh a named feed (metar, nws, tfr, notam, amtrak, atcscc_opsplan, runsheet) |
| `dispatch_admin_force_recompute_cps` | `POST /admin/force-recompute-cps` | Force CPS recomputation |
| `dispatch_admin_force_opsplan_snapshot` | `POST /admin/force-opsplan-snapshot` | Force opsplan fetch |
| `dispatch_admin_send_push_alert` | `POST /admin/push-test-alert` | Send ntfy push notification |
| `dispatch_admin_get_audit_log` | `GET /admin/audit` | View audit log (append-only, 90-day retention) |
| `dispatch_watchdog_status` | `GET /admin/watchdog/status` | Last ctdi-watchdog run result (lives in admin.py, so excluded in public-safe mode despite the name) |

### Second Brain — `tools/second_brain/remember.py` (requires `DISPATCH_TOKEN`; **excluded in public-safe mode**)

| Tool | Route | Description |
|---|---|---|
| `dispatch_remember` | `POST /api/v1/remember` | Capture a manual note into the second-brain vault (`01-Sources/manual/`). Scrub-gated (CUI/PII **block**, not redact — 422 on match, nothing written). |

### Flight Tracking — airplanes.live — `tools/flight.py` (no auth)

| Tool | Description |
|---|---|
| `flight_get_by_callsign` | ADS-B position lookup by ICAO callsign |
| `flight_get_by_registration` | ADS-B position + hex by tail number |
| `flight_get_by_hex` | ADS-B position by confirmed ICAO 24-bit hex |

**Hex resolution order:** `callsign → registration → hex`. Always confirm hex via
`flight_get_by_registration` before adding to watchlist — hex is airframe-bound;
callsign-to-hex mappings can be stale day-over-day.

### ACARS — airframes.io — `tools/acars.py` (no auth)

| Tool | Description |
|---|---|
| `acars_get_by_hex` | Recent ACARS/VDL2/HFDL messages for an airframe hex |

## Security model: no per-caller auth on admin/second-brain tools

`admin._check_token()` only verifies the **process** has a `DISPATCH_TOKEN`
configured — it does not verify the MCP caller presented anything. Every
outbound admin call uses that one fixed token regardless of caller. These
tools are therefore only safe on instances where reachability itself is the
access control (stdio on your own machine, or the loopback/tailnet mcpo
instance). Any instance fronted by a public hostname must run with
`DISPATCH_MCP_PUBLIC_SAFE=1`, which never loads them at all. See
[docs/mcpo-openwebui.md](./docs/mcpo-openwebui.md) for the two-instance
deployment that enforces this.

## Install

```bash
pip install -e .
```

Requires Python 3.11+. Dependencies (declared in `pyproject.toml`): `mcp[cli]`,
`httpx`, `pydantic`, and `jsonschema`.

> **Why jsonschema is pinned here:** `mcp/server/lowlevel/server.py` imports
> `jsonschema` unconditionally, but the `mcp` package does not declare it and
> the `mcp[cli]` extra does not reliably pull it in. Without it the server
> crashes at import. Declared explicitly in this repo's `pyproject.toml` as of
> 2026-08-11.

> **Public mirror gap (2026-08-11):** the public GitHub mirror
> (`corporatetravel-dispatch-mcp` public copy) is **missing the `public_safe`
> registration-mode commits**. Anyone installing from the public repo's
> `pip install git+https://...` instructions gets a build with **no way to
> exclude admin/second_brain tools**. Until the mirror is re-synced, do not
> build a publicly exposed instance from the public repo.

## Configure

| Env var | Default | Notes |
|---|---|---|
| `DISPATCH_BASE_URL` | `http://100.94.80.100:8000` | Tailscale address of the Pi — primary. |
| `DISPATCH_FALLBACK_URL` | `https://dispatch.csexecutiveservices.com` | Tried only on transport-level failure of the primary (connect/timeout), never on HTTP 4xx/5xx. CF Access gates POST routes there, so admin failover may 401/403. |
| `DISPATCH_TOKEN` | _(empty)_ | Required for admin/second-brain tools (`csex-token create` on the Pi) |
| `DISPATCH_TIMEOUT` | `30` | Dispatch HTTP timeout (seconds) |
| `ADSB_TIMEOUT` | `15` | airplanes.live timeout (seconds) |
| `ACARS_BASE_URL` | `https://api.airframes.io/messages` | airframes.io ACARS aggregator |
| `ACARS_TIMEOUT` | `15` | airframes.io timeout (seconds) |
| `DISPATCH_MCP_TRANSPORT` | `stdio` | `stdio` or `http` (streamable HTTP) |
| `DISPATCH_MCP_PORT` | `8080` | Port when transport=http |
| `DISPATCH_MCP_PUBLIC_SAFE` | _(unset)_ | `1`/`true`/`yes` → never load admin/second_brain (26 tools). Opt-in per instance, never default. |

> **Retired hostname:** `ops.csexecutiveservices.com` is fully retired and
> hard-rejected app-side (dispatch platform `runner/main.py`
> `_RETIRED_HOSTNAMES`). It must not appear in any config. Older docs and
> examples that referenced it as the default `DISPATCH_BASE_URL` are obsolete.

## Use with Claude Code

Register at user scope (persists across projects):

```bash
claude mcp add dispatch \
  -e DISPATCH_BASE_URL=http://100.94.80.100:8000 \
  -e DISPATCH_TOKEN=your-token-here \
  --scope user \
  -- dispatch-mcp
```

Or add to `~/.claude/.claude.json` directly under `"mcpServers"`:

```json
{
  "mcpServers": {
    "dispatch": {
      "type": "stdio",
      "command": "/full/path/to/dispatch-mcp",
      "args": [],
      "env": {
        "DISPATCH_BASE_URL": "http://100.94.80.100:8000",
        "DISPATCH_TOKEN": "your-token-here"
      }
    }
  }
}
```

On the Pi itself, `dispatch-mcp-wrapper.sh` (repo root) is the preferred
command: it extracts `DISPATCH_ADMIN_TOKEN` from
`/etc/corporatetraveldc/dispatch-secrets.env` without sourcing the file as
bash, exports it as `DISPATCH_TOKEN`, and execs the venv binary at
`/opt/corporatetraveldc/corporatetravel-dispatch-mcp/venv/bin/dispatch-mcp`.
Both deployed mcpo services use this wrapper.

## Use with Cline / Cursor / Zed / Windsurf

Same MCP JSON config block — each supports `mcpServers` in their settings file.
Point `command` at the installed `dispatch-mcp` binary or `python -m dispatch_mcp.server`.

## Use with Open WebUI / Claude.ai / HTTP clients

See [docs/mcpo-openwebui.md](./docs/mcpo-openwebui.md). Two separate mcpo
bridge instances run on the Pi:

- **Private, full toolset (34):** `corporatetraveldc-mcpo.service`, port `8082`,
  no public hostname — Open WebUI consumes it via `host.containers.internal:8082`.
- **Public-safe (26):** `corporatetraveldc-mcpo-public.service`, port `8083`
  (loopback-bound), `DISPATCH_MCP_PUBLIC_SAFE=1`, fronted by nginx + Cloudflare
  Tunnel at `https://mcp.csexecutiveservices.com` — the endpoint remote
  integrations (e.g. a Claude.ai custom connector) use.

## Context efficiency and plan compatibility

MCP tool responses are structured and compact — each tool returns only the data the agent
actually needs, rather than dumping raw API payloads into the context window. This matters
for subscription plan users:

- **Claude Pro** — operational dispatch workflows (TFR checks, CPS queries, flight lookups,
  daily brief) stay well within the message window because context stays lean. Pairing with
  a context guardian skill (e.g. the `dispatch-context-guardian` Cowork skill bundled with
  this deployment) automatically compacts sessions before they hit plan limits.
- **Claude Max / API** — compact responses reduce per-request token cost and latency.
- **Cline / Cursor / Windsurf** — same economy; MCP tool calls consume far fewer tokens
  than equivalent REST-then-paste workflows.

## Verify syntax

```bash
python -m py_compile \
  dispatch_mcp/server.py \
  dispatch_mcp/config.py \
  dispatch_mcp/client.py \
  dispatch_mcp/tools/__init__.py \
  dispatch_mcp/tools/dispatch.py \
  dispatch_mcp/tools/flight.py \
  dispatch_mcp/tools/admin.py \
  dispatch_mcp/tools/aircraft.py \
  dispatch_mcp/tools/acars.py \
  dispatch_mcp/tools/fids.py \
  dispatch_mcp/tools/second_brain/__init__.py \
  dispatch_mcp/tools/second_brain/remember.py
echo "All clean"
```

## Notes

- Tier 0 endpoints (`/api/v1/*`) require no authentication.
- `dispatch_get_runsheet` is Tailscale-gated and only works against the default
  Tailscale `DISPATCH_BASE_URL`.
- Admin endpoints require `DISPATCH_TOKEN`. Create tokens on the Pi: `csex-token create`.
- `dispatch.csexecutiveservices.com` has Cloudflare Access on POST routes; it is
  the transport-failure fallback only, not the primary.
- `ops.csexecutiveservices.com` is retired and hard-rejected — never use it.
- CUI rules: this server never generates or exposes SHARES/HEARS/HEART frequencies.
  The platform ships with empty placeholder credential files.

## License

MIT
