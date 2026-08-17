# Documentation refresh — 2026-08-11

Full from-scratch rewrite of this repo's documentation, grounded in the code as
it exists on branch `docs-refresh-2026-08-11`. Every claim below was verified
against the working tree (`grep`/`find`/full reads), the running Pi services,
and the live `/openapi.json` of both mcpo instances — not against the old docs.

## Verification baseline

- Tool count: `grep -rc "@mcp.tool" dispatch_mcp/tools/` → dispatch.py 17,
  admin.py 7, fids.py 3, flight.py 3, aircraft.py 2, acars.py 1,
  second_brain/remember.py 1 = **34 total**; public-safe subset = 34 − 7 − 1 = **26**.
- Runtime cross-check: `http://127.0.0.1:8082/openapi.json` → 34 paths (all 6
  `dispatch_admin_*` + `dispatch_watchdog_status` under admin, plus
  `/dispatch_remember` present); `http://127.0.0.1:8083/openapi.json` → 26
  paths, zero admin/remember; `https://mcp.csexecutiveservices.com/openapi.json`
  → 26 paths (matches :8083).
- `dispatch_mcp/server.py` read in full: registration is
  `tools.register(mcp, public_safe=...)` driven by `DISPATCH_MCP_PUBLIC_SAFE`.
- Deployed units read via `systemctl --user cat`; bind addresses via `ss -tlnp`
  (8082 → `0.0.0.0`, 8083 → `127.0.0.1`); nginx vhost read from
  `/opt/corporatetraveldc/private/ctdi-dispatch-internal/nginx/conf.d/mcp.csexecutiveservices.com.conf`.
- `mcpo.csexecutiveservices.com` probed: HTTP 404 (dead hostname).
- `jsonschema` gap confirmed: `import jsonschema` present in the installed
  `mcp` package's `server/lowlevel/server.py`; not declared in this repo's
  `pyproject.toml` before today.

## File-by-file changes

### 1. `README.md` — rewritten from scratch

