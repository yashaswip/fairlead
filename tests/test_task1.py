from pydantic import ValidationError

from mcp_lab.task1.ledger import GetCustomerInput, TriggerRefundInput, apply_refund, get_customer


def test_customer_id_schema():
    assert GetCustomerInput.model_validate({"customer_id": "CUST-10428"})
    for bad in ("cust-10428", "CUST-1", "CUST-1042A"):
        try:
            GetCustomerInput.model_validate({"customer_id": bad})
        except ValidationError:
            continue
        raise AssertionError(bad)


def test_rejects_unknown_fields():
    try:
        GetCustomerInput.model_validate({"customer_id": "CUST-10428", "extra": True})
    except ValidationError:
        return
    raise AssertionError("extra fields must fail")


def test_refund_schema():
    TriggerRefundInput.model_validate(
        {"customer_id": "CUST-10428", "amount": 12.5, "reason": "duplicate charge on invoice"}
    )
    for payload in (
        {"customer_id": "CUST-10428", "amount": 0, "reason": "duplicate charge on invoice"},
        {"customer_id": "CUST-10428", "amount": 1, "reason": "too short"},
    ):
        try:
            TriggerRefundInput.model_validate(payload)
        except ValidationError:
            continue
        raise AssertionError(payload)


def test_ledger_rejects_over_refund():
    before = get_customer("CUST-22019").balance_usd
    try:
        apply_refund("CUST-22019", before + 1, "customer asked for a full refund")
    except Exception as exc:
        assert "exceeds" in str(exc)
        return
    raise AssertionError("over-refund must fail")
