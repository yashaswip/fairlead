from __future__ import annotations

from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mcp_lab import configure_logging, env, env_int
from mcp_lab.task2.policy import (
    RpcParseError,
    allowed,
    jsonrpc_error,
    parse_jsonrpc,
    role_from_bearer,
    tool_name,
    unauthorized,
)

log = configure_logging("mcp-gw")
app = FastAPI()

TOKENS = {
    "admin": env("TOKEN_ADMIN", "adm_live_replace_me"),
    "viewer": env("TOKEN_VIEWER", "vw_live_replace_me"),
}
DOWNSTREAM = env("DOWNSTREAM_MCP_URL", "http://127.0.0.1:8091/mcp")


@app.post("/mcp")
async def proxy(req: Request) -> JSONResponse:
    role = role_from_bearer(req.headers.get("authorization"), TOKENS)
    if role is None:
        return JSONResponse({"error": "invalid_token"}, status_code=401)

    try:
        rpc = parse_jsonrpc(await req.json())
    except RpcParseError as exc:
        return JSONResponse(jsonrpc_error(None, exc.code, str(exc)))

    rpc_id = rpc.get("id")
    method = rpc["method"]

    if method == "tools/call":
        name = tool_name(rpc.get("params"))
        if not name:
            return JSONResponse(jsonrpc_error(rpc_id, -32602, "tools/call requires params.name"))
        if not allowed(role, name):
            log.info("blocked admin tool role=%s name=%s", role, name)
            return JSONResponse(unauthorized(rpc_id, name))

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(DOWNSTREAM, json=rpc)
        return JSONResponse(res.json(), status_code=res.status_code)
    except httpx.HTTPError as exc:
        log.info("downstream failed: %s", exc)
        return JSONResponse(jsonrpc_error(rpc_id, -32002, "downstream MCP unavailable"), status_code=502)


def main() -> None:
    port = env_int("GATEWAY_PORT", 8080)
    log.info("proxy on :%s -> %s", port, DOWNSTREAM)
    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None)


if __name__ == "__main__":
    main()
