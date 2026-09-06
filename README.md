# fairlead

FDE take-home. Python 3.11, official `mcp` SDK.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## 1. MCP server (stdio)

The prompt asks for stdio, so this process talks JSON-RPC on stdin/stdout. Logs are stderr only.

```bash
python -m mcp_lab.task1.server
```

- `get_customer_record(customer_id)` — `CUST-` plus five digits
- `trigger_refund(customer_id, amount, reason)` — amount > 0, reason >= 10 chars

Pydantic rejects junk; that becomes JSON-RPC `-32602`. Sample ids: `CUST-10428`, `CUST-22019`.

## 2. MCP gateway

```bash
python -m mcp_lab.task2.downstream
python -m mcp_lab.task2.proxy
```

`Authorization: Bearer admin` or `Bearer viewer`. `tools/list` always goes downstream. `tools/call` on `admin_*` needs admin; otherwise `-32001` and we don't forward.

## 3. Streaming PII filter

```bash
python -m mcp_lab.mocks.llm --mode leak --port 8092
python -m mcp_lab.task3.server
```

Rewrites SSE deltas as they arrive (`[REDACTED]` for email / SSN / card). Doesn't wait for the full reply.

## 4. Rate limit + failover

```bash
python -m mcp_lab.task4.server
```

SQLite file `data/gateway.sqlite`, 50k tokens/min per API key. Primary 429 or 3s timeout → backup. Errors are `{code, message, request_id}` only.
