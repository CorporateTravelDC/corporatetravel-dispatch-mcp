# Wiring dispatch-mcp into Open WebUI via mcpo

[mcpo](https://github.com/open-webui/mcpo) bridges MCP stdio servers to an OpenAPI HTTP
endpoint. Open WebUI (and Conduit) consume it as a "Tool" source. New tools added to
`dispatch-mcp` appear in Open WebUI automatically after an mcpo restart — no reconfiguration.

## Architecture

```
Conduit (Android / iOS)
        │
        ▼
openwebui.csexecutiveservices.com
        │
        ▼
Open WebUI  (:3000, container)
        │  calls tools via HTTP
        ▼
mcpo (:8082, host — corporatetraveldc-mcpo.service)
        │  spawns subprocess
        ▼
dispatch-mcp (stdio)
        │                         │
        ▼                         ▼
your-dispatch.your-domain   airplanes.live
```

External clients (Cline, Cursor, Windsurf) can also reach mcpo directly at
`https://mcpo.csexecutiveservices.com`.

## Current deployment (Pi — already running)

mcpo runs as a systemd user service, not a container, because `dispatch-mcp` is a host
Python binary and spawning it from inside a container is unnecessarily complex.

**Service file:** `~/.config/systemd/user/corporatetraveldc-mcpo.service`

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

ExecStart=/home/corporatetraveldc/.local/bin/mcpo --port 8082 -- /home/corporatetraveldc/.local/bin/dispatch-mcp

[Install]
WantedBy=default.target
```

Start/stop/status:

```bash
systemctl --user {start,stop,restart,status} corporatetraveldc-mcpo
```

## Install from scratch

mcpo and dispatch-mcp are Pi-wheel-free packages. On Fedora with a PEP 668 system Python,
bypass piwheels (which is unreachable on non-RPi-OS systems) and install to user site:

```bash
pip install --user --break-system-packages \
  --index-url https://pypi.org/simple \
  mcpo

pip install --user --break-system-packages \
  --index-url https://pypi.org/simple \
  'git+https://github.com/CorporateTravelDC/corporatetravel-dispatch-mcp.git'
```

Then drop the service file above into `~/.config/systemd/user/` and:

```bash
systemctl --user daemon-reload
systemctl --user enable --now corporatetraveldc-mcpo
```

## Configure Open WebUI

1. Open `https://openwebui.csexecutiveservices.com`
2. Admin Panel → Settings → Tools → Add Tool
3. Type: **OpenAPI**
4. URL: `http://host.containers.internal:8082/openapi.json`
   (Open WebUI runs in a container; `host.containers.internal` resolves to the Pi host)
5. Save

All 25 dispatch-mcp tools appear in Open WebUI and Conduit immediately.

## Configure external clients (Cline / Cursor / Windsurf)

These run outside the container and reach mcpo over the CF tunnel:

```
https://mcpo.csexecutiveservices.com/openapi.json
```

Add as an OpenAPI tool server in each client's settings using that URL.

## Verify

```bash
# From Pi host
curl http://127.0.0.1:8082/openapi.json | python3 -c \
  'import sys,json; d=json.load(sys.stdin); print(len(d["paths"]), "tools")'

# From anywhere (CF tunnel)
curl https://mcpo.csexecutiveservices.com/openapi.json | python3 -c \
  'import sys,json; d=json.load(sys.stdin); print(len(d["paths"]), "tools")'
```

Should print `25 tools`. Each MCP tool is a POST endpoint under its tool name.

## CF tunnel hostnames

| Hostname | Service | Notes |
|---|---|---|
| `openwebui.csexecutiveservices.com` | `:3000` | Open WebUI frontend |
| `mcpo.csexecutiveservices.com` | `:8082` | mcpo OpenAPI bridge |
