# fairlead

Python take-home for the FDE assessment: MCP servers, MCP gateways, LLM gateways, and stream guardrails.

Python 3.11+, official `mcp` 2.x, Pydantic v2, FastAPI, httpx, SQLite on disk.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

**25 tests.** Copy `.env.example` if you need non-default ports.

## Task 1: Build a Custom MCP Server with Strict Validation & Transport Handling

`src/mcp_lab/task1/server.py` — official SDK, **stdio**.

| Tool | Input |
|------|--------|
| `get_customer_record` | `customer_id` = `CUST-XXXXX` (`CUST-` + 5 digits) |
| `trigger_refund` | same id, `amount` > 0, `reason` min length 10 |

Pydantic (`extra="forbid"`). Bad input → `MCPError(INVALID_PARAMS)` → JSON-RPC **`-32602`**. Logs go to **stderr** only; stdout is the MCP wire. No `print()`.

```bash
python -m mcp_lab.task1.server
```

Seed records: `CUST-10428`, `CUST-22019`.

```json
{
  "command": "python",
  "args": ["-m", "mcp_lab.task1.server"],
  "cwd": "/absolute/path/to/fairlead"
}
```

## Task 2: Implement an MCP Security Gateway Proxy (Tool Filtering & Auth)

HTTP JSON-RPC reverse proxy between an agent and a mock MCP server.

```bash
python -m mcp_lab.task2.downstream   # :8091
python -m mcp_lab.task2.proxy        # :8080
```

`Authorization: Bearer <token>` — role is `admin` or `viewer` (`Bearer admin` / `Bearer viewer`, or HS256 JWT `{"role": ...}`).

- `tools/list` — forward as-is
- `tools/call` — if `params.name` starts with `admin_`, role must be admin; otherwise JSON-RPC **`-32001 Unauthorized Tool Call`** and the downstream is **not** called

```bash
curl -s localhost:8080/mcp \
  -H 'authorization: Bearer viewer' \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"admin_reset_key"}}'
```

## Task 3: Implement an LLM Gateway Streaming Guardrail (PII Redaction)

Proxies `/v1/chat/completions`, rewrites SSE **deltas** as they arrive. Emails, SSNs, and Luhn-valid cards become `[REDACTED]`. Only an incomplete suffix is held (not the full reply).

```bash
python -m mcp_lab.mocks.llm --mode leak --port 8092
python -m mcp_lab.task3.server
curl -N localhost:8081/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"hi"}],"stream":true}'
```

Or set `UPSTREAM_LLM_URL` to a real OpenAI-style SSE endpoint.

## Task 4: Build a Rate-Limiting & Model Fallback Router for LLM Gateways

On-disk SQLite sliding window: **50,000 tokens/minute per tenant API key** (`Authorization: Bearer <key>`).

If the primary returns **429** or exceeds **3000ms**, the request fails over to the backup. Client errors are `{ "error": { "code", "message", "request_id" } }` — no upstream bodies or stack traces.

```bash
python -m mcp_lab.task4.server
```

`SQLITE_PATH` default: `./data/gateway.sqlite`.

## Layout

```
src/mcp_lab/task1   MCP server (stdio)
src/mcp_lab/task2   JSON-RPC gateway + mock downstream
src/mcp_lab/task3   streaming PII filter
src/mcp_lab/task4   token window + failover
src/mcp_lab/mocks   leaky/429/slow LLM stub
tests/              25 tests
```
