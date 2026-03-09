from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise TimeoutError(f"MCP server did not start on port {port}.")


async def _list_tools(server_url: str) -> list[str]:
    async with streamablehttp_client(server_url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            return [tool.name for tool in tools_result.tools]


def main() -> int:
    server_path = Path(__file__).with_name("server.py")
    port = _find_free_port()
    server_process = subprocess.Popen(
        [
            sys.executable,
            str(server_path),
            "--transport",
            "streamable-http",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    try:
        _wait_for_port(port)
        tool_names = asyncio.run(_list_tools(f"http://127.0.0.1:{port}/mcp"))
    finally:
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
            server_process.wait(timeout=5)

    print("MCP connection established.")
    print("Available tools:")
    for name in tool_names:
        print(f"- {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
