from __future__ import annotations

import json

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

import os

from mcp_lab import configure_logging, env, env_int
from mcp_lab.task3.redact import StreamRedactor, rewrite_sse_block

log = configure_logging("llm-gw")
app = FastAPI()
UPSTREAM = env("UPSTREAM_LLM_URL", "http://127.0.0.1:8092/v1/chat/completions")
UPSTREAM_KEY = os.environ.get("UPSTREAM_LLM_KEY", "")


@app.post("/v1/chat/completions")
async def completions(req: Request):
    body = await req.json()
    stream = body.get("stream", True)
    headers = {"content-type": "application/json"}
    if UPSTREAM_KEY:
        headers["authorization"] = f"Bearer {UPSTREAM_KEY}"

    try:
        client = httpx.AsyncClient(timeout=None)
        upstream = await client.send(
            client.build_request("POST", UPSTREAM, headers=headers, json={**body, "stream": stream}),
            stream=True,
        )
    except httpx.HTTPError as exc:
        log.info("upstream connect failed: %s", exc)
        return JSONResponse({"error": {"message": "upstream unreachable"}}, status_code=502)

    if not stream:
        payload = await upstream.aread()
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
                    yield f"data: {json.dumps({'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': {'content': leftover}}]})}\n\n"
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(frames(), media_type="text/event-stream", status_code=upstream.status_code)


def main() -> None:
    port = env_int("GUARDRAIL_PORT", 8081)
    log.info("streaming guardrail on :%s -> %s", port, UPSTREAM)
    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None)


if __name__ == "__main__":
    main()
