from pathlib import Path

from mcp_lab.task4.errors import gateway_error
from mcp_lab.task4.limiter import TokenWindow, estimate_tokens


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
