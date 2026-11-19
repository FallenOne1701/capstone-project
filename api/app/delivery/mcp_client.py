"""Calls MCP Server 1 (Google Docs / Gmail) over stdio. Only drafts and appends; sending is denylisted."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

from app.config import get_settings

DENYLIST = {"gmail_send_email"}


class McpDeliveryError(RuntimeError):
    pass


def _server_env() -> dict[str, str]:
    s = get_settings()
    missing = [k for k, v in (("GOOGLE_CLIENT_ID", s.google_client_id), ("GOOGLE_CLIENT_SECRET", s.google_client_secret),
                              ("GOOGLE_REFRESH_TOKEN", s.google_refresh_token)) if not v]
    if missing:
        raise McpDeliveryError(f"Google credentials not configured: {', '.join(missing)}")
    env = {"GOOGLE_CLIENT_ID": s.google_client_id, "GOOGLE_CLIENT_SECRET": s.google_client_secret,
           "GOOGLE_REFRESH_TOKEN": s.google_refresh_token, "DOTENV_CONFIG_QUIET": "true",
           "PATH": os.environ.get("PATH", "")}
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    return env


def google_status() -> dict:
    """Cheap readiness for /health (no Google call, since Railway polls it): names of what is missing, never values."""
    s = get_settings()
    missing = []
    if shutil.which(s.node_command) is None:
        missing.append("node")
    if not (Path(s.mcp_server_dir) / "dist" / "server.js").exists():
        missing.append("mcp_build")
    for name, value in (("GOOGLE_CLIENT_ID", s.google_client_id), ("GOOGLE_CLIENT_SECRET", s.google_client_secret),
                        ("GOOGLE_REFRESH_TOKEN", s.google_refresh_token), ("PULSE_DOC_ID", s.pulse_doc_id)):
        if not value:
            missing.append(name)
    return {"ready": not missing, "missing": missing}


async def _call(name: str, args: dict) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    s = get_settings()
    server = Path(s.mcp_server_dir) / "dist" / "server.js"
    params = StdioServerParameters(command=s.node_command, args=[str(server)], env=_server_env(),
                                   cwd=str(s.mcp_server_dir))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
    text = "".join(getattr(c, "text", "") for c in (result.content or []))
    if getattr(result, "isError", False):
        raise McpDeliveryError(f"{name} failed: {text[:300]}")
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {"raw": text[:500]}


def call_tool(name: str, args: dict) -> dict:
    if name in DENYLIST:
        raise McpDeliveryError(f"{name} is not allowed (drafts only)")
    s = get_settings()
    if not (Path(s.mcp_server_dir) / "dist" / "server.js").exists():
        raise McpDeliveryError("MCP server not built: run npm ci && npm run build in api/mcp_server")
    try:
        return asyncio.run(asyncio.wait_for(_call(name, args), timeout=s.mcp_timeout_s))
    except McpDeliveryError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise McpDeliveryError(f"{name} failed: {type(exc).__name__}: {exc}") from exc
