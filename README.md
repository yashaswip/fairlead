# Overview

MCP servers, MCP gateways, LLM gateways, security guardrails, and system integration.

Stack: Python 3.11+, official `mcp` 2.x (`MCPServer` + in-process `Client` tests), Pydantic v2, FastAPI, HS256 JWTs, httpx streaming, SQLite WAL.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Live demo (optional): leaky mock LLM on :8092, then the Task 3 proxy on :8081.

```bash
python -m mcp_lab.mocks.llm --mode leak --port 8092
python -m mcp_lab.task3.server
curl -N localhost:8081/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"hi"}],"stream":true}'
```

## Task 1: Build a Custom MCP Server with Strict Validation & Transport Handling

`src/mcp_lab/task1/server.py`

- `get_customer_record` — `customer_id` matches `CUST-\d{5}`
- `trigger_refund` — same id, `amount` > 0, `reason` ≥ 10 chars

Pydantic (`extra="forbid"`) runs on every call. Failures raise `MCPError(INVALID_PARAMS)` → JSON-RPC `-32602`. Logging is stderr only; stdout stays on the MCP wire.

```bash
python -m mcp_lab.task1.server
```

Cursor / Claude Desktop:

```json
{
  "command": "python",
  "args": ["-m", "mcp_lab.task1.server"],
  "cwd": "/absolute/path/to/mcp-gateway-lab"
}
```

Seed ids: `CUST-10428`, `CUST-22019`.

## Task 2: Implement an MCP Security Gateway Proxy (Tool Filtering & Auth)

```bash
python -m mcp_lab.task2.downstream   # :8091
python -m mcp_lab.task2.proxy        # :8080
```

`Authorization: Bearer <token>` — role is `admin` or `viewer` (plain `Bearer admin` / `Bearer viewer`, or an HS256 JWT with `{"role": ...}`).

- If method is `tools/list`, forward to the downstream MCP server
- If method is `tools/call` and `params.name` starts with `admin_`, role must be admin; otherwise return JSON-RPC `-32001 Unauthorized Tool Call` and do not call downstream

```bash
python -c "from mcp_lab.task2.policy import mint_token; print(mint_token('viewer', 'dev-only-change-me-use-32bytes-min'))"
curl -s localhost:8080/mcp \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"admin_reset_key"}}'
```

## Task 3: Implement an LLM Gateway Streaming Guardrail (PII Redaction)

SSE proxy. Chunks are rewritten as they arrive. A 48-char holdback covers emails / SSNs / PANs split across reads. Cards need a passing Luhn check.

```bash
python -m mcp_lab.task3.server
```

Point `UPSTREAM_LLM_URL` at a `/v1/chat/completions` SSE source.

## Task 4: Build a Rate-Limiting & Model Fallback Router for LLM Gateways

SQLite sliding window, 50k tokens / tenant / minute. Primary has a 3s deadline; `429` or timeout flips to the backup URL. Clients only see `{ error: { code, message, request_id } }`.

```bash
python -m mcp_lab.task4.server
```

## Layout

```
src/mcp_lab/task1  MCP server
src/mcp_lab/task2  JSON-RPC proxy + mock downstream
src/mcp_lab/task3  SSE PII filter
src/mcp_lab/task4  token window + model failover
tests/
```
