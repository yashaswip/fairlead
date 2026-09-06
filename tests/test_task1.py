import json

import pytest
from mcp import MCPError
from mcp.client import Client
from mcp.types import INVALID_PARAMS

from mcp_lab.task1.ledger import GetCustomerInput, TriggerRefundInput, apply_refund, get_customer
from mcp_lab.task1.server import mcp
from pydantic import ValidationError


def test_customer_id_schema():
    GetCustomerInput.model_validate({"customer_id": "CUST-10428"})
    for bad in ("cust-10428", "CUST-1", "CUST-1042A"):
        with pytest.raises(ValidationError):
            GetCustomerInput.model_validate({"customer_id": bad})


def test_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        GetCustomerInput.model_validate({"customer_id": "CUST-10428", "extra": True})


def test_refund_schema():
    TriggerRefundInput.model_validate(
        {"customer_id": "CUST-10428", "amount": 12.5, "reason": "duplicate charge on invoice"}
    )
    with pytest.raises(ValidationError):
        TriggerRefundInput.model_validate(
            {"customer_id": "CUST-10428", "amount": 0, "reason": "duplicate charge on invoice"}
        )
    with pytest.raises(ValidationError):
        TriggerRefundInput.model_validate({"customer_id": "CUST-10428", "amount": 1, "reason": "too short"})


def test_ledger_rejects_over_refund():
    before = get_customer("CUST-22019").balance_usd
    with pytest.raises(Exception, match="exceeds"):
        apply_refund("CUST-22019", before + 1, "customer asked for a full refund")


@pytest.mark.asyncio
async def test_mcp_get_customer_record():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools.tools}
        assert names == {"get_customer_record", "trigger_refund"}
        result = await client.call_tool("get_customer_record", {"customer_id": "CUST-10428"})
        payload = json.loads(result.content[0].text)
        assert payload["name"] == "Northwind Labs"


@pytest.mark.asyncio
async def test_mcp_invalid_customer_id_is_jsonrpc_invalid_params():
    async with Client(mcp) as client:
        with pytest.raises(MCPError) as err:
            await client.call_tool("get_customer_record", {"customer_id": "CUST-1"})
        assert err.value.code == INVALID_PARAMS
