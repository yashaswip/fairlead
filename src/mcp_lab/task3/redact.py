from __future__ import annotations

import json
import re
from typing import Any

EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CC_CANDIDATE = re.compile(r"\b(?:\d[ \-]*?){13,19}\b")

HOLD = 48
_DIGIT_TAIL = re.compile(r"(?:\d[\d \-]{0,22})$")
_EMAIL_INCOMPLETE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]*$")
_LOCAL_DOT = re.compile(r"[A-Za-z0-9._%+\-]+\.[A-Za-z0-9._%+\-]+$")


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


def _hold_tail(text: str) -> tuple[str, str]:
    """Hold only a suffix that could still become email / SSN / PAN — emit the rest now (TTFT)."""
    candidates: list[str] = []
    digit = _DIGIT_TAIL.search(text)
    if digit:
        raw = digit.group(0)
        digits = re.sub(r"\D", "", raw)
        if "-" in raw or len(digits) >= 3:
            candidates.append(raw)
    if "@" in text[-HOLD:]:
        found = _EMAIL_INCOMPLETE.search(text)
        if found:
            candidates.append(found.group(0))
    else:
        found = _LOCAL_DOT.search(text)
        if found:
            candidates.append(found.group(0))
    if not candidates:
        return text, ""
    tail = max(candidates, key=len)
    if len(tail) > HOLD:
        tail = tail[-HOLD:]
    if not text.endswith(tail):
        return text, ""
    return text[: -len(tail)], tail


class StreamRedactor:
    def __init__(self) -> None:
        self._tail = ""

    def push(self, chunk: str) -> str:
        joined = redact_complete(self._tail + chunk)
        emit, self._tail = _hold_tail(joined)
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
        delta = ((parsed.get("choices") or [{}])[0].get("delta") or {})
        content = delta.get("content")
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
