from contextlib import closing
from decimal import Decimal
from typing import Literal

from fastapi import FastAPI, HTTPException, Query

from oa.db import connect
from oa.rules import RULE_VERSION, get_approval_chain
from oa.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    BudgetResponse,
    SuppliersResponse,
)

app = FastAPI(title="模拟 OA 后端", version="0.2.0")


def yuan(cents: int) -> str:
    return format(Decimal(cents) / Decimal("100"), ".2f")


@app.get("/health")
def health():
    return {"status": "ok", "service": "oa"}


@app.get("/budgets", response_model=BudgetResponse)
def get_budget(
    department: str = Query(
        min_length=1,
        max_length=50,
        pattern=r"\S",
    ),
    month: str = Query(
        pattern=r"^[1-9][0-9]{3}-(0[1-9]|1[0-2])$",
    ),
):
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT * FROM budgets WHERE department = ? AND month = ?",
            (department.strip(), month),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="未找到该部门该月份的预算",
        )

    return {
        "department": row["department"],
        "month": row["month"],
        "currency": "CNY",
        "total": yuan(row["total_cents"]),
        "used": yuan(row["used_cents"]),
        "remaining": yuan(row["total_cents"] - row["used_cents"]),
    }


@app.get("/suppliers", response_model=SuppliersResponse)
def get_suppliers(
    category: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
        pattern=r"\S",
    ),
    keyword: str | None = Query(
        default=None,
        min_length=1,
        max_length=50,
        pattern=r"\S",
    ),
    status: Literal["active", "inactive"] | None = None,
):
    sql = "SELECT id, name, category, status FROM suppliers WHERE 1=1"
    params = []

    if category is not None:
        sql += " AND category = ?"
        params.append(category.strip())

    if keyword is not None:
        sql += " AND instr(name, ?) > 0"
        params.append(keyword.strip())

    if status is not None:
        sql += " AND status = ?"
        params.append(status)

    sql += " ORDER BY id"

    with closing(connect()) as conn:
        rows = conn.execute(sql, params).fetchall()

    items = [dict(row) for row in rows]
    return {"count": len(items), "items": items}


@app.post("/approval-chain", response_model=ApprovalResponse)
def approval_chain(body: ApprovalRequest):
    rule_id, chain = get_approval_chain(body.amount)

    return {
        "amount": format(body.amount, ".2f"),
        "currency": body.currency,
        "chain": chain,
        "rule_id": rule_id,
        "rule_version": RULE_VERSION,
    }