"""
MCP tool registrations for the System Health Assistant.

Each tool is a plain function decorated with @mcp.tool(). The MCP SDK derives
the input schema from the type hints and the tool description from the
docstring, then exposes them to any MCP client (including Alexa+).

For now this contains a single trivial ping tool to verify the MCP handshake.
Real diagnostic tools are added in later steps.
"""

from backend.mcp_server.server import mcp


@mcp.tool()
def ping() -> str:
    """
    Health check. Returns 'pong' to confirm the MCP server is reachable and
    tool invocation works. Use this to verify connectivity.
    """
    return "pong"
