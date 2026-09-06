from __future__ import annotations

import json

from mcp import MCPError
from mcp.server import MCPServer
from mcp.types import INVALID_PARAMS
from pydantic import ValidationError

from mcp_lab import configure_logging
from mcp_lab.task1.ledger import (
    GetCustomerInput,
    LedgerError,
    TriggerRefundInput,
    apply_refund,
    format_pydantic,
    get_customer,
)

log = configure_logging("customer-mcp")
mcp = MCPServer("customer-ops", version="1.0.0", log_level="WARNING")


def _parse(model, payload: dict):
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise MCPError(code=INVALID_PARAMS, message=format_pydantic(exc)) from exc


@mcp.tool(name="get_customer_record")
def get_customer_record(customer_id: str) -> str:
    """Look up a billing record. customer_id must match CUST-XXXXX."""
    args = _parse(GetCustomerInput, {"customer_id": customer_id})
    record = get_customer(args.customer_id)
    if record is None:
        raise MCPError(code=INVALID_PARAMS, message=f"unknown customer_id {args.customer_id}")
    return record.model_dump_json()


@mcp.tool(name="trigger_refund")
def trigger_refund(customer_id: str, amount: float, reason: str) -> str:
    """Issue a refund. amount > 0, reason at least 10 characters."""
    args = _parse(
        TriggerRefundInput,
        {"customer_id": customer_id, "amount": amount, "reason": reason},
    )
    try:
        record = apply_refund(args.customer_id, args.amount, args.reason)
    except LedgerError as exc:
        raise MCPError(code=INVALID_PARAMS, message=str(exc)) from exc
    last = record.refunds[-1]
    return json.dumps({"ok": True, "refund": last.model_dump(), "balance_usd": record.balance_usd})


def main() -> None:
    log.info("stdio transport; logs on stderr only")
    mcp.run()


if __name__ == "__main__":
    main()