| Was (wrong) | Now (verified) |
|---|---|
| "Tools (21 total)" | "Tools (34 total; 26 in public-safe mode)" — per-module grep counts + both live openapi.json |
| Tool tables omitted `dispatch_get_data_usage`, `dispatch_watchdog_status`, all 3 FIDS tools, both aircraft-registry tools, and `acars_get_by_hex` | All 34 tools tabled, grouped by source module, with real routes |
| Watchlist rows: `POST /api/v1/watchlist`, `DELETE /api/v1/watchlist` | Actual routes: `POST /api/v1/watchlist/{flights\|trains\|vessels}` (typed; bare path doesn't exist on the backend per dispatch.py comment), `DELETE /api/v1/watchlist/{session_id}` |
| Env table: `DISPATCH_BASE_URL` default `https://ops.csexecutiveservices.com` | Real default per `config.py`: `http://192.0.2.10:8000` (Tailscale), plus previously undocumented `DISPATCH_FALLBACK_URL` (`https://dispatch.csexecutiveservices.com`, transport-failure-only), `ACARS_BASE_URL`, `ACARS_TIMEOUT`, `DISPATCH_MCP_PUBLIC_SAFE` |
| `claude mcp add` example and JSON example both used `DISPATCH_BASE_URL=https://ops.csexecutiveservices.com` | Both examples use the Tailscale default; retired-hostname warning added |
| Notes: "use `ops.csexecutiveservices.com` for programmatic access" | ops.csexecutiveservices.com documented as fully retired and hard-rejected app-side (platform `runner/main.py` `_RETIRED_HOSTNAMES`) |
| Verify-syntax snippet compiled only 6 files (missing fids, aircraft, acars, second_brain, tools/__init__) | Compiles all 12 Python files |
| No mention of the security model, the wrapper script, the two mcpo instances, or the public-mirror gap | New sections: per-caller-auth caveat for admin/second_brain; `dispatch-mcp-wrapper.sh` behavior (token extraction + venv exec path, matching both deployed units); two-instance summary; public-mirror missing `public_safe` commits warning |

### 2. `docs/mcpo-openwebui.md` — rewritten from scratch

| Was (wrong) | Now (verified) |
|---|---|
| "All 25 dispatch-mcp tools appear…" / "Should print `25 tools`" | 34 (private :8082) / 26 (public :8083), matching live openapi.json |
| Single-instance architecture diagram, dispatch backend shown as `ops.csexecutiveservices.com` | Two-path diagram: private (Open WebUI → :8082, 34 tools) vs public (Cloudflare Tunnel → nginx → 127.0.0.1:8083, 26 tools); backend shown as Tailscale `192.0.2.10:8000` with `dispatch.csexecutiveservices.com` failback |
| Documented ExecStart: `mcpo --port 8082 -- /home/corporatetraveldc/.local/bin/dispatch-mcp` | Real deployed ExecStart (both units): `…/mcpo [--host 127.0.0.1] --port 808x -- /home/corporatetraveldc/mcp/dispatch-mcp/dispatch-mcp-wrapper.sh`, which execs `/opt/corporatetraveldc/corporatetravel-dispatch-mcp/venv/bin/dispatch-mcp` |
| `corporatetraveldc-mcpo-public.service` not mentioned anywhere (the public/private split was completely undocumented) | Full section: unit text as deployed, `DISPATCH_MCP_PUBLIC_SAFE=1` semantics (admin/second_brain never imported, not gated), canonical file locations in the private infra repo, nginx vhost summary incl. its "MUST NOT proxy to :8082" rule and `X-CTDI-Public: 1` header |
| External clients directed to `https://mcpo.csexecutiveservices.com` (fronting :8082 — the full/admin toolset) | That hostname is dead (probed: 404) and flagged "do not re-create"; remote clients (incl. the Claude.ai custom connector) use `https://mcp.csexecutiveservices.com` → :8083 only |
| Hostname table: `mcpo.csexecutiveservices.com` → `:8082` | Hostname/port map with all four rows: openwebui :3000, host-internal :8082 (no public hostname ever), mcp.csexecutiveservices.com → 127.0.0.1:8083, mcpo.* dead |
| No deployment gotchas | New section with the three 2026-08-11 findings: (a) `jsonschema` import crash + pyproject fix, (b) unit/vhost written 2026-08-06 but never enabled until 2026-08-11, (c) SELinux `httpd_can_network_connect` boolean needed for nginx → :8083 (confirmed via `ausearch -m avc`) |
| No mirror warning | Public GitHub mirror missing the `public_safe` commits — installs from it always register all 34 tools; flagged prominently in both docs |
| — (accurate but noted) | 8082 actually binds `0.0.0.0` (unit passes no `--host`); documented honestly, with a recommendation to add `--host 127.0.0.1` to match the public unit |

### 3. `pyproject.toml` — code fix (not just docs)

Added `jsonschema>=4.0.0` to `[project] dependencies` with a comment explaining
why: `mcp/server/lowlevel/server.py` imports it unconditionally, but neither
the `mcp` package nor its `[cli]` extra reliably provides it; the public mcpo
instance crashed at import on 2026-08-11 until `pip install --user jsonschema`.

### 4. `dispatch_mcp/server.py` — module docstring

| Was (wrong) | Now |
|---|---|
| `DISPATCH_BASE_URL … (default: https://ops.csexecutiveservices.com)` | Default `http://192.0.2.10:8000` (Tailscale) + `DISPATCH_FALLBACK_URL`; retired-hostname note |
| "Tool inventory (34 tools)" but only 32 listed — `dispatch_get_data_usage` and `dispatch_watchdog_status` missing | All 34 listed; `dispatch_watchdog_status` shown under Admin (it lives in admin.py, so it's excluded in public-safe mode) |
| Watchlist inventory rows showed bare `/api/v1/watchlist` for POST/DELETE | Typed add routes + `/{session_id}` delete |
| Env-var list missing `DISPATCH_FALLBACK_URL`, `ACARS_TIMEOUT`, `DISPATCH_MCP_PUBLIC_SAFE` | All documented; "26 with DISPATCH_MCP_PUBLIC_SAFE=1" stated |
| "Can also run as a streamable HTTP server for mcpo → Open WebUI" (implied mcpo uses HTTP transport) | Clarified: deployed mcpo bridges spawn the stdio binary; HTTP transport is a separate option |

No logic changed; `_public_safe` handling and `main()` untouched.

### 5. `dispatch_mcp/config.py` — docstring/comments only

- Module docstring: "…works against local Tailscale, ops.csexecutiveservices.com,
  or a dev instance" → Tailscale default / dispatch.csexecutiveservices.com
  failback / dev instance.
- The `DISPATCH_BASE_URL` comment's "do not revert to ops… until DNS/tunnel
  routing is corrected upstream" (implying it might come back) → 2026-08-11
  note that ops is fully retired and hard-rejected app-side
  (`runner/main.py` `_RETIRED_HOSTNAMES`); never revert.
- No value or logic changes.

### 6. `dispatch_mcp/tools/admin.py` — module docstring only

- Was: "Admin routes are only accessible from Tailscale (100.x.x.x) or via
  ops.csexecutiveservices.com with a valid token." → ops reference removed
  (retired/hard-rejected); Tailscale default named explicitly; CF-Access
  failover caveat kept accurate.
- Added the process-token-vs-caller-auth caveat (mirrors the existing
  `tools/__init__.py` reasoning) and the `DISPATCH_MCP_PUBLIC_SAFE=1`
  exclusion. No logic changed.

### 7. `dispatch_mcp/tools/__init__.py` — docstrings only

- Module docstring said "Call register(mcp) to attach all tools" — predates the
  `public_safe` parameter. Now documents `register(mcp, public_safe=False)`
  with the 34/26 split.
- `register()` docstring's bare reference to `docs/COMPLIANCE_SECURITY.md`
  (which does not exist in this repo) clarified to point at the
  `corporatetraveldc-dispatch` platform repo. Registration logic untouched.

## Known gaps intentionally NOT fixed here (documented only)

1. **Public GitHub mirror is stale**: missing the `public_safe`
   registration-mode commits entirely. Anyone following the public repo's
   `pip install git+https://…` instructions gets a build with no way to exclude
   admin/second_brain tools. Needs a mirror re-sync (via push-public.sh flow);
   out of scope for this branch.
2. **:8082 binds 0.0.0.0**: the private unit passes no `--host`. Not a doc bug —
   documented as-is with a hardening recommendation (`--host 127.0.0.1`).
   Changing the deployed unit is an infra-repo change, not a change in this repo.
3. Old docs' "21 tools" (README), "25 tools" (mcpo doc), and server.py's
   own inventory listing 32-of-34 were three mutually inconsistent counts —
   all now derive from the same verified number (34/26) with the verification
   command recorded in the README.

All changes are uncommitted working-tree edits on `docs-refresh-2026-08-11`,
per the standing rule that the operator reviews and commits everything.
