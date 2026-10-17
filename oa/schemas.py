from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BudgetResponse(BaseModel):
    department: str
    month: str
    currency: Literal["CNY"]
    total: str
    used: str
    remaining: str


class Supplier(BaseModel):
    id: str
    name: str
    category: str
    status: Literal["active", "inactive"]


class SuppliersResponse(BaseModel):
    count: int
    items: list[Supplier]


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
        allow_inf_nan=False,
    )
    currency: Literal["CNY"]


class ApprovalResponse(BaseModel):
    amount: str
    currency: Literal["CNY"]
    chain: list[str]
    rule_id: str
    rule_version: str