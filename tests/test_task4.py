import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from mcp_lab.task4.errors import gateway_error
from mcp_lab.task4.limiter import TokenWindow, estimate_tokens
from mcp_lab.task4.server import create_app


def test_sliding_window_trips_at_budget(tmp_path: Path):
    lim = TokenWindow(str(tmp_path / "t.sqlite"), 100, window_ms=60_000)
    assert lim.consume("k1", 80, now_ms=1_000).allowed
    assert not lim.consume("k1", 30, now_ms=1_100).allowed
    assert lim.consume("k1", 30, now_ms=62_000).allowed
    lim.close()


def test_token_estimate_is_prompt_plus_max_tokens():
    assert estimate_tokens({"messages": [{"role": "user", "content": "abcd"}], "max_tokens": 10}) == 11


def test_errors_stay_public():
    err = gateway_error("timeout", "gw_1")
    assert "stack" not in err["error"]["message"]
    assert err["error"]["code"] == "timeout"
    assert "Traceback" not in json.dumps(err)


def _router(tmp_path: Path, handler, timeout_ms: int = 50):
    lim = TokenWindow(str(tmp_path / "gw.sqlite"), 50_000)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(
        limiter=lim,
        primary="http://primary/v1/chat/completions",
        backup="http://backup/v1/chat/completions",
        timeout_ms=timeout_ms,
        http=http,
    )
    return TestClient(app)


def test_429_fails_over_to_backup(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "primary":
            return httpx.Response(429, json={"error": "slow down"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "from-backup"}}]})

    with _router(tmp_path, handler) as client:
        res = client.post(
            "/v1/chat/completions",
            headers={"authorization": "Bearer tenant_a"},
            json={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 8},
        )
    assert res.status_code == 200
    assert res.headers["x-model-route"] == "backup"
    assert "from-backup" in res.text
    assert "slow down" not in res.text


def test_timeout_fails_over_to_backup(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "primary":
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "from-backup"}}]})

    with _router(tmp_path, handler, timeout_ms=50) as client:
        res = client.post(
            "/v1/chat/completions",
            headers={"authorization": "Bearer tenant_a"},
            json={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 8},
        )
    assert res.status_code == 200
    assert res.headers["x-model-route"] == "backup"
    assert "from-backup" in res.text


def test_rate_limit_returns_gateway_error(tmp_path: Path):
    lim = TokenWindow(str(tmp_path / "gw.sqlite"), 5)
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    app = create_app(
        limiter=lim,
        primary="http://primary/v1",
        backup="http://backup/v1",
        timeout_ms=50,
        http=http,
    )
    with TestClient(app) as client:
        res = client.post(
            "/v1/chat/completions",
            headers={"authorization": "Bearer tenant_a"},
            json={"messages": [{"role": "user", "content": "abcdefghij"}], "max_tokens": 20},
        )
    assert res.status_code == 429
    body = res.json()["error"]
    assert body["code"] == "rate_limited"
    assert "request_id" in body
