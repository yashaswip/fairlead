# fairlead

FDE take-home (MCP + LLM gateways). Python 3.11.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

I used the official `mcp` SDK, Pydantic, FastAPI, httpx, and SQLite on disk. Ports / URLs are in `.env.example`.

## Task 1

stdio MCP server: `python -m mcp_lab.task1.server`

- `get_customer_record` — `customer_id` like `CUST-10428` (CUST- + 5 digits)
- `trigger_refund` — same id, amount > 0, reason at least 10 chars

Invalid args raise `MCPError` / `-32602`. Don't `print()` in this process; stdout is the JSON-RPC stream, logs go to stderr.

Try `CUST-10428` or `CUST-22019`.

```json
{
  "command": "python",
  "args": ["-m", "mcp_lab.task1.server"],
  "cwd": "/absolute/path/to/this/repo"
}
```

## Task 2

```bash
python -m mcp_lab.task2.downstream   # mock MCP on :8091
python -m mcp_lab.task2.proxy        # gateway on :8080
```

Send `Authorization: Bearer admin` or `Bearer viewer` (JWT with a `role` claim also works).

`tools/list` is proxied through. `tools/call` with a name starting `admin_` is admin-only; viewers get `-32001` and the mock never sees the call.

```bash
curl -s localhost:8080/mcp \
  -H 'authorization: Bearer viewer' \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"admin_reset_key"}}'
```

## Task 3

Streaming proxy. It redacts emails / SSNs / Luhn cards to `[REDACTED]` as chunks come in. I keep a short tail so a split email still gets caught; I don't buffer the whole completion.

```bash
python -m mcp_lab.mocks.llm --mode leak --port 8092
python -m mcp_lab.task3.server
curl -N localhost:8081/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"hi"}],"stream":true}'
```

Point `UPSTREAM_LLM_URL` at a real `/v1/chat/completions` if you have one.

## Task 4

50k tokens/min per tenant key, stored in `./data/gateway.sqlite`. Primary has a 3s timeout; 429 or timeout goes to the backup URL. Errors look like `{error:{code,message,request_id}}` — I don't pass through upstream bodies.

```bash
python -m mcp_lab.task4.server
```

## Layout

```
src/mcp_lab/task1
src/mcp_lab/task2
src/mcp_lab/task3
src/mcp_lab/task4
src/mcp_lab/mocks   # fake LLM that leaks PII / 429s / hangs
tests/
```
