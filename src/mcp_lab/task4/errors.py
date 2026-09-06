from __future__ import annotations

import secrets
import time
from typing import Literal

PublicCode = Literal["rate_limited", "timeout", "overloaded", "unavailable", "unauthorized", "bad_request"]

_MESSAGES: dict[PublicCode, str] = {
    "rate_limited": "Tenant token budget exceeded",
    "timeout": "Upstream model timed out",
    "overloaded": "Upstream model rejected the request",
    "unavailable": "No healthy upstream model",
    "unauthorized": "Missing or invalid tenant API key",
    "bad_request": "Malformed completion request",
}


def gateway_error(code: PublicCode, request_id: str) -> dict:
    return {"error": {"code": code, "message": _MESSAGES[code], "request_id": request_id}}


def classify_upstream(status: int, timed_out: bool) -> PublicCode:
    if timed_out:
        return "timeout"
    if status == 429:
        return "overloaded"
    return "unavailable"


def new_request_id() -> str:
    return f"gw_{int(time.time()):x}_{secrets.token_hex(3)}"
