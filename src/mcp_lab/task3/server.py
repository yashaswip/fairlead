from __future__ import annotations

import json
import os

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from mcp_lab import configure_logging, env, env_int
from mcp_lab.task3.redact import StreamRedactor, rewrite_sse_block

log = configure_logging("llm-gw")


def create_app(*, upstream: str, upstream_key: str = "", http: httpx.AsyncClient | None = None) -> FastAPI:
    app = FastAPI()
    app.state.upstream = upstream
    app.state.upstream_key = upstream_key
    app.state.http = http

    @app.post("/v1/chat/completions")
    async def completions(req: Request):
        body = await req.json()
        stream = body.get("stream", True)
        headers = {"content-type": "application/json"}
        if req.app.state.upstream_key:
            headers["authorization"] = f"Bearer {req.app.state.upstream_key}"

        client = req.app.state.http
        owns = client is None
        if owns:
            client = httpx.AsyncClient(timeout=None)
        try:
            upstream = await client.send(
                client.build_request("POST", req.app.state.upstream, headers=headers, json={**body, "stream": stream}),
                stream=True,
            )
        except httpx.HTTPError as exc:
            if owns:
                await client.aclose()
            log.info("upstream connect failed: %s", exc)
            return JSONResponse({"error": {"message": "upstream unreachable"}}, status_code=502)

        if not stream:
            payload = await upstream.aread()
            if owns:
                await upstream.aclose()
                await client.aclose()
            return JSONResponse(json.loads(payload), status_code=upstream.status_code)

        async def frames():
            redactor = StreamRedactor()
            carry = ""
            try:
                async for raw in upstream.aiter_text():
                    carry += raw
                    parts = carry.split("\n\n")
                    carry = parts.pop() if parts else ""
                    for part in parts:
                        rewritten = rewrite_sse_block(part, redactor, ending=False)
                        if rewritten.strip():
                            yield rewritten + "\n\n"
                if carry.strip():
                    rewritten = rewrite_sse_block(carry, redactor, ending=True)
                    if rewritten.strip():
                        yield rewritten + "\n\n"
                else:
                    leftover = redactor.flush()
                    if leftover:
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "object": "chat.completion.chunk",
                                    "choices": [{"index": 0, "delta": {"content": leftover}}],
                                }
                            )
                            + "\n\n"
                        )
            finally:
                await upstream.aclose()
                if owns:
                    await client.aclose()

        return StreamingResponse(frames(), media_type="text/event-stream", status_code=upstream.status_code)

    return app


app = create_app(
    upstream=env("UPSTREAM_LLM_URL", "http://127.0.0.1:8092/v1/chat/completions"),
    upstream_key=os.environ.get("UPSTREAM_LLM_KEY", ""),
)


def main() -> None:
    port = env_int("GUARDRAIL_PORT", 8081)
    log.info("streaming guardrail on :%s -> %s", port, app.state.upstream)
    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None)


if __name__ == "__main__":
    main()
