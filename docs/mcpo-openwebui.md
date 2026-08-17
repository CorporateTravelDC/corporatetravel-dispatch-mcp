# dispatch-mcp over HTTP: the two mcpo bridge instances

_Last verified against the running Pi: 2026-08-11_

[mcpo](https://github.com/open-webui/mcpo) bridges MCP stdio servers to an OpenAPI HTTP
endpoint. Open WebUI (and Conduit) consume it as a "Tool" source; remote integrations
(e.g. a Claude.ai custom connector) consume the public instance. New tools added to
`dispatch-mcp` appear automatically after an mcpo restart — no reconfiguration.

**There are TWO separate mcpo instances.** They run the same `dispatch-mcp` binary via
the same wrapper script but with different toolsets and different exposure. This split
exists because the admin and second-brain tools have **no per-caller authorization**
(see `dispatch_mcp/tools/__init__.py` — `admin._check_token()` only checks the process
has a token, not that the caller presented one), so the only safe way to expose a subset
publicly is a genuinely separate process that never loads those tools at all.

| | Private (full) | Public-safe |
|---|---|---|
| Unit | `corporatetraveldc-mcpo.service` | `corporatetraveldc-mcpo-public.service` |
| Port | `8082` | `8083` (`--host 127.0.0.1`, loopback-bound) |
| Toolset | **34 tools** incl. admin + second_brain | **26 tools** — `DISPATCH_MCP_PUBLIC_SAFE=1`, admin/second_brain **never loaded** |
| Public hostname | **None — must never get one** | `https://mcp.csexecutiveservices.com` (nginx + Cloudflare Tunnel) |
| Consumers | Open WebUI (local container), tailnet clients | Claude.ai custom connector / remote OpenAPI clients |

Both instances confirmed healthy 2026-08-11: `:8082/openapi.json` → 34 paths (all
admin + `dispatch_remember` present); `:8083/openapi.json` → 26 paths, zero
admin/second_brain paths, same result via `https://mcp.csexecutiveservices.com`.

## Architecture

```
LOCAL / PRIVATE PATH                        PUBLIC PATH
--------------------                        -----------
Conduit (Android / iOS)                     Claude.ai custom connector,
        │                                   remote OpenAPI clients
        ▼                                           │
openwebui.csexecutiveservices.com                   ▼
        │                                   Cloudflare Tunnel
        ▼                                           │
Open WebUI (:3000, container)                       ▼
        │ host.containers.internal:8082     nginx vhost
        ▼                                   mcp.csexecutiveservices.com.conf
mcpo :8082                                  ("MUST NOT proxy to :8082")
corporatetraveldc-mcpo.service                      │
FULL toolset: 34 tools                              ▼
        │                                   mcpo :8083 (127.0.0.1 only)
        │                                   corporatetraveldc-mcpo-public.service
        │                                   DISPATCH_MCP_PUBLIC_SAFE=1 → 26 tools
        │                                           │
        └──────────────┬────────────────────────────┘
                       ▼
        dispatch-mcp-wrapper.sh → dispatch-mcp (stdio)
                       │
        ┌──────────────┼──────────────────┐
        ▼              ▼                  ▼
  dispatch API    airplanes.live     airframes.io
  (Tailscale 100.94.80.100:8000,
   failback dispatch.csexecutiveservices.com)
```

Claude Code does **not** use either bridge — it spawns `dispatch-mcp` directly over
stdio (see README "Use with Claude Code").

The old `mcpo.csexecutiveservices.com` hostname (previously documented as fronting
`:8082`) is dead — it returns 404 and must not be resurrected. The full-toolset
instance is never to be given a public or LAN-reachable hostname; the nginx vhost for
`mcp.csexecutiveservices.com` carries an explicit "MUST NOT proxy to :8082" comment.

## Deployed units (Pi, systemd user services)

Both units live in `~/.config/systemd/user/` and exec the repo's wrapper script
(`/home/corporatetraveldc/mcp/dispatch-mcp/dispatch-mcp-wrapper.sh`), which extracts
`DISPATCH_ADMIN_TOKEN` from `/etc/corporatetraveldc/dispatch-secrets.env` (without
sourcing it as bash), exports it as `DISPATCH_TOKEN`, and execs the venv binary
`/opt/corporatetraveldc/corporatetravel-dispatch-mcp/venv/bin/dispatch-mcp`.

**`corporatetraveldc-mcpo.service`** (private, full toolset):

```ini
[Unit]
Description=Corporate Travel DC -- mcpo (MCP-over-OpenAPI bridge for dispatch-mcp)
Documentation=https://github.com/CorporateTravelDC/corporatetravel-dispatch-mcp
After=network-online.target
After=podman-user-wait-network-online.service

[Service]
Type=simple
Restart=always
RestartSec=10
EnvironmentFile=/etc/corporatetraveldc/dispatch.env
EnvironmentFile=/etc/corporatetraveldc/dispatch-secrets.env
ExecStart=/home/corporatetraveldc/.local/bin/mcpo --port 8082 -- /home/corporatetraveldc/mcp/dispatch-mcp/dispatch-mcp-wrapper.sh

[Install]
WantedBy=default.target
```

Note: this unit passes no `--host`, so mcpo binds `0.0.0.0:8082` (verified with
`ss -tlnp` 2026-08-11). Its "loopback-only" status is enforced by the absence of any
hostname/vhost/tunnel routing to it, not by the bind address — adding
`--host 127.0.0.1` (as the public unit already does) would harden this and is
recommended.

**`corporatetraveldc-mcpo-public.service`** (public-safe):

```ini
[Unit]
Description=Corporate Travel DC -- mcpo (MCP-over-OpenAPI bridge for dispatch-mcp, PUBLIC-SAFE toolset only)
Documentation=https://github.com/CorporateTravelDC/corporatetravel-dispatch-mcp
After=network-online.target
After=podman-user-wait-network-online.service

[Service]
Type=simple
Restart=always
RestartSec=10
EnvironmentFile=/etc/corporatetraveldc/dispatch.env
EnvironmentFile=/etc/corporatetraveldc/dispatch-secrets.env
Environment=DISPATCH_MCP_PUBLIC_SAFE=1
ExecStart=/home/corporatetraveldc/.local/bin/mcpo --host 127.0.0.1 --port 8083 -- /home/corporatetraveldc/mcp/dispatch-mcp/dispatch-mcp-wrapper.sh

[Install]
WantedBy=default.target
```

`DISPATCH_MCP_PUBLIC_SAFE=1` makes `dispatch_mcp/tools/__init__.py::register()` skip
`admin` and `second_brain` entirely — the modules are never imported into the tool
registry, so no gate, header, or token check is in the request path at all.

The canonical copies of the public unit and the nginx vhost are tracked in the
private infra repo at
`/opt/corporatetraveldc/private/ctdi-dispatch-internal/.config/systemd/user/corporatetraveldc-mcpo-public.service`
and `/opt/corporatetraveldc/private/ctdi-dispatch-internal/nginx/conf.d/mcp.csexecutiveservices.com.conf`.

Start/stop/status:

```bash
systemctl --user {start,stop,restart,status} corporatetraveldc-mcpo
systemctl --user {start,stop,restart,status} corporatetraveldc-mcpo-public
```

## nginx vhost (public instance only)

`mcp.csexecutiveservices.com.conf` listens on :80 (Cloudflare terminates TLS;
nginx sees plain HTTP from cloudflared), rate-limits
(`zone=corporatetraveldc_lr burst=20`), sets `X-CTDI-Public: 1` (same pattern as the
other public vhosts), and proxies **only** to `http://127.0.0.1:8083`. The config
comment is explicit: it must never proxy to `:8082`.

## Install / deploy from scratch

On Fedora with a PEP 668 system Python, bypass piwheels and install to user site:

```bash
pip install --user --break-system-packages \
  --index-url https://pypi.org/simple \
  mcpo

pip install --user --break-system-packages \
  --index-url https://pypi.org/simple \
  jsonschema

pip install --user --break-system-packages \
  --index-url https://pypi.org/simple \
  'git+https://github.com/CorporateTravelDC/corporatetravel-dispatch-mcp.git'
```

Then drop both unit files into `~/.config/systemd/user/` and:

```bash
systemctl --user daemon-reload
systemctl --user enable --now corporatetraveldc-mcpo corporatetraveldc-mcpo-public
```

### Deployment gotchas (all hit for real on 2026-08-11)

1. **`jsonschema` missing → server crashes at import.** The `mcp` package's
   `mcp/server/lowlevel/server.py` does `import jsonschema` unconditionally, but
   neither `mcp` nor the `mcp[cli]` extra reliably declares/pulls it. Fixed at the
   source: this repo's `pyproject.toml` now declares `jsonschema` explicitly. If you
   installed before that fix (or from the public mirror): `pip install --user jsonschema`.
2. **Unit + vhost written but never deployed.** The public unit and nginx vhost had
   existed in the private infra repo since 2026-08-06 but were not enabled on the box
   until 2026-08-11. Writing the files is not deploying them — copy the unit into
   `~/.config/systemd/user/`, the vhost into `/etc/nginx/conf.d/`, then
   `daemon-reload` + `enable --now` + `nginx -s reload`.
3. **SELinux blocks nginx → :8083.** `httpd_t` was denied connecting to the backend
   (confirmed via `ausearch -m avc`; generic missing-port-context denial, not specific
   to 8083). Fix: `sudo setsebool -P httpd_can_network_connect on`.

### Public mirror gap (do not install a public instance from the mirror)

As of 2026-08-11 the public GitHub mirror of this repo is **missing the
`public_safe` registration-mode commits**. A build installed from the public
mirror's `pip install git+https://...` instructions ignores
`DISPATCH_MCP_PUBLIC_SAFE` entirely and always registers all 34 tools,
including admin and second_brain. Until the mirror is re-synced, only build
publicly exposed instances from this (private) repo.

## Configure Open WebUI

1. Open `https://openwebui.csexecutiveservices.com`
2. Admin Panel → Settings → Tools → Add Tool
3. Type: **OpenAPI**
4. URL: `http://host.containers.internal:8082/openapi.json`
   (Open WebUI runs in a container; `host.containers.internal` resolves to the Pi host —
   this is the **private** instance, so Open WebUI gets all 34 tools)
5. Save

## Configure remote clients (Claude.ai connector, Cline, Cursor, Windsurf off-net)

Use the **public** instance only:

```
https://mcp.csexecutiveservices.com/openapi.json
```

These clients get the 26-tool public-safe subset. There is no public URL for the
full toolset, by design; on-tailnet clients that need admin tools should either run
`dispatch-mcp` locally over stdio or reach `:8082` over the tailnet.

## Verify

```bash
# Private instance (Pi host) — expect 34 paths, admin + remember present
curl -s http://127.0.0.1:8082/openapi.json | python3 -c \
  'import sys,json; d=json.load(sys.stdin); print(len(d["paths"]), "paths")'

# Public instance, locally — expect 26 paths, zero admin/second_brain
curl -s http://127.0.0.1:8083/openapi.json | python3 -c \
  'import sys,json; p=json.load(sys.stdin)["paths"]; print(len(p), "paths"); \
   print("admin leak!" if any("admin" in x or "remember" in x for x in p) else "no admin paths")'

# Public instance, through Cloudflare — must match :8083 exactly
curl -s https://mcp.csexecutiveservices.com/openapi.json | python3 -c \
  'import sys,json; d=json.load(sys.stdin); print(len(d["paths"]), "paths")'
```

Each MCP tool is a POST endpoint under its tool name.

## Hostname / port map

| Hostname / address | Backend | Toolset | Notes |
|---|---|---|---|
| `openwebui.csexecutiveservices.com` | `:3000` (container) | n/a | Open WebUI frontend |
| `http://host.containers.internal:8082` | `corporatetraveldc-mcpo.service` | 34 (full) | Container-to-host only; **no public hostname, ever** |
| `mcp.csexecutiveservices.com` | nginx → `127.0.0.1:8083` | 26 (public-safe) | Cloudflare Tunnel; Claude.ai connector endpoint |
| `mcpo.csexecutiveservices.com` | — | — | **Dead (404). Retired; do not re-create.** |
