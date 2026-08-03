"""Second-brain tools — wraps /api/v1/remember on the dispatch platform.

Manual vault capture ("remember this"), driven from any MCP client instead
of only from a shell on the Pi. Same scrub gate, same write path, same
index call as the CLI (second_brain.remember) and the REST route
(web/routes/remember.py) it wraps -- one code path underneath all three.

Requires a valid DISPATCH_TOKEN bearer token, same as the other admin-tier
write endpoints on this platform.
"""

import json
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

from dispatch_mcp.client import dispatch_post, handle_http_error
from dispatch_mcp.config import DISPATCH_TOKEN


class RememberInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    text: str = Field(
        ...,
        description="The fact, finding, or note to capture into the second-brain vault.",
        min_length=1,
    )
    tags: str = Field(
        default="",
        description="Comma-separated tags (e.g. 'infra,mcp,ops-findings'). Defaults to 'manual,high-priority' server-side if omitted.",
    )


def register(mcp: FastMCP) -> None:

    def _check_token() -> str | None:
        """Return error string if DISPATCH_TOKEN is not set, else None."""
        if not DISPATCH_TOKEN:
            return (
                "Error: DISPATCH_TOKEN is not set. "
                "The remember endpoint requires a bearer token. "
                "Create one on the Pi with: csex-token create "
                "Then set DISPATCH_TOKEN env var before starting the MCP server."
            )
        return None

    @mcp.tool(
        name="dispatch_remember",
        annotations={
            "title": "Capture a Note into the Second-Brain Vault (Token Required)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def dispatch_remember(params: RememberInput) -> str:
        """Capture a manual note into the second-brain vault (01-Sources/manual/).

        Runs through the same CUI/PII scrub gate as every other ingestion
        path (daily/weekly digest, RSS poller). The gate BLOCKS rather than
        redacts: if the text looks like CUI radio data (SHARES/HEARS/HEART
        co-occurring with a frequency-shaped token) or contains an
        SSN-shaped token, the call fails with a 422 and nothing is written.
        Requires DISPATCH_TOKEN env var to be set.

        Args:
            params (RememberInput):
                - text (str): the note to capture
                - tags (str, optional): comma-separated tags

        Returns:
            str: JSON {"status": "ok", "path": "<vault-relative path written>"},
                 or an error string (missing token, scrub-gate block, etc.)

        Examples:
            - "Remember that the FDPS feed needs re-provisioning after the Pi swap" -> params.text=..., params.tags='infra,ops-findings'
        """
        if err := _check_token():
            return err
        try:
            body = {"text": params.text, "tags": params.tags}
            data = await dispatch_post("/api/v1/remember", auth=True, body=body)
            return json.dumps(data, indent=2)
        except Exception as e:
            return handle_http_error(e)
