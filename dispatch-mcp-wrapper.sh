#!/bin/bash
# dispatch-mcp-wrapper.sh
# Extracts DISPATCH_ADMIN_TOKEN from secrets file without executing the file as bash
# (the file contains passwords with shell-special chars).
# Sources DISPATCH_TOKEN for /admin/* MCP tools.

SECRETS_FILE="/etc/corporatetraveldc/dispatch-secrets.env"

if [[ -f "$SECRETS_FILE" ]]; then
    DISPATCH_TOKEN=$(grep '^DISPATCH_ADMIN_TOKEN=' "$SECRETS_FILE" | head -1 | cut -d= -f2-)
    export DISPATCH_TOKEN
fi

exec "/opt/corporatetraveldc/corporatetravel-dispatch-mcp/venv/bin/dispatch-mcp" "$@"
