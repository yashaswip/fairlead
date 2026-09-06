from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import time


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    used: int
    remaining: int
    retry_after_ms: int


class TokenWindow:
    def __init__(self, path: str, limit: int, window_ms: int = 60_000) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._limit = limit
        self._window_ms = window_ms
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS token_events (
              tenant TEXT NOT NULL,
              tokens INTEGER NOT NULL,
              ts INTEGER NOT NULL
            )
            """
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_tenant_ts ON token_events(tenant, ts)")
        self._db.commit()

    def consume(self, tenant: str, tokens: int, now_ms: int | None = None) -> RateDecision:
        now = now_ms if now_ms is not None else int(time() * 1000)
        start = now - self._window_ms
        with self._db:
            self._db.execute("DELETE FROM token_events WHERE ts < ?", (start,))
            used = self._db.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM token_events WHERE tenant = ? AND ts >= ?",
                (tenant, start),
            ).fetchone()[0]
            used = int(used)
            if used + tokens > self._limit:
                oldest = self._db.execute(
                    "SELECT MIN(ts) FROM token_events WHERE tenant = ? AND ts >= ?",
                    (tenant, start),
                ).fetchone()[0]
                retry = max(0, int(oldest) + self._window_ms - now) if oldest else self._window_ms
                return RateDecision(False, used, max(0, self._limit - used), retry)
            self._db.execute(
                "INSERT INTO token_events (tenant, tokens, ts) VALUES (?, ?, ?)",
                (tenant, tokens, now),
            )
            nxt = used + tokens
            return RateDecision(True, nxt, max(0, self._limit - nxt), 0)

    def close(self) -> None:
        self._db.close()


def estimate_tokens(body: dict) -> int:
    messages = body.get("messages") or []
    prompt = "\n".join(str(m.get("content") or "") for m in messages if isinstance(m, dict))
    prompt_tokens = max(1, (len(prompt) + 3) // 4)
    max_out = body.get("max_tokens")
    max_out_n = max_out if isinstance(max_out, int) and max_out >= 0 else 256
    return prompt_tokens + max_out_n
