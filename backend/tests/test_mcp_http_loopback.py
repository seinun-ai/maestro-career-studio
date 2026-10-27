"""A single-worker backend must serve sync MCP tools that call its REST API."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import anyio
import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation

from mcp_server import server as srv
from mcp_server.profiles import HUNT_TOOLS


BACKEND = Path(__file__).resolve().parents[1]
CLIENT_INFO = Implementation(name="loopback-test", version="1")


def _backend_env(root: Path, url: str) -> dict[str, str]:
    # Copied from tests/sync/conftest.py's pinned _home_env, with sync disabled.
    env = os.environ.copy()
    env.pop("TEST_DATABASE_URL", None)
    for name in ("data", "settings", "applications", "base_resumes", "kb_documents", "logs", "exports"):
        directory = root / name
        directory.mkdir(parents=True, exist_ok=True)
        env[f"{name.upper()}_DIR"] = str(directory)
    env.update(
        DATABASE_URL=f"sqlite:///{root / 'data' / 'loopback.sqlite3'}",
        BACKEND_URL=url,
        SYNC_KEY_FILE="", SYNC_REMOTE_URL="", SYNC_PUBLIC_HOST="",
        OPENAI_API_KEY="", GEMINI_API_KEY="", ANTHROPIC_API_KEY="", OPENROUTER_API_KEY="",
        OPENAI_BASE_URL="",
        LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="", LANGFUSE_HOST="",
        ALLOWED_HOSTS="127.0.0.1,localhost",
        NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost",
    )
    return env


@pytest.fixture
def loopback_backend(tmp_path):
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    env = _backend_env(tmp_path, url)
    with (tmp_path / "uvicorn.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(port), "--workers", "1", "--no-access-log", "--log-level", "error"],
            cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(base_url=url, timeout=1, trust_env=False) as http:
                deadline = time.monotonic() + 20
                last_health = "no response"
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        pytest.fail(f"Loopback backend exited before /health; see {log.name}")
                    try:
                        response = http.get("/health")
                        last_health = f"HTTP {response.status_code}"
                        if response.status_code == 200:
                            break
                    except httpx.TransportError as exc:
                        last_health = str(exc)
                    time.sleep(0.05)
                else:
                    pytest.fail(f"Loopback /health timed out: {last_health}; see {log.name}")
            yield url
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


@pytest.mark.integration
async def test_single_worker_mcp_loopback_tools_and_client_label(loopback_backend):
    # The process owns the sessions: avoid a DELETE waiting on a deadlocked server
    # during failure cleanup. The fixture always kills and reaps that process.
    timeout = httpx.Timeout(30, read=300)
    async with (
        httpx.AsyncClient(trust_env=False, timeout=timeout) as http_client,
        streamable_http_client(
            f"{loopback_backend}/mcp", http_client=http_client, terminate_on_close=False
        ) as streams,
    ):
        async with ClientSession(streams[0], streams[1], client_info=CLIENT_INFO) as session:
            with anyio.fail_after(10):
                await session.initialize()
                tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            assert len(names) == 92
            assert set(names) == set(srv.list_registered_tool_names("full"))

            # Without offload_tools, sync list_jobs blocks this sole uvicorn
            # event loop while waiting for GET /api/jobs on the very same loop.
            with anyio.fail_after(10):
                jobs = await session.call_tool("list_jobs", {})
            assert not jobs.isError, jobs.content

            # Entity creation is LLM-free and persists ctx's initialize label.
            with anyio.fail_after(10):
                created = await session.call_tool(
                    "kb_create_entity", {"kind": "project", "title": "Loopback test project"}
                )
            assert not created.isError, created.content
            entity_id = json.loads(created.content[0].text)["id"]
            async with httpx.AsyncClient(
                base_url=loopback_backend, timeout=5, trust_env=False
            ) as http:
                response = await http.get(f"/api/kb/entities/{entity_id}")
            response.raise_for_status()
            entity = response.json()
            assert entity["origin"] == "mcp"
            assert entity["origin_detail"] == "loopback-test"
            assert [event["label"] for event in entity["timeline"] if event["type"] == "created"] == [
                "Item created by Loopback Test"
            ]

    async with (
        httpx.AsyncClient(trust_env=False, timeout=timeout) as http_client,
        streamable_http_client(
            f"{loopback_backend}/mcp/hunt", http_client=http_client, terminate_on_close=False
        ) as streams,
    ):
        async with ClientSession(streams[0], streams[1], client_info=CLIENT_INFO) as session:
            with anyio.fail_after(10):
                await session.initialize()
                tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            assert len(names) == len(HUNT_TOOLS)
            assert set(names) == HUNT_TOOLS
