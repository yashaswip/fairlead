from mcp_lab.task2.policy import allowed, parse_jsonrpc, role_from_bearer, unauthorized

TOKENS = {"admin": "adm_live_replace_me", "viewer": "vw_live_replace_me"}


def test_bearer_maps_to_role():
    assert role_from_bearer("Bearer adm_live_replace_me", TOKENS) == "admin"
    assert role_from_bearer("Bearer vw_live_replace_me", TOKENS) == "viewer"
    assert role_from_bearer("Bearer nope", TOKENS) is None


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
