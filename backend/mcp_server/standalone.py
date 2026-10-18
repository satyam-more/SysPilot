"""
Standalone runner for the MCP server over Streamable HTTP via uvicorn.

Uses the SAME get_mcp_app() path that the FastAPI mount uses in production,
so behaviour is identical. Preferred over mcp.run() for testing with the
MCP Inspector.

    .venv/bin/python -m backend.mcp_server.standalone
"""

import logging

import uvicorn

from backend.mcp_server.server import get_mcp_app

logging.basicConfig(level=logging.INFO)

app = get_mcp_app(path="/mcp")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
