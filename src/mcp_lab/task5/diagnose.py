from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from mcp_lab import env


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _tcp(host: str, port: int, timeout: float = 1.5) -> Check:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return Check(f"tcp {host}:{port}", True, "open")
    except OSError as exc:
        return Check(f"tcp {host}:{port}", False, str(exc))


def _dns(host: str) -> Check:
    try:
        addr = socket.getaddrinfo(host, None)[0][4][0]
        return Check(f"dns {host}", True, str(addr))
    except OSError as exc:
        return Check(f"dns {host}", False, str(exc))


def _file(label: str, path: str | None) -> Check:
    if not path:
        return Check(label, False, "path not set")
    return Check(label, Path(path).exists(), path)


def main() -> int:
    target = env("DOWNSTREAM_MCP_URL", "http://127.0.0.1:8091/mcp")
    parsed = urlparse(target)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    strict = os.environ.get("ZTNA_STRICT") == "1"

    checks = [_dns(host), _tcp(host, port)]
    cert = _file("client cert", os.environ.get("ZTNA_CLIENT_CERT"))
    key = _file("client key", os.environ.get("ZTNA_CLIENT_KEY"))
    if strict:
        checks.extend([cert, key])
    else:
        checks.append(Check(cert.name, True, f"{cert.detail} ({'present' if cert.ok else 'optional'})"))
        checks.append(Check(key.name, True, f"{key.detail} ({'present' if key.ok else 'optional'})"))

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "unset (direct egress)"
    checks.append(Check("https_proxy", True, proxy))
    checks.append(Check("no_proxy", True, os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or "unset"))

    failed = False
    for c in checks:
        mark = "ok" if c.ok else "FAIL"
        print(f"{mark:<4} {c.name} — {c.detail}", file=__import__("sys").stderr)
        if not c.ok:
            failed = True

    if failed:
        print(
            "\nLikely ZTNA miss: mTLS material missing or the MCP hop is not reachable from this identity.",
            file=__import__("sys").stderr,
        )
        return 1
    print("\npath looks healthy from this host", file=__import__("sys").stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
