from __future__ import annotations

import argparse
import asyncio
import json

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from mcp_lab import env_int

app = FastAPI()
MODE = "leak"


@app.post("/v1/chat/completions")
async def completions(req: Request):
    body = await req.json()
    stream = body.get("stream", True)

    if MODE == "429":
        return JSONResponse({"error": {"message": "overloaded"}}, status_code=429)

    if MODE == "slow":
        await asyncio.sleep(5)

    if MODE == "leak":
        chunks = [
            "contact ada.l",
            "ovelace@example.com ssn 078-05-1120",
            " card 4111 1111 1111 1111 thanks",
        ]
    else:
        chunks = ["ok from backup"]

    if not stream:
        return {"choices": [{"message": {"content": "".join(chunks)}}]}

    async def frames():
        for part in chunks:
            payload = {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": part}}]}
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.05)
        yield "data: [DONE]\n\n"

    return StreamingResponse(frames(), media_type="text/event-stream")


def main() -> None:
    global MODE
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("leak", "ok", "429", "slow"), default="leak")
    parser.add_argument("--port", type=int, default=env_int("MOCK_LLM_PORT", 8092))
    args = parser.parse_args()
    MODE = args.mode
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_config=None)


if __name__ == "__main__":
    main()
