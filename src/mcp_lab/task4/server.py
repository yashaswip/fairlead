from __future__ import annotations

from dataclasses import dataclass

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mcp_lab import configure_logging, env, env_int
from mcp_lab.task4.errors import classify_upstream, gateway_error, new_request_id
from mcp_lab.task4.limiter import TokenWindow, estimate_tokens

log = configure_logging("router")
app = FastAPI()
LIMITER = TokenWindow(env("SQLITE_PATH", "./data/gateway.sqlite"), env_int("RATE_LIMIT_TOKENS_PER_MIN", 50_000))
PRIMARY = env("PRIMARY_LLM_URL", "http://127.0.0.1:8093/v1/chat/completions")
BACKUP = env("BACKUP_LLM_URL", "http://127.0.0.1:8094/v1/chat/completions")
TIMEOUT_MS = env_int("PRIMARY_TIMEOUT_MS", 3000)


@dataclass
class Attempt:
    ok: bool
    payload: dict | None = None
    status: int = 0
    timed_out: bool = False


@app.post("/v1/chat/completions")
async def completions(req: Request) -> JSONResponse:
    request_id = new_request_id()
    key = _bearer(req.headers.get("authorization"))
    if not key:
        return JSONResponse(gateway_error("unauthorized", request_id), status_code=401)

    body = await req.json()
    if not isinstance(body.get("messages"), list):
        return JSONResponse(gateway_error("bad_request", request_id), status_code=400)

    decision = LIMITER.consume(key, estimate_tokens(body))
    if not decision.allowed:
        retry = max(1, (decision.retry_after_ms + 999) // 1000)
        return JSONResponse(
            gateway_error("rate_limited", request_id),
            status_code=429,
            headers={"retry-after": str(retry)},
        )

    primary = await _call(PRIMARY, body, TIMEOUT_MS)
    if primary.ok:
        return JSONResponse(primary.payload, headers={"x-model-route": "primary", "x-request-id": request_id})

    if primary.status == 429 or primary.timed_out:
        log.info("failing over request_id=%s reason=%s", request_id, "timeout" if primary.timed_out else "429")
        backup = await _call(BACKUP, body, TIMEOUT_MS)
        if backup.ok:
            return JSONResponse(backup.payload, headers={"x-model-route": "backup", "x-request-id": request_id})
        code = classify_upstream(backup.status, backup.timed_out)
        return JSONResponse(gateway_error(code, request_id), status_code=502)

    return JSONResponse(
        gateway_error(classify_upstream(primary.status, primary.timed_out), request_id),
        status_code=502,
    )


async def _call(url: str, body: dict, timeout_ms: int) -> Attempt:
    try:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
            res = await client.post(url, json=body)
        if res.status_code == 429:
            return Attempt(ok=False, status=429)
        if res.is_error:
            return Attempt(ok=False, status=res.status_code)
        return Attempt(ok=True, payload=res.json(), status=res.status_code)
    except httpx.TimeoutException:
        return Attempt(ok=False, timed_out=True)
    except httpx.HTTPError as exc:
        log.info("upstream error: %s", exc)
        return Attempt(ok=False, status=0)


def _bearer(header: str | None) -> str | None:
    if not header or not header.startswith("Bearer "):
        return None
    token = header.removeprefix("Bearer ").strip()
    return token or None


def main() -> None:
    port = env_int("ROUTER_PORT", 8082)
    log.info("model router on :%s", port)
    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None)


if __name__ == "__main__":
    main()
