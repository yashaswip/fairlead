import json

import httpx
from fastapi.testclient import TestClient

from mcp_lab.task3.redact import StreamRedactor, redact_complete
from mcp_lab.task3.server import create_app


def test_redacts_email_ssn_and_luhn_cards():
    text = "ping ada@northwind.io ssn 078-05-1120 card 4111 1111 1111 1111 thanks"
    out = redact_complete(text)
    assert "[REDACTED]" in out
    assert "ada@" not in out
    assert "078-05-1120" not in out
    assert "4111" not in out


def test_holds_partial_email_across_chunks():
    r = StreamRedactor()
    joined = r.push("reach me at ada.l") + r.push("ovelace@example.com tomorrow") + r.flush()
    assert "@example.com" not in joined
    assert "[REDACTED]" in joined


def test_sse_proxy_redacts_split_email():
    frames = [
        b'data: {"choices":[{"delta":{"content":"mail ada.l"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"ovelace@example.com now"}}]}\n\n',
        b"data: [DONE]\n\n",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=b"".join(frames))

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(upstream="http://llm/v1/chat/completions", http=http)
    with TestClient(app) as client:
        res = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}], "stream": True})
    body = res.text
    assert "[REDACTED]" in body
    assert "@example.com" not in body
    texts = []
    for line in body.splitlines():
        if line.startswith("data:") and "[DONE]" not in line:
            payload = json.loads(line[5:].strip())
            texts.append(((payload.get("choices") or [{}])[0].get("delta") or {}).get("content") or "")
    assert "".join(texts).count("[REDACTED]") >= 1
