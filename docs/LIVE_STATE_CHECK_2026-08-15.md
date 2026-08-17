# Live state check — 2026-08-15 (off-cycle)

Baseline: `docs/DOCS_REFRESH_2026-08-11.md`. Zero commits in this repo since
then (branch `docs-refresh-2026-08-11`; the 2026-08-11 refresh edits are still
uncommitted working-tree changes awaiting operator review). Run early — ahead
of the normal Monday cycle — because of tonight's ctdi-dispatch-internal work
(Ollama resource-exhaustion fix `2ff1fbb`, csex/csexec naming cleanup
`be79c47`); both were checked for relevance here, plus this repo's own drift.

## Drift found

### 1. `csex-token create` never existed — 5 files affected (naming cleanup hit)

Tonight's internal commit `be79c47` establishes that `csex-token` was never a
real binary. The token CLI is `src/ctdc_token/cli.py` in ctdi-dispatch-internal,
invoked as `PYTHONPATH=src python3 src/ctdc_token/cli.py` — usage
`ctdc-token create --user <user> --tier <cert|shares|admin> [...]` (admin tier
for `DISPATCH_TOKEN`). Stale references in this repo:

- `README.md:144` and `README.md:250` — "`csex-token create` on the Pi"
- `dispatch_mcp/config.py:47` — comment
- `dispatch_mcp/tools/admin.py:4` and `:95` — docstring + error message
  (the `:95` one is user-facing: it's returned to the caller on 401/403)
- `dispatch_mcp/server.py:26` — docstring
- `dispatch_mcp/tools/second_brain/remember.py:42` — error message

### 2. Private mcpo (:8082) is now loopback-bound — doc says 0.0.0.0

`docs/mcpo-openwebui.md:98-101` states the private unit passes no `--host`,
binds `0.0.0.0:8082`, and recommends adding `--host 127.0.0.1`. That
recommendation has been applied: the deployed
`~/.config/systemd/user/corporatetraveldc-mcpo.service` (mtime 2026-08-11
12:59, i.e. same day as the refresh but after its `ss` check; repo-tracked
copy changed in internal `dc48a84`, 2026-08-07) now has
`ExecStart=... mcpo --host 127.0.0.1 --port 8082 ...`, and `ss -tlnp` confirms
`127.0.0.1:8082`. The doc's "binds 0.0.0.0 / hardening recommended" passage is
stale — it should say both instances are loopback-only.

### 3. The documented Open WebUI → :8082 path is dead (two independent ways)

`README.md:205-206` ("Open WebUI consumes it via `host.containers.internal:8082`")
and the private-path diagram in `docs/mcpo-openwebui.md` do not match live:

- With :8082 now loopback-only, `host.containers.internal` (169.254.1.2 in the
  `openwebui` container, pasta networking) cannot reach it — verified from
  inside the container: `curl http://host.containers.internal:8082/openapi.json`
  → connect failure (000). Loopback- and tailnet-bound host services are not
  reachable via that address at all (ports 8000/8083/11434 all fail the same way).
- Independently, Open WebUI itself has **no tool server configured**:
  `webui.db` has `tool_server.connections = []` and a features flag
  `"tool_servers": false`. No URL containing `8082` appears anywhere in its DB.

So "34 tools in Open WebUI via :8082" is not the current live state. Whether
the connection was removed or never survived the 08-11 loopback change is not
determinable from this side; re-wiring it (e.g. via a URL reachable from the
container, or podman network changes) is an infra/Open WebUI task, not a
docs-only fix.

### 4. "Public mirror gap" warnings are stale — mirror has the public_safe commits

`README.md` (~lines 131-136) and `docs/mcpo-openwebui.md` §"Public mirror gap"
warn that the public GitHub copy of this repo is missing the `public_safe`
registration-mode commits. Verified today:
`github.com/CorporateTravelDC/corporatetravel-dispatch-mcp` is public
(`private: false`), default branch `main`, last pushed 2026-08-10T04:07Z, and
`origin/main` = `8f29ebe`, which contains `8a79a9f`
(feat(second-brain): ... + public-safe registration mode). A `pip install
git+https://...` from the public repo gets `DISPATCH_MCP_PUBLIC_SAFE` support.
Both warnings should be dropped or rewritten. Residual: the public repo still
has a stale sanitized `master` branch (`fe93cfe`), but it is not the default
and does not affect installs.

### 5. `dispatch_watchdog_status` describes a watchdog that never runs

`dispatch_mcp/tools/admin.py:315-322` (docstring, also the MCP tool
description): "runs every 5 minutes via ctdi-watchdog.timer ... checks ...
ollama, openwebui, acars stack". Live:

- No `ctdi-watchdog.timer`/`.service` exists at user or system level; no
  `/opt/corporatetraveldc/bin/ctdi-watchdog.sh` (the path the backend endpoint
  cites); `/var/lib/corporatetraveldc/watchdog-last-run.json` absent on host.
- Live endpoint (loopback, admin token): `GET /admin/watchdog/status` →
  `{"available": false, "reason": "no run recorded yet"}`.
- The separate stack watchdog that does exist in the internal repo
  (`scripts/watchdog.sh`, "runs as root via systemd timer every 90s") also has
  no timer installed and its log file/dir (`/var/log/corporatetraveldc/`)
  doesn't exist. Root's crontab wasn't readable from this session, but with no
  status file and no log ever written, effectively no watchdog is running.

The tool works but will always report "no run recorded yet". Fixing the
watchdog itself is a platform (ctdi-dispatch-internal) task; this repo's
docstring overpromises meanwhile.

## Tonight's internal changes — relevance verdict

- **Ollama fix (`2ff1fbb`)**: minimal relevance. This repo's only Ollama
  mention is the admin.py watchdog docstring (finding 5). The fix retired all
  `corporatetraveldc-ollama-prewarm-*` units (now masked, moved to
  `retired-20260814/`) and tightened `ollama.service` limits
  (`LLAMA_ARG_CACHE_RAM=0` etc.); `ollama.service` (system) is still active,
  bound to the tailnet IP only. Nothing in this repo documents prewarm timers
  or Ollama binding, so no additional drift from that commit.
- **Naming cleanup (`be79c47`)**: directly relevant — finding 1.

## Verified unchanged (spot checks, not full re-verification)

- Tool counts: source grep still 34 total / 26 public-safe;
  `127.0.0.1:8082/openapi.json` → 34 paths; `127.0.0.1:8083` → 26;
  `https://mcp.csexecutiveservices.com/openapi.json` → 26;
  `mcpo.csexecutiveservices.com` still dead (404).
- Both units `corporatetraveldc-mcpo{,-public}.service` loaded/active/running;
  ExecStarts match the documented wrapper flow (modulo finding 2);
  `dispatch-mcp-wrapper.sh` unchanged (extracts `DISPATCH_ADMIN_TOKEN` →
  `DISPATCH_TOKEN`, execs
  `/opt/corporatetraveldc/corporatetravel-dispatch-mcp/venv/bin/dispatch-mcp`,
  which exists).
- nginx vhost `mcp.csexecutiveservices.com` still `proxy_pass 127.0.0.1:8083`;
  SELinux `httpd_can_network_connect` still on; Open WebUI :3000 answering.
- `jsonschema>=4.0.0` pin still in `pyproject.toml`.
- `config.py` defaults match docs (`http://192.0.2.10:8000` placeholder default,
  `https://dispatch.csexecutiveservices.com` fallback); deployed env overrides
  `DISPATCH_BASE_URL=http://100.94.80.100:8000` via
  `/etc/corporatetraveldc/dispatch.env`.

Per task rules: nothing committed/staged/pushed; no README/CLAUDE.md/docs
edits made — findings above are report-only.
