# MCP Gateway Lab

Python take-home for MCP + LLM gateway work. Python 3.11+, official `mcp` SDK, Pydantic, FastAPI, SQLite on disk.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Task 1 — customer MCP (stdio)

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

## Task 2 — MCP gateway

```bash
python -m mcp_lab.task2.downstream   # :8091
python -m mcp_lab.task2.proxy        # :8080
```

`Authorization: Bearer <token>` maps to admin/viewer (`TOKEN_ADMIN` / `TOKEN_VIEWER`).

- `tools/list` is forwarded
- `tools/call` with `params.name` starting `admin_` needs the admin token
- otherwise `{ "error": { "code": -32001, "message": "Unauthorized Tool Call" } }` and the downstream is not called

```bash
curl -s localhost:8080/mcp \
  -H 'authorization: Bearer vw_live_replace_me' \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"admin_reset_key"}}'
```

## Task 3 — streaming redaction

SSE proxy. Chunks are rewritten as they arrive. A 48-char holdback covers emails / SSNs / PANs split across reads. Cards need a passing Luhn check.

```bash
python -m mcp_lab.task3.server
```

Point `UPSTREAM_LLM_URL` at a `/v1/chat/completions` SSE source.

## Task 4 — rate limit + failover

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
