from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class GetCustomerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_id: str = Field(pattern=r"^CUST-\d{5}$")


class TriggerRefundInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_id: str = Field(pattern=r"^CUST-\d{5}$")
    amount: float = Field(gt=0)
    reason: str = Field(min_length=10)

    @field_validator("amount", mode="before")
    @classmethod
    def amount_is_number(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("amount must be a positive float")
        return float(value)


class Refund(BaseModel):
    id: str
    amount: float
    reason: str
    at: str


class CustomerRecord(BaseModel):
    customer_id: str
    name: str
    plan: Literal["starter", "growth", "enterprise"]
    balance_usd: float
    refunds: list[Refund] = Field(default_factory=list)


class LedgerError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_LEDGER: dict[str, CustomerRecord] = {
    "CUST-10428": CustomerRecord(
        customer_id="CUST-10428",
        name="Northwind Labs",
        plan="growth",
        balance_usd=1840.5,
    ),
    "CUST-22019": CustomerRecord(
        customer_id="CUST-22019",
        name="Pave Street Coffee",
        plan="starter",
        balance_usd=96.0,
    ),
}


def format_pydantic(err: ValidationError) -> str:
    bits = []
    for issue in err.errors():
        loc = ".".join(str(p) for p in issue["loc"]) or "(root)"
        bits.append(f"{loc}: {issue['msg']}")
    return "; ".join(bits)


def get_customer(customer_id: str) -> CustomerRecord | None:
    return _LEDGER.get(customer_id)


def apply_refund(customer_id: str, amount: float, reason: str) -> CustomerRecord:
    row = _LEDGER.get(customer_id)
    if row is None:
        raise LedgerError("NOT_FOUND", "customer not found")
    if amount > row.balance_usd:
        raise LedgerError("INSUFFICIENT", "amount exceeds remaining balance")
    refund = Refund(
        id=f"rf_{int(datetime.now(tz=timezone.utc).timestamp() * 1000):x}",
        amount=amount,
        reason=reason,
        at=datetime.now(tz=timezone.utc).isoformat(),
    )
    row.balance_usd = round(row.balance_usd - amount, 2)
    row.refunds.append(refund)
    return row
