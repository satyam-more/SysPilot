"""
System Health MCP server.

A self-hosted MCP server (Streamable HTTP, spec 2025-11-25) that exposes
system-diagnostic and guided-fix tools. Designed to be invoked by Alexa+ via
an MCP add-on, or by any MCP client / our own web front end.

Transport: Streamable HTTP at /mcp (required by Alexa+).
Safety model: read-only diagnostics run freely; any action is proposed with a
numbered fix guide and gated behind explicit human confirmation — never
executed autonomously.

Run standalone (for MCP Inspector testing):
    .venv/bin/python -m backend.mcp_server.server
"""

import logging

from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)

# The MCP server instance. Tools are registered onto this in tools.py.
mcp = MCPServer(
    name="System Health Assistant",
    instructions=(
        "A system health and troubleshooting assistant. It can read the "
        "machine's health (CPU, memory, disk, temperature), list running and "
        "startup applications, identify which apps are safe to close, detect "
        "system issues, and produce step-by-step fix guides. It NEVER runs "
        "destructive or privileged commands on its own — every fix is presented "
        "as numbered steps for the user to review and approve."
    ),
)


def get_mcp_app(path: str = "/mcp"):
    """
    Return the Streamable HTTP Starlette app to mount into FastAPI.
    Alexa+ connects to this endpoint.
    """
    return mcp.streamable_http_app(streamable_http_path=path)


def main() -> None:
    """Run the MCP server standalone over Streamable HTTP (for Inspector)."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting System Health MCP server (streamable-http) on /mcp")
    mcp.run(transport="streamable-http")


# Register all tools at import time (after `mcp` exists) so any entrypoint —
# standalone run, FastAPI mount, or test import — sees them.
from backend.mcp_server import tools  # noqa: E402,F401


if __name__ == "__main__":
    main()
