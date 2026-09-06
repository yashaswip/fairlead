from __future__ import annotations

import json
import re
from typing import Any

EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CC_CANDIDATE = re.compile(r"\b(?:\d[ \-]*?){13,19}\b")

HOLD = 48


def luhn_ok(digits: str) -> bool:
    total = 0
    alt = False
    for ch in reversed(digits):
        n = ord(ch) - 48
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


def redact_complete(text: str) -> str:
    out = EMAIL.sub("[REDACTED]", text)
    out = SSN.sub("[REDACTED]", out)

    def _cc(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            return "[REDACTED]"
        return match.group(0)

    return CC_CANDIDATE.sub(_cc, out)


class StreamRedactor:
    def __init__(self) -> None:
        self._tail = ""

    def push(self, chunk: str) -> str:
        joined = redact_complete(self._tail + chunk)
        if len(joined) <= HOLD:
            self._tail = joined
            return ""
        emit, self._tail = joined[:-HOLD], joined[-HOLD:]
        return emit

    def flush(self) -> str:
        rest, self._tail = self._tail, ""
        return rest


def rewrite_sse_block(block: str, redactor: StreamRedactor, ending: bool) -> str:
    lines_out: list[str] = []
    for line in block.split("\n"):
        if not line.startswith("data:"):
            lines_out.append(line)
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            leftover = redactor.flush()
            if leftover:
                lines_out.append(f"data: {json.dumps(_delta(leftover))}")
            lines_out.append(line)
            continue
        try:
            parsed: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError:
            lines_out.append(line)
            continue
        content = (((parsed.get("choices") or [{}])[0].get("delta") or {}).get("content"))
        if isinstance(content, str) and content:
            safe = redactor.push(content)
            if ending:
                safe += redactor.flush()
            if not safe:
                continue
            parsed["choices"][0]["delta"]["content"] = safe
            lines_out.append(f"data: {json.dumps(parsed)}")
        else:
            lines_out.append(line)
    return "\n".join(lines_out)


def _delta(content: str) -> dict[str, Any]:
    return {"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": content}}]}
