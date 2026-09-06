import json

import httpx
from fastapi.testclient import TestClient

from mcp_lab.task2.policy import allowed, mint_token, parse_jsonrpc, role_from_bearer, unauthorized
from mcp_lab.task2.proxy import create_app

SECRET = "test-secret-must-be-32-bytes-min"


def test_jwt_maps_to_role():
    assert role_from_bearer(f"Bearer {mint_token('admin', SECRET)}", SECRET) == "admin"
    assert role_from_bearer(f"Bearer {mint_token('viewer', SECRET)}", SECRET) == "viewer"
    assert role_from_bearer("Bearer admin", SECRET) == "admin"
    assert role_from_bearer("Bearer viewer", SECRET) == "viewer"
    assert role_from_bearer("Bearer nope", SECRET) is None


def test_admin_tools_are_gated():
    assert allowed("viewer", "lookup_order")
    assert not allowed("viewer", "admin_reset_key")
    assert allowed("admin", "admin_reset_key")


def test_unauthorized_uses_32001():
    err = unauthorized(7, "admin_reset_key")
    assert err["error"]["code"] == -32001
    assert err["error"]["message"] == "Unauthorized Tool Call"


def test_jsonrpc_envelope():
    assert parse_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["method"] == "tools/list"
    try:
        parse_jsonrpc({"method": "tools/list"})
    except Exception:
        return
    raise AssertionError("envelope must fail")


def _client(handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app = create_app(downstream="http://downstream/mcp", secret=SECRET, http=http)
    return TestClient(app)


def test_viewer_admin_tool_is_blocked_without_downstream():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    with _client(handler) as client:
        res = client.post(
            "/mcp",
            headers={"authorization": f"Bearer {mint_token('viewer', SECRET)}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "admin_reset_key"}},
        )
    assert res.json()["error"]["code"] == -32001
    assert seen == []


def test_plain_bearer_viewer_is_blocked():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    with _client(handler) as client:
        res = client.post(
            "/mcp",
            headers={"authorization": "Bearer viewer"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "admin_reset_key"}},
        )
    assert res.json()["error"]["code"] == -32001
    assert res.json()["error"]["message"] == "Unauthorized Tool Call"
    assert seen == []


def test_tools_list_is_forwarded():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["method"] == "tools/list"
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [{"name": "lookup_order"}]}},
        )

    with _client(handler) as client:
        res = client.post(
            "/mcp",
            headers={"authorization": f"Bearer {mint_token('viewer', SECRET)}"},
            json={"jsonrpc": "2.0", "id": 9, "method": "tools/list"},
        )
    assert res.json()["result"]["tools"][0]["name"] == "lookup_order"


def test_admin_can_call_admin_tool():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": "ok"}]}},
        )

    with _client(handler) as client:
        res = client.post(
            "/mcp",
            headers={"authorization": f"Bearer {mint_token('admin', SECRET)}"},
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "admin_reset_key"}},
        )
    assert "error" not in res.json()
