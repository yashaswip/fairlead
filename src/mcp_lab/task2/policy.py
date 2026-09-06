from __future__ import annotations

from typing import Any, Literal

import jwt

Role = Literal["admin", "viewer"]

UNAUTHORIZED_TOOL = -32001
INVALID_REQUEST = -32600
INVALID_PARAMS = -32602
JWT_ALG = "HS256"


def jsonrpc_error(
    id_: str | int | None,
    code: int,
    message: str,
    data: Any | None = None,
) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": err}


def unauthorized(id_: str | int | None, tool: str) -> dict[str, Any]:
    return jsonrpc_error(id_, UNAUTHORIZED_TOOL, "Unauthorized Tool Call", {"tool": tool})


def parse_jsonrpc(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise RpcParseError(INVALID_REQUEST, "payload must be a JSON-RPC object")
    if body.get("jsonrpc") != "2.0" or not isinstance(body.get("method"), str):
        raise RpcParseError(INVALID_REQUEST, "invalid JSON-RPC envelope")
    return body


def mint_token(role: Role, secret: str) -> str:
    return jwt.encode({"role": role}, secret, algorithm=JWT_ALG)


def role_from_bearer(header: str | None, secret: str) -> Role | None:
    if not header or not header.startswith("Bearer "):
        return None
    token = header.removeprefix("Bearer ").strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None
    role = payload.get("role")
    if role in ("admin", "viewer"):
        return role
    return None


def tool_name(params: Any) -> str | None:
    if not isinstance(params, dict):
        return None
    name = params.get("name")
    return name if isinstance(name, str) else None


def allowed(role: Role, name: str) -> bool:
    if name.startswith("admin_"):
        return role == "admin"
    return True


class RpcParseError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
