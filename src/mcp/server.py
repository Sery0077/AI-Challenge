from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

mcp_server = FastMCP("local-tool-demo", host="127.0.0.1")


@mcp_server.tool(description="Returns a simple pong response.")
def ping() -> str:
    return "pong"


@mcp_server.tool(description="Adds two integers and returns the sum.")
def add(a: int, b: int) -> int:
    return a + b


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="streamable-http",
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    mcp_server.settings.port = args.port
    mcp_server.run(transport=args.transport)
