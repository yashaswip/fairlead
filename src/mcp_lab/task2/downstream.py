from __future__ import annotations

from typing import Any

import uvicorn
from fastapi import FastAPI, Request

from mcp_lab import configure_logging, env_int

log = configure_logging("downstream-mcp")
app = FastAPI()

TOOLS = [
    {"name": "lookup_order", "description": "Fetch an order by id"},
    {"name": "admin_reset_key", "description": "Rotate an API key"},
    {"name": "admin_purge_cache", "description": "Drop the edge cache"},
]


@app.post("/mcp")
async def mcp(req: Request) -> dict[str, Any]:
    body = await req.json()
    rpc_id = body.get("id")
    method = body.get("method")

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = (body.get("params") or {}).get("name", "unknown")
        log.info("executed %s", name)
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"content": [{"type": "text", "text": f"ok:{name}"}]},
        }

    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    port = env_int("DOWNSTREAM_PORT", 8091)
    log.info("listening on :%s", port)
    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None)


if __name__ == "__main__":
    main()
