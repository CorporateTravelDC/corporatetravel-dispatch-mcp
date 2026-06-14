# Wiring dispatch-mcp into Open WebUI via mcpo

[mcpo](https://github.com/open-webui/mcpo) is an MCP-to-OpenAPI bridge. It runs on the Pi
and exposes any MCP server as an OpenAPI spec, which Open WebUI can consume as a single
"OpenAPI Tool" source. New tools added to the MCP server appear automatically in Open WebUI
without any reconfiguration.

## Architecture

```
Conduit (Android) ──> Open WebUI ──> mcpo (Pi, :8001) ──> dispatch-mcp (stdio) ──> ops.csexecutiveservices.com
                                                                                   ──> airplanes.live
```

## Install mcpo on the Pi

```bash
pip install mcpo --break-system-packages
```

Or run as a rootless Podman container (see quadlet example below).

## Run mcpo pointing at dispatch-mcp

```bash
mcpo \
  --port 8001 \
  --server-type stdio \
  --command "dispatch-mcp" \
  -- \
  --env DISPATCH_BASE_URL=https://ops.csexecutiveservices.com \
  --env DISPATCH_TOKEN=<your-token>
```

mcpo will start and expose the OpenAPI spec at `http://localhost:8001/openapi.json`.

## Podman Quadlet for mcpo (rootless, user corporatetraveldc)

Create `/home/corporatetraveldc/.config/containers/systemd/mcpo.container`:

```ini
[Unit]
Description=mcpo — MCP to OpenAPI bridge for dispatch-mcp
After=network-online.target

[Container]
Image=ghcr.io/open-webui/mcpo:latest
PublishPort=8001:8001
Environment=DISPATCH_BASE_URL=https://ops.csexecutiveservices.com
EnvironmentFile=/etc/corporatetraveldc/dispatch-secrets.env
Exec=--port 8001 --server-type stdio --command dispatch-mcp

[Service]
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

Then:
```bash
systemctl --user daemon-reload
systemctl --user enable --now mcpo
```

## Configure Open WebUI

1. Open `https://openwebui.csexecutiveservices.com`
2. Admin Panel → Settings → Tools → Add Tool
3. Type: **OpenAPI**
4. URL: `http://localhost:8001/openapi.json`  (or `http://100.94.80.100:8001/openapi.json` from remote)
5. Save

All 21 dispatch-mcp tools now appear in Open WebUI and Conduit automatically.
Any new tools added to dispatch-mcp will appear after restarting mcpo.

## Verify

```bash
curl http://localhost:8001/openapi.json | jq '.paths | keys'
```

Should return all tool paths. Each MCP tool becomes a POST endpoint.
